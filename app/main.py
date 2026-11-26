from __future__ import annotations
import os, json, hashlib, shutil
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi import UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, inspect, text
from sqlalchemy.exc import IntegrityError
from .database import Base, engine, get_db, SessionLocal
from . import models as m
from .schemas import (LoginIn, MfaCodeIn, PartyIn, LeadIn, OpportunityIn, ContractIn, PaymentIn, CountryIn, BusinessUnitIn, PasswordResetIn,
                      ProjectIn, PropertyUnitIn, PropertyReservationIn, FoodProductIn,
                      FoodOrderIn, CarIn, CarBookingIn, MaintenanceIn, TaskIn, UserIn)
from .security import (verify_password, hash_password, issue_session, revoke_session,
                       get_current_user, set_session_cookie, clear_session_cookie, COOKIE_NAME, session_token_hash)
from .mfa import decrypt_secret, encrypt_secret, is_mfa_required, new_secret, provisioning_uri, verify_totp

from .production import is_production, validate_production, protect_requests
from .observability import request_observability
from .storage import save_document, load_document, delete_document

APP_NAME = os.getenv("APP_NAME", "SAWA UNITED Business Management System")
app = FastAPI(title=APP_NAME, version="1.0.0", description="Internal multi-business management platform API",
              docs_url=None if is_production() else "/docs",
              redoc_url=None if is_production() else "/redoc",
              openapi_url=None if is_production() else "/openapi.json")
app.middleware("http")(protect_requests)
app.middleware("http")(request_observability)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

UNIT_SEEDS = [
    ("REAL_ESTATE", "العقارات", "Real Estate"),
    ("SAWA_FOOD", "سوا فود", "Sawa Food"),
    ("MASHARY_CARS", "مشاري كارز", "Mashary Cars"),
    ("VENTURES", "مشروعات واستثمارات", "Other Ventures"),
]
COUNTRY_SEEDS = [
    ("EG", "مصر", "Egypt", "EGP", "Africa/Cairo"),
    ("MA", "المغرب", "Morocco", "MAD", "Africa/Casablanca"),
    ("KW", "الكويت", "Kuwait", "KWD", "Asia/Kuwait"),
    ("AE", "الإمارات", "United Arab Emirates", "AED", "Asia/Dubai"),
    ("SA", "السعودية", "Saudi Arabia", "SAR", "Asia/Riyadh"),
]

def _upgrade_local_mfa_columns():
    """Backfill only the new MFA columns for pre-existing local SQLite databases."""
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "users": {
            "mfa_enabled": "BOOLEAN NOT NULL DEFAULT 0",
            "mfa_secret_encrypted": "VARCHAR(500)",
            "mfa_pending_secret_encrypted": "VARCHAR(500)",
            "mfa_last_counter": "INTEGER NOT NULL DEFAULT -1",
        },
        "session_tokens": {"mfa_verified": "BOOLEAN NOT NULL DEFAULT 0"},
    }
    with engine.begin() as connection:
        schema = inspect(connection)
        tables = set(schema.get_table_names())
        for table_name, columns in additions.items():
            if table_name not in tables:
                continue
            present = {column["name"] for column in schema.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name not in present:
                    connection.exec_driver_sql(
                        f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}'
                    )


def startup(initialize=False):
    validate_production()
    if is_production():
        schema = inspect(engine)
        existing_tables = set(schema.get_table_names())
        missing_tables = set(Base.metadata.tables) - existing_tables
        missing_columns = {}
        for table_name, table in Base.metadata.tables.items():
            if table_name in existing_tables:
                actual = {column["name"] for column in schema.get_columns(table_name)}
                absent = {column.name for column in table.columns} - actual
                if absent:
                    missing_columns[table_name] = sorted(absent)
        if missing_tables or missing_columns:
            raise RuntimeError(
                "Production schema incomplete. Apply reviewed migrations before startup. "
                f"Missing tables: {sorted(missing_tables)}; missing columns: {missing_columns}"
            )
    else:
        Base.metadata.create_all(bind=engine)
        _upgrade_local_mfa_columns()
    if is_production() and not initialize:
        return
    db = SessionLocal()
    try:
        for code, ar, en in UNIT_SEEDS:
            if not db.query(m.BusinessUnit).filter_by(code=code).first():
                db.add(m.BusinessUnit(code=code, name_ar=ar, name_en=en))
        for code, ar, en, currency, tz in COUNTRY_SEEDS:
            if not db.get(m.Country, code):
                db.add(m.Country(code=code, name_ar=ar, name_en=en, default_currency=currency, timezone=tz))
        admin_email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@sawa.local").lower()
        if not db.query(m.User).filter_by(email=admin_email).first():
            password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "ChangeMeNow!2026")
            if is_production() and (len(password) < 16 or password == "ChangeMeNow!2026"):
                raise RuntimeError("First production startup requires a unique admin password of at least 16 characters")
            user = m.User(email=admin_email,
                          full_name="مدير النظام",
                          password_hash=hash_password(password),
                          role="super_admin")
            db.add(user)
        db.commit()
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app_instance):
    startup()
    yield

app.router.lifespan_context = lifespan

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/health")
def health():
    return {"status": "ok", "service": "sawa-united", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ready"}

def unit_by_code(db: Session, code: str) -> m.BusinessUnit:
    unit = db.query(m.BusinessUnit).filter(m.BusinessUnit.code == code, m.BusinessUnit.active.is_(True)).first()
    if not unit:
        raise HTTPException(422, f"نشاط غير معروف: {code}")
    return unit

def ensure_unit_access(user: m.User, unit: m.BusinessUnit):
    if user.role in {"super_admin", "group_manager"}:
        return
    allowed = {x.business_unit_id for x in user.units}
    if unit.id not in allowed:
        raise HTTPException(403, "ليس لديك صلاحية الوصول إلى هذا النشاط")

def ensure_party_access(db: Session, user: m.User, party_id: str | None, unit: m.BusinessUnit):
    if not party_id or user.role in {"super_admin", "group_manager"}:
        return
    allowed = db.query(m.PartyBusinessUnit).filter_by(party_id=party_id, business_unit_id=unit.id).first()
    if not allowed:
        raise HTTPException(403, "ملف الطرف غير مرتبط بالنشاط المصرح لك به")

def require_any_role(user: m.User, roles: set[str]):
    if user.role not in roles:
        raise HTTPException(403, "ليست لديك الصلاحية المطلوبة")

def audit(db: Session, user: m.User | None, action: str, entity_type: str, entity_id: str | None, details: dict | None = None, ip: str | None = None):
    db.add(m.AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type,
                      entity_id=entity_id, details=json.dumps(details, ensure_ascii=False, default=str) if details else None,
                      ip_address=ip))

def norm_dt(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def json_entity(entity):
    return entity

def new_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}"

@app.post("/api/v1/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    from .login_limits import check_login_budget
    check_login_budget(db, payload.email)
    user = db.query(m.User).filter(func.lower(m.User.email) == payload.email.lower()).with_for_update().first()
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "البريد الإلكتروني أو كلمة المرور غير صحيحة")

    mfa_verified = False
    if user.mfa_enabled:
        if not user.mfa_secret_encrypted:
            raise HTTPException(503, "إعداد المصادقة الثنائية غير مكتمل؛ تواصل مع مسؤول النظام")
        try:
            secret = decrypt_secret(user.mfa_secret_encrypted)
        except RuntimeError:
            raise HTTPException(503, "تعذر التحقق بالمصادقة الثنائية؛ تواصل مع مسؤول النظام") from None
        counter = verify_totp(secret, payload.mfa_code, last_counter=user.mfa_last_counter)
        if counter is None:
            raise HTTPException(401, "رمز المصادقة الثنائية غير صحيح أو مستخدم سابقًا")
        user.mfa_last_counter = counter
        mfa_verified = True

    setup_required = is_mfa_required(user.role) and not user.mfa_enabled
    token = issue_session(db, user, mfa_verified=mfa_verified)
    set_session_cookie(response, token)
    audit(db, user, "login", "user", user.id, {"mfa_verified": mfa_verified})
    db.commit()
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role,
            "mfa_setup_required": setup_required}

@app.get("/api/v1/auth/mfa/status")
def mfa_status(user: m.User = Depends(get_current_user)):
    return {"enabled": user.mfa_enabled, "required": is_mfa_required(user.role)}

@app.post("/api/v1/auth/mfa/setup")
def mfa_setup(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    locked_user = (db.query(m.User).filter(m.User.id == user.id)
                   .with_for_update().populate_existing().first())
    if not locked_user:
        raise HTTPException(401, "الحساب غير موجود؛ سجل الدخول مجددًا")
    if locked_user.mfa_enabled:
        raise HTTPException(409, "المصادقة الثنائية مفعلة بالفعل")
    secret = new_secret()
    locked_user.mfa_pending_secret_encrypted = encrypt_secret(secret)
    audit(db, locked_user, "mfa_setup_started", "user", locked_user.id)
    db.commit()
    return {"secret": secret, "otpauth_uri": provisioning_uri(locked_user.email, secret),
            "issuer": "SAWA UNITED", "digits": 6, "period_seconds": 30}

@app.post("/api/v1/auth/mfa/confirm")
def mfa_confirm(payload: MfaCodeIn, request: Request, db: Session = Depends(get_db),
                user: m.User = Depends(get_current_user)):
    from .login_limits import check_login_budget
    check_login_budget(db, user.email)
    locked_user = (db.query(m.User).filter(m.User.id == user.id)
                   .with_for_update().populate_existing().first())
    if not locked_user or not locked_user.mfa_pending_secret_encrypted or locked_user.mfa_enabled:
        raise HTTPException(409, "ابدأ إعداد المصادقة الثنائية أولًا")
    try:
        secret = decrypt_secret(locked_user.mfa_pending_secret_encrypted)
    except RuntimeError:
        raise HTTPException(503, "تعذر استعادة إعداد المصادقة؛ ابدأ الإعداد من جديد") from None
    counter = verify_totp(secret, payload.code, last_counter=locked_user.mfa_last_counter)
    if counter is None:
        raise HTTPException(422, "رمز التحقق غير صحيح أو منتهي الصلاحية")
    locked_user.mfa_secret_encrypted = locked_user.mfa_pending_secret_encrypted
    locked_user.mfa_pending_secret_encrypted = None
    locked_user.mfa_enabled = True
    locked_user.mfa_last_counter = counter

    token = request.cookies.get(COOKIE_NAME)
    session_row = db.query(m.SessionToken).filter_by(token_hash=session_token_hash(token or ""), revoked=False).first()
    if not session_row:
        db.rollback()
        raise HTTPException(401, "انتهت الجلسة؛ سجل الدخول مجددًا")
    session_row.mfa_verified = True
    audit(db, locked_user, "mfa_enabled", "user", locked_user.id)
    db.commit()
    return {"ok": True, "mfa_enabled": True}

@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    revoke_session(db, token)
    clear_session_cookie(response)
    return {"ok": True}

@app.get("/api/v1/auth/me")
def me(user: m.User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role,
            "business_units": [x.business_unit_id for x in user.units]}

@app.get("/api/v1/reference/business-units")
def list_units(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    q = db.query(m.BusinessUnit).filter(m.BusinessUnit.active.is_(True))
    if user.role not in {"super_admin", "group_manager"}:
        ids = [x.business_unit_id for x in user.units]
        q = q.filter(m.BusinessUnit.id.in_(ids))
    return q.order_by(m.BusinessUnit.code).all()

@app.get("/api/v1/reference/countries")
def list_countries(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    return db.query(m.Country).filter(m.Country.active.is_(True)).order_by(m.Country.name_en).all()

@app.post("/api/v1/reference/business-units", status_code=201)
def create_business_unit(payload: BusinessUnitIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin"})
    row = m.BusinessUnit(code=payload.code.strip().upper(), name_ar=payload.name_ar, name_en=payload.name_en)
    db.add(row)
    try: db.commit(); db.refresh(row)
    except IntegrityError: db.rollback(); raise HTTPException(409, "رمز النشاط مسجل بالفعل")
    return row

@app.post("/api/v1/reference/countries", status_code=201)
def create_country(payload: CountryIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin"})
    data = payload.model_dump(); data["code"] = data["code"].upper(); data["default_currency"] = data["default_currency"].upper()
    row = m.Country(**data); db.add(row)
    try: db.commit(); db.refresh(row)
    except IntegrityError: db.rollback(); raise HTTPException(409, "رمز الدولة مسجل بالفعل")
    return row

@app.get("/api/v1/users")
def list_users(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin", "group_manager"})
    rows = db.query(m.User).order_by(m.User.created_at.desc()).all()
    return [{"id": x.id, "email": x.email, "full_name": x.full_name, "role": x.role,
             "active": x.active, "mfa_enabled": x.mfa_enabled,
             "units": [{"business_unit_id": z.business_unit_id} for z in x.units],
             "created_at": x.created_at} for x in rows]

@app.post("/api/v1/users", status_code=201)
def create_user(payload: UserIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin"})
    valid_roles = {"super_admin", "group_manager", "business_manager", "sales", "contract_manager", "accountant", "operations", "viewer"}
    if payload.role not in valid_roles:
        raise HTTPException(422, "دور المستخدم غير صالح")
    email = payload.email.strip().lower()
    if db.query(m.User).filter(func.lower(m.User.email) == email).first():
        raise HTTPException(409, "البريد الإلكتروني مسجل بالفعل")
    if payload.role not in {"super_admin", "group_manager"} and not payload.business_unit_codes:
        raise HTTPException(422, "يجب تخصيص نشاط واحد على الأقل لهذا المستخدم")
    row = m.User(email=email, full_name=payload.full_name, password_hash=hash_password(payload.password), role=payload.role)
    db.add(row); db.flush()
    for code in payload.business_unit_codes:
        unit = unit_by_code(db, code)
        db.add(m.UserBusinessUnit(user_id=row.id, business_unit_id=unit.id))
    audit(db, user, "create", "user", row.id, {"email": row.email, "role": row.role})
    db.commit(); db.refresh(row)
    return {"id": row.id, "email": row.email, "full_name": row.full_name, "role": row.role,
            "business_units": [x.business_unit_id for x in row.units]}

@app.post("/api/v1/users/{user_id}/reset-password")
def reset_user_password(user_id: str, payload: PasswordResetIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin"})
    target = db.get(m.User, user_id)
    if not target: raise HTTPException(404, "المستخدم غير موجود")
    target.password_hash = hash_password(payload.password)
    target.mfa_enabled = False
    target.mfa_secret_encrypted = None
    target.mfa_pending_secret_encrypted = None
    target.mfa_last_counter = -1
    for session in db.query(m.SessionToken).filter(m.SessionToken.user_id == target.id).all():
        session.revoked = True
    audit(db, user, "reset_password", "user", target.id, {"mfa_reset": True})
    db.commit()
    return {"ok": True, "message": "تم تغيير كلمة المرور وإبطال الجلسات السابقة"}

@app.post("/api/v1/users/{user_id}/deactivate")
def deactivate_user(user_id: str, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin"})
    target = db.get(m.User, user_id)
    if not target: raise HTTPException(404, "المستخدم غير موجود")
    if target.id == user.id: raise HTTPException(409, "لا يمكنك تعطيل حسابك الحالي")
    target.active = False
    for session in db.query(m.SessionToken).filter(m.SessionToken.user_id == target.id).all():
        session.revoked = True
    audit(db, user, "deactivate", "user", target.id)
    db.commit()
    return {"ok": True}

@app.get("/api/v1/dashboard")
def dashboard(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    units = db.query(m.BusinessUnit).filter(m.BusinessUnit.active.is_(True)).all()
    if user.role not in {"super_admin", "group_manager"}:
        allowed_ids = {x.business_unit_id for x in user.units}
        units = [u for u in units if u.id in allowed_ids]
    result = []
    for unit in units:
        leads = db.query(m.Lead).filter(m.Lead.business_unit_id == unit.id).count()
        opps = db.query(m.Opportunity).filter(m.Opportunity.business_unit_id == unit.id).count()
        contracts = db.query(m.Contract).filter(m.Contract.business_unit_id == unit.id).count()
        pending_contracts = db.query(m.Contract).filter(m.Contract.business_unit_id == unit.id,
                                                         m.Contract.status.in_(["draft", "review", "approved", "sent"])).count()
        result.append({"code": unit.code, "name_ar": unit.name_ar, "leads": leads,
                       "opportunities": opps, "contracts": contracts, "pending_contracts": pending_contracts})
    return {"business_units": result,
            "parties": db.query(m.Party).count(),
            "active_cars": db.query(m.Car).filter(m.Car.status == "available").count(),
            "food_products": db.query(m.FoodProduct).filter(m.FoodProduct.active.is_(True)).count(),
            "open_tasks": db.query(m.Task).filter(m.Task.status == "open").count()}

# CRM
@app.get("/api/v1/parties")
def list_parties(q: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    query = db.query(m.Party).filter(m.Party.active.is_(True))
    if user.role not in {"super_admin", "group_manager"}:
        allowed_ids = [x.business_unit_id for x in user.units]
        query = query.join(m.PartyBusinessUnit).filter(m.PartyBusinessUnit.business_unit_id.in_(allowed_ids))
    if q:
        term = f"%{q}%"
        query = query.filter(or_(m.Party.display_name.ilike(term), m.Party.phone.ilike(term), m.Party.email.ilike(term)))
    return query.distinct().order_by(m.Party.created_at.desc()).limit(250).all()

@app.post("/api/v1/parties", status_code=201)
def create_party(payload: PartyIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    data = payload.model_dump(exclude={"business_unit_codes"})
    party = m.Party(**data)
    db.add(party); db.flush()
    if user.role not in {"super_admin", "group_manager"} and not payload.business_unit_codes:
        db.rollback(); raise HTTPException(422, "يجب ربط العميل بنشاط واحد على الأقل")
    for code in payload.business_unit_codes:
        business_unit = unit_by_code(db, code); ensure_unit_access(user, business_unit)
        db.add(m.PartyBusinessUnit(party_id=party.id, business_unit_id=business_unit.id))
    audit(db, user, "create", "party", party.id, {"display_name": party.display_name}, request.client.host if request.client else None)
    db.commit(); db.refresh(party)
    return party

@app.get("/api/v1/leads")
def list_leads(business_unit_code: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    query = db.query(m.Lead)
    if business_unit_code:
        unit = unit_by_code(db, business_unit_code); ensure_unit_access(user, unit); query = query.filter_by(business_unit_id=unit.id)
    elif user.role not in {"super_admin", "group_manager"}:
        query = query.filter(m.Lead.business_unit_id.in_([x.business_unit_id for x in user.units]))
    return query.order_by(m.Lead.created_at.desc()).limit(250).all()

@app.post("/api/v1/leads", status_code=201)
def create_lead(payload: LeadIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    unit = unit_by_code(db, payload.business_unit_code); ensure_unit_access(user, unit)
    ensure_party_access(db, user, payload.party_id, unit)
    row = m.Lead(party_id=payload.party_id, business_unit_id=unit.id, country_code=payload.country_code,
                 source=payload.source, subject=payload.subject, assigned_to=payload.assigned_to, notes=payload.notes)
    db.add(row); db.flush(); audit(db, user, "create", "lead", row.id, {"subject": row.subject}, request.client.host if request.client else None)
    db.commit(); db.refresh(row); return row

@app.get("/api/v1/opportunities")
def list_opportunities(business_unit_code: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    query = db.query(m.Opportunity)
    if business_unit_code:
        unit = unit_by_code(db, business_unit_code); ensure_unit_access(user, unit); query = query.filter_by(business_unit_id=unit.id)
    elif user.role not in {"super_admin", "group_manager"}:
        query = query.filter(m.Opportunity.business_unit_id.in_([x.business_unit_id for x in user.units]))
    return query.order_by(m.Opportunity.created_at.desc()).limit(250).all()

@app.post("/api/v1/opportunities", status_code=201)
def create_opportunity(payload: OpportunityIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    unit = unit_by_code(db, payload.business_unit_code); ensure_unit_access(user, unit)
    if not db.get(m.Party, payload.party_id): raise HTTPException(404, "العميل غير موجود")
    ensure_party_access(db, user, payload.party_id, unit)
    data = payload.model_dump(exclude={"business_unit_code"})
    row = m.Opportunity(**data, business_unit_id=unit.id, owner_id=user.id)
    db.add(row); db.flush(); audit(db, user, "create", "opportunity", row.id)
    db.commit(); db.refresh(row); return row

# Contracts & finance
CONTRACT_TRANSITIONS = {
    "draft": {"review"}, "review": {"draft", "approved"}, "approved": {"sent", "signed"},
    "sent": {"signed", "approved"}, "signed": {"active"}, "active": {"expired", "terminated"},
}
@app.get("/api/v1/contracts")
def list_contracts(business_unit_code: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    query = db.query(m.Contract)
    if business_unit_code:
        unit = unit_by_code(db, business_unit_code); ensure_unit_access(user, unit); query = query.filter_by(business_unit_id=unit.id)
    elif user.role not in {"super_admin", "group_manager"}:
        query = query.filter(m.Contract.business_unit_id.in_([x.business_unit_id for x in user.units]))
    return query.order_by(m.Contract.created_at.desc()).limit(250).all()

@app.post("/api/v1/contracts", status_code=201)
def create_contract(payload: ContractIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    unit = unit_by_code(db, payload.business_unit_code); ensure_unit_access(user, unit)
    if not db.get(m.Party, payload.party_id): raise HTTPException(404, "الطرف المتعاقد غير موجود")
    ensure_party_access(db, user, payload.party_id, unit)
    if payload.end_date and payload.start_date and payload.end_date < payload.start_date: raise HTTPException(422, "تاريخ نهاية العقد يسبق تاريخ بدايته")
    data = payload.model_dump(exclude={"business_unit_code"})
    row = m.Contract(**data, business_unit_id=unit.id, created_by=user.id)
    db.add(row)
    try:
        db.flush(); audit(db, user, "create", "contract", row.id, {"contract_no": row.contract_no}, request.client.host if request.client else None)
        db.commit(); db.refresh(row)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "رقم العقد مستخدم بالفعل")
    return row

@app.post("/api/v1/contracts/{contract_id}/transition")
def transition_contract(contract_id: str, new_status: str, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    row = db.get(m.Contract, contract_id)
    if not row: raise HTTPException(404, "العقد غير موجود")
    unit = db.get(m.BusinessUnit, row.business_unit_id); ensure_unit_access(user, unit)
    if new_status in {"approved", "signed", "active", "terminated"}:
        require_any_role(user, {"super_admin", "group_manager", "business_manager", "contract_manager"})
    if new_status not in CONTRACT_TRANSITIONS.get(row.status, set()):
        raise HTTPException(409, f"لا يمكن نقل العقد من {row.status} إلى {new_status}")
    old = row.status; row.status = new_status
    audit(db, user, "transition", "contract", row.id, {"from": old, "to": new_status}, request.client.host if request.client else None)
    db.commit(); db.refresh(row); return row

@app.post("/api/v1/finance/payments", status_code=201)
def create_payment(payload: PaymentIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin", "group_manager", "business_manager", "accountant"})
    unit = unit_by_code(db, payload.business_unit_code); ensure_unit_access(user, unit)
    if payload.direction not in {"receipt", "payment"}: raise HTTPException(422, "اتجاه الحركة غير صحيح")
    if not db.get(m.Party, payload.party_id): raise HTTPException(404, "الطرف غير موجود")
    ensure_party_access(db, user, payload.party_id, unit)
    if payload.contract_id:
        contract = db.get(m.Contract, payload.contract_id)
        if not contract: raise HTTPException(404, "العقد غير موجود")
        if contract.currency != payload.currency: raise HTTPException(422, "عملة الحركة يجب أن تطابق عملة العقد")
    row = m.Payment(**payload.model_dump(exclude={"business_unit_code"}), business_unit_id=unit.id)
    db.add(row); db.flush(); audit(db, user, "create", "payment", row.id, {"amount": str(row.amount), "currency": row.currency})
    db.commit(); db.refresh(row); return row

@app.get("/api/v1/finance/payments")
def list_payments(business_unit_code: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    query = db.query(m.Payment)
    if business_unit_code:
        unit = unit_by_code(db, business_unit_code); ensure_unit_access(user, unit); query = query.filter_by(business_unit_id=unit.id)
    elif user.role not in {"super_admin", "group_manager"}:
        query = query.filter(m.Payment.business_unit_id.in_([x.business_unit_id for x in user.units]))
    return query.order_by(m.Payment.created_at.desc()).limit(250).all()

# Real estate
@app.get("/api/v1/real-estate/projects")
def list_projects(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    unit = unit_by_code(db, "REAL_ESTATE"); ensure_unit_access(user, unit)
    return db.query(m.RealEstateProject).order_by(m.RealEstateProject.created_at.desc()).all()

@app.post("/api/v1/real-estate/projects", status_code=201)
def create_project(payload: ProjectIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "REAL_ESTATE"))
    row = m.RealEstateProject(**payload.model_dump()); db.add(row); db.flush()
    audit(db, user, "create", "real_estate_project", row.id)
    db.commit(); db.refresh(row); return row

@app.get("/api/v1/real-estate/projects/{project_id}/units")
def list_property_units(project_id: str, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "REAL_ESTATE"))
    if not db.get(m.RealEstateProject, project_id): raise HTTPException(404, "المشروع غير موجود")
    return db.query(m.PropertyUnit).filter_by(project_id=project_id).order_by(m.PropertyUnit.unit_code).all()

@app.post("/api/v1/real-estate/projects/{project_id}/units", status_code=201)
def create_property_unit(project_id: str, payload: PropertyUnitIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "REAL_ESTATE"))
    if not db.get(m.RealEstateProject, project_id): raise HTTPException(404, "المشروع غير موجود")
    row = m.PropertyUnit(project_id=project_id, **payload.model_dump()); db.add(row)
    try: db.commit(); db.refresh(row)
    except IntegrityError: db.rollback(); raise HTTPException(409, "كود الوحدة موجود في المشروع")
    return row

@app.get("/api/v1/real-estate/units")
def list_all_property_units(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "REAL_ESTATE"))
    return db.query(m.PropertyUnit).order_by(m.PropertyUnit.created_at.desc()).limit(500).all()

@app.get("/api/v1/real-estate/reservations")
def list_property_reservations(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "REAL_ESTATE"))
    return db.query(m.PropertyReservation).order_by(m.PropertyReservation.created_at.desc()).limit(250).all()

@app.post("/api/v1/real-estate/reservations", status_code=201)
def create_property_reservation(payload: PropertyReservationIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "REAL_ESTATE"))
    unit = db.query(m.PropertyUnit).filter(m.PropertyUnit.id == payload.unit_id).with_for_update().first()
    if not unit: raise HTTPException(404, "الوحدة غير موجودة")
    start, end = norm_dt(payload.start_at), norm_dt(payload.expires_at)
    if end <= start: raise HTTPException(422, "انتهاء الحجز يجب أن يكون بعد بدايته")
    now = datetime.now(timezone.utc)
    conflict = db.query(m.PropertyReservation).filter(m.PropertyReservation.unit_id == unit.id,
        m.PropertyReservation.status.in_(["pending", "confirmed"]),
        m.PropertyReservation.expires_at > now,
        m.PropertyReservation.start_at < end,
        m.PropertyReservation.expires_at > start).first()
    if conflict or unit.status in {"sold", "blocked"}:
        raise HTTPException(409, "الوحدة غير متاحة خلال الفترة المطلوبة")
    row = m.PropertyReservation(unit_id=unit.id, party_id=payload.party_id, start_at=start, expires_at=end,
                                deposit_amount=payload.deposit_amount, currency=payload.currency)
    db.add(row); unit.status = "reserved"; db.flush(); audit(db, user, "reserve", "property_unit", unit.id, {"reservation_id": row.id})
    db.commit(); db.refresh(row); return row

@app.post("/api/v1/real-estate/reservations/{reservation_id}/cancel")
def cancel_property_reservation(reservation_id: str, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "REAL_ESTATE"))
    row = db.get(m.PropertyReservation, reservation_id)
    if not row: raise HTTPException(404, "الحجز غير موجود")
    if row.status not in {"pending", "confirmed"}: raise HTTPException(409, "لا يمكن إلغاء هذا الحجز")
    row.status = "cancelled"
    unit = db.get(m.PropertyUnit, row.unit_id)
    other = db.query(m.PropertyReservation).filter(m.PropertyReservation.unit_id == row.unit_id,
        m.PropertyReservation.id != row.id, m.PropertyReservation.status.in_(["pending", "confirmed"]),
        m.PropertyReservation.expires_at > datetime.now(timezone.utc)).first()
    if not other and unit.status == "reserved": unit.status = "available"
    db.commit(); db.refresh(row); return row

# Sawa Food
@app.get("/api/v1/food/products")
def list_food_products(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "SAWA_FOOD"))
    return db.query(m.FoodProduct).filter(m.FoodProduct.active.is_(True)).order_by(m.FoodProduct.name).all()

@app.post("/api/v1/food/products", status_code=201)
def create_food_product(payload: FoodProductIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "SAWA_FOOD"))
    row = m.FoodProduct(**payload.model_dump()); db.add(row)
    try: db.commit(); db.refresh(row)
    except IntegrityError: db.rollback(); raise HTTPException(409, "رمز الصنف مستخدم بالفعل")
    return row

@app.post("/api/v1/food/orders", status_code=201)
def create_food_order(payload: FoodOrderIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "SAWA_FOOD"))
    if payload.business_model not in {"direct", "brokerage"}: raise HTTPException(422, "نموذج الصفقة يجب أن يكون direct أو brokerage")
    if payload.business_model == "brokerage" and not payload.supplier_party_id:
        raise HTTPException(422, "يجب تحديد المورد في صفقة الوساطة")
    food_unit = unit_by_code(db, "SAWA_FOOD")
    ensure_party_access(db, user, payload.customer_party_id, food_unit)
    ensure_party_access(db, user, payload.supplier_party_id, food_unit)
    total = sum((x.quantity * x.unit_price for x in payload.lines), Decimal("0"))
    commission = (total * payload.commission_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    order = m.FoodOrder(order_no=new_number("SF"), business_model=payload.business_model,
        customer_party_id=payload.customer_party_id, supplier_party_id=payload.supplier_party_id,
        country_code=payload.country_code, currency=payload.currency, goods_total=total,
        commission_rate=payload.commission_rate, commission_amount=commission, status="draft")
    db.add(order); db.flush()
    for line in payload.lines:
        product = db.get(m.FoodProduct, line.product_id)
        if not product: db.rollback(); raise HTTPException(404, f"الصنف غير موجود: {line.product_id}")
        if product.currency != payload.currency: db.rollback(); raise HTTPException(422, "عملة الصنف لا تطابق عملة الطلب")
        db.add(m.FoodOrderLine(order_id=order.id, product_id=line.product_id, quantity=line.quantity, unit_price=line.unit_price))
    db.commit(); db.refresh(order); return order

@app.get("/api/v1/food/orders")
def list_food_orders(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "SAWA_FOOD"))
    return db.query(m.FoodOrder).order_by(m.FoodOrder.created_at.desc()).limit(250).all()

@app.post("/api/v1/food/orders/{order_id}/fulfill")
def fulfill_food_order(order_id: str, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin", "group_manager", "business_manager", "operations"})
    ensure_unit_access(user, unit_by_code(db, "SAWA_FOOD"))
    # Serialize duplicate fulfilment and concurrent orders against the same inventory row.
    order = db.query(m.FoodOrder).filter(m.FoodOrder.id == order_id).with_for_update().first()
    if not order: raise HTTPException(404, "الطلب غير موجود")
    if order.status != "draft": raise HTTPException(409, "يمكن تنفيذ الطلبات المسودة فقط")
    lines = db.query(m.FoodOrderLine).filter_by(order_id=order.id).order_by(m.FoodOrderLine.product_id).all()
    # Brokerage never changes company-owned inventory. Direct model consumes inventory on fulfillment.
    if order.business_model == "direct":
        product_ids = sorted({line.product_id for line in lines})
        products = db.query(m.FoodProduct).filter(m.FoodProduct.id.in_(product_ids)) \
            .order_by(m.FoodProduct.id).with_for_update().all()
        products_by_id = {product.id: product for product in products}
        for line in lines:
            product = products_by_id.get(line.product_id)
            if not product:
                raise HTTPException(409, "تعذر العثور على صنف في الطلب")
            if product.stock_quantity < line.quantity:
                raise HTTPException(409, f"المخزون غير كافٍ للصنف {product.name}")
        for line in lines:
            product = products_by_id[line.product_id]
            product.stock_quantity -= line.quantity
            db.add(m.StockMovement(product_id=product.id, order_id=order.id, movement_type="out", quantity=line.quantity))
    order.status = "fulfilled"; audit(db, user, "fulfill", "food_order", order.id, {"business_model": order.business_model})
    db.commit(); db.refresh(order); return order

# Mashary Cars
@app.get("/api/v1/cars")
def list_cars(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "MASHARY_CARS"))
    return db.query(m.Car).order_by(m.Car.created_at.desc()).all()

@app.post("/api/v1/cars", status_code=201)
def create_car(payload: CarIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "MASHARY_CARS"))
    row = m.Car(**payload.model_dump()); db.add(row)
    try: db.commit(); db.refresh(row)
    except IntegrityError: db.rollback(); raise HTTPException(409, "رقم تسجيل السيارة مستخدم بالفعل")
    return row

@app.post("/api/v1/cars/maintenance", status_code=201)
def create_maintenance(payload: MaintenanceIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin", "group_manager", "business_manager", "operations"})
    ensure_unit_access(user, unit_by_code(db, "MASHARY_CARS"))
    car = db.get(m.Car, payload.car_id)
    if not car: raise HTTPException(404, "السيارة غير موجودة")
    start, end = norm_dt(payload.start_at), norm_dt(payload.end_at)
    if end <= start: raise HTTPException(422, "تاريخ نهاية الصيانة يجب أن يكون بعد بدايتها")
    row = m.CarMaintenanceBlock(car_id=car.id, start_at=start, end_at=end, reason=payload.reason)
    db.add(row); db.commit(); db.refresh(row); return row

@app.post("/api/v1/cars/bookings", status_code=201)
def create_car_booking(payload: CarBookingIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "MASHARY_CARS"))
    car = db.query(m.Car).filter(m.Car.id == payload.car_id).with_for_update().first()
    if not car: raise HTTPException(404, "السيارة غير موجودة")
    ensure_party_access(db, user, payload.party_id, unit_by_code(db, "MASHARY_CARS"))
    if car.status in {"inactive", "sold", "blocked"}: raise HTTPException(409, "السيارة غير متاحة للتأجير")
    start, end = norm_dt(payload.start_at), norm_dt(payload.end_at)
    if end <= start: raise HTTPException(422, "وقت الإرجاع يجب أن يكون بعد وقت الاستلام")
    conflict = db.query(m.CarBooking).filter(m.CarBooking.car_id == car.id,
        m.CarBooking.status.in_(["pending", "confirmed", "active"]),
        m.CarBooking.start_at < end, m.CarBooking.end_at > start).first()
    maintenance = db.query(m.CarMaintenanceBlock).filter(m.CarMaintenanceBlock.car_id == car.id,
        m.CarMaintenanceBlock.status == "scheduled", m.CarMaintenanceBlock.start_at < end,
        m.CarMaintenanceBlock.end_at > start).first()
    if conflict or maintenance: raise HTTPException(409, "السيارة محجوزة أو خاضعة للصيانة خلال الفترة المطلوبة")
    row = m.CarBooking(booking_no=new_number("MC"), car_id=car.id, party_id=payload.party_id,
        start_at=start, end_at=end, currency=payload.currency, total_amount=payload.total_amount,
        deposit_amount=payload.deposit_amount, status="pending")
    db.add(row); db.commit(); db.refresh(row); return row

@app.post("/api/v1/cars/bookings/{booking_id}/confirm")
def confirm_car_booking(booking_id: str, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin", "group_manager", "business_manager", "operations"})
    ensure_unit_access(user, unit_by_code(db, "MASHARY_CARS"))
    row = db.get(m.CarBooking, booking_id)
    if not row: raise HTTPException(404, "الحجز غير موجود")
    if row.status != "pending": raise HTTPException(409, "الحجز ليس في حالة انتظار")
    row.status = "confirmed"; db.commit(); db.refresh(row); return row

@app.get("/api/v1/cars/bookings")
def list_car_bookings(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    ensure_unit_access(user, unit_by_code(db, "MASHARY_CARS"))
    return db.query(m.CarBooking).order_by(m.CarBooking.created_at.desc()).limit(250).all()

# Private document storage; files are never served from the public static directory.
UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "./private_uploads")).resolve()
ALLOWED_FILE_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}
MAX_UPLOAD_BYTES = 3 * 1024 * 1024 if os.getenv("VERCEL") else 15 * 1024 * 1024

def validate_document_link(db, user, entity_type, entity_id, unit):
    if entity_type not in {"party", "contract"}:
        raise HTTPException(422, "نوع الربط المدعوم: party أو contract")
    model = m.Party if entity_type == "party" else m.Contract
    entity = db.get(model, entity_id)
    if not entity:
        raise HTTPException(404, "السجل المرتبط غير موجود")
    if entity_type == "party":
        if unit:
            ensure_party_access(db, user, entity_id, unit)
    elif unit is None or entity.business_unit_id != unit.id:
        raise HTTPException(403, "العقد غير مرتبط بالنشاط المحدد")


@app.get("/api/v1/documents")
def list_documents(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    query = db.query(m.Document)
    if user.role not in {"super_admin", "group_manager"}:
        query = query.filter(m.Document.business_unit_id.in_([x.business_unit_id for x in user.units]))
    return [{"id": row.id, "filename": row.original_filename, "size_bytes": row.size_bytes,
             "entity_type": row.entity_type, "entity_id": row.entity_id}
            for row in query.order_by(m.Document.created_at.desc()).limit(250)]


@app.post("/api/v1/documents", status_code=201)
def upload_document(file: UploadFile = File(...), entity_type: str = Form(...), entity_id: str = Form(...),
                          business_unit_code: str | None = Form(None), db: Session = Depends(get_db),
                          user: m.User = Depends(get_current_user)):
    unit = unit_by_code(db, business_unit_code) if business_unit_code else None
    if not unit and user.role not in {"super_admin", "group_manager"}:
        raise HTTPException(403, "يجب تحديد النشاط لرفع المستند")
    if unit: ensure_unit_access(user, unit)
    validate_document_link(db, user, entity_type, entity_id, unit)
    if file.content_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(415, "نوع الملف غير مسموح؛ الصيغ المدعومة PDF والصور وDOCX وXLSX")
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "حجم الملف أكبر من الحد المسموح")
    if not content:
        raise HTTPException(422, "الملف فارغ")
    signatures = {
        "application/pdf": content.startswith(b"%PDF"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": content.startswith(b"PK\x03\x04"),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": content.startswith(b"PK\x03\x04"),
    }
    if not signatures.get(file.content_type, False):
        raise HTTPException(415, "محتوى الملف لا يطابق نوعه المعلن")
    key = f"{uuid4().hex}.bin"
    save_document(key, content)
    digest = hashlib.sha256(content).hexdigest()
    row = m.Document(original_filename=Path((file.filename or "document").replace("\\", "/")).name, storage_key=key,
        content_type=file.content_type, size_bytes=len(content), sha256=digest, entity_type=entity_type,
        entity_id=entity_id, business_unit_id=unit.id if unit else None, uploaded_by=user.id)
    try:
        db.add(row)
        db.flush()
        audit(db, user, "upload", "document", row.id, {"entity_type": entity_type, "entity_id": entity_id})
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_document(key)
        except Exception:
            pass  # Storage lifecycle reconciliation must remove unreferenced objects.
        raise
    db.refresh(row)
    return {"id": row.id, "filename": row.original_filename, "content_type": row.content_type,
            "size_bytes": row.size_bytes, "sha256": row.sha256, "entity_type": row.entity_type, "entity_id": row.entity_id}

@app.get("/api/v1/documents/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    row = db.get(m.Document, document_id)
    if not row: raise HTTPException(404, "المستند غير موجود")
    if not row.business_unit_id and user.role not in {"super_admin", "group_manager"}:
        raise HTTPException(403, "مستند مقيد للإدارة")
    if row.business_unit_id:
        ensure_unit_access(user, db.get(m.BusinessUnit, row.business_unit_id))
    from urllib.parse import quote
    return Response(load_document(row.storage_key), media_type="application/octet-stream",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.original_filename, safe=""),
                             "Cache-Control": "no-store"})

# Tasks and audit
@app.get("/api/v1/tasks")
def list_tasks(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    query = db.query(m.Task)
    if user.role not in {"super_admin", "group_manager"}:
        query = query.filter(m.Task.business_unit_id.in_([x.business_unit_id for x in user.units]))
    return query.order_by(m.Task.due_at.asc()).limit(250).all()

@app.post("/api/v1/tasks", status_code=201)
def create_task(payload: TaskIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    unit = unit_by_code(db, payload.business_unit_code); ensure_unit_access(user, unit)
    data = payload.model_dump(exclude={"business_unit_code"})
    row = m.Task(**data, business_unit_id=unit.id)
    db.add(row); db.commit(); db.refresh(row); return row

@app.get("/api/v1/audit-logs")
def list_audit_logs(limit: int = 100, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_any_role(user, {"super_admin", "group_manager"})
    return db.query(m.AuditLog).order_by(m.AuditLog.created_at.desc()).limit(min(limit, 500)).all()

@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    return Response(content='{"detail":"تعارض في البيانات أو قيمة مكررة"}', status_code=409, media_type="application/json")

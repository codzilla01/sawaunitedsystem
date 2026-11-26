import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from .database import get_db
from .models import SessionToken, User
from .mfa import is_mfa_required

COOKIE_NAME = "sawa_session"
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-this-secret-key")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False

def session_token_hash(token: str) -> str:
    return hashlib.sha256((SECRET_KEY + token).encode()).hexdigest()

def issue_session(db: Session, user: User, *, mfa_verified: bool = False) -> str:
    token = secrets.token_urlsafe(48)
    db.add(SessionToken(user_id=user.id, token_hash=session_token_hash(token),
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
                        mfa_verified=mfa_verified))
    db.commit()
    return token

def revoke_session(db: Session, token: str | None):
    if not token:
        return
    token_hash = session_token_hash(token)
    row = db.query(SessionToken).filter(SessionToken.token_hash == token_hash).first()
    if row:
        row.revoked = True
        db.commit()

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="تسجيل الدخول مطلوب")
    token_hash = session_token_hash(token)
    session = db.query(SessionToken).filter(SessionToken.token_hash == token_hash,
                                             SessionToken.revoked.is_(False)).first()
    if not session:
        raise HTTPException(status_code=401, detail="جلسة غير صالحة")
    expiry = session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry < datetime.now(timezone.utc):
        session.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="انتهت الجلسة، سجل الدخول مجددًا")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="الحساب غير نشط")
    is_mfa_route = request.url.path.startswith("/api/v1/auth/mfa/")
    if user.mfa_enabled and not session.mfa_verified and not is_mfa_route:
        raise HTTPException(status_code=403, detail="يلزم إكمال التحقق بالمصادقة الثنائية")
    if is_mfa_required(user.role) and not user.mfa_enabled and not is_mfa_route:
        raise HTTPException(status_code=403, detail="يلزم إعداد المصادقة الثنائية قبل استخدام النظام")
    return user

def set_session_cookie(response, token: str):
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=COOKIE_SECURE,
                        samesite="lax", max_age=SESSION_TTL_HOURS * 3600, path="/")

def clear_session_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/")

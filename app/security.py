import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from .database import get_db
from .models import SessionToken, User

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

def issue_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256((SECRET_KEY + token).encode()).hexdigest()
    db.add(SessionToken(user_id=user.id, token_hash=token_hash,
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)))
    db.commit()
    return token

def revoke_session(db: Session, token: str | None):
    if not token:
        return
    token_hash = hashlib.sha256((SECRET_KEY + token).encode()).hexdigest()
    row = db.query(SessionToken).filter(SessionToken.token_hash == token_hash).first()
    if row:
        row.revoked = True
        db.commit()

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="تسجيل الدخول مطلوب")
    token_hash = hashlib.sha256((SECRET_KEY + token).encode()).hexdigest()
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
    return user

def set_session_cookie(response, token: str):
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=COOKIE_SECURE,
                        samesite="lax", max_age=SESSION_TTL_HOURS * 3600, path="/")

def clear_session_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/")

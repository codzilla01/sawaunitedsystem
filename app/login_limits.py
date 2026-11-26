"""Atomic account-based limit shared across serverless instances."""
import hashlib
import time
from fastapi import HTTPException
from sqlalchemy import delete
from .models import LoginBudget
from .production import is_production


def check_login_budget(db, email):
    if not is_production():
        return
    from sqlalchemy.dialects.postgresql import insert
    window = int(time.time()) // 900
    key = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    db.execute(delete(LoginBudget).where(LoginBudget.window < window - 1))
    stmt = insert(LoginBudget).values(key=key, window=window, attempts=1)
    stmt = stmt.on_conflict_do_update(index_elements=[LoginBudget.key, LoginBudget.window],
                                     set_={"attempts": LoginBudget.attempts + 1}).returning(LoginBudget.attempts)
    attempts = db.execute(stmt).scalar_one()
    db.commit()
    if attempts > 10:
        raise HTTPException(429, "محاولات دخول كثيرة؛ أعد المحاولة لاحقًا", headers={"Retry-After": "900"})

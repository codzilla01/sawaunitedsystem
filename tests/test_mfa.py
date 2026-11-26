from cryptography.fernet import Fernet
from datetime import datetime, timedelta, timezone
import secrets
from sqlalchemy import create_engine, inspect, text

from app.mfa import current_counter, decrypt_secret, encrypt_secret, new_secret, totp_code, verify_totp


def test_totp_matches_current_window_and_rejects_replay():
    secret = new_secret()
    counter = current_counter()
    code = totp_code(secret, counter)
    assert verify_totp(secret, code, now=counter * 30, last_counter=counter - 1) == counter
    assert verify_totp(secret, code, now=counter * 30, last_counter=counter) is None
    assert verify_totp(secret, "000000", now=counter * 30, last_counter=-1) is None


def test_mfa_secret_is_encrypted(monkeypatch):
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    secret = new_secret()
    encrypted = encrypt_secret(secret)
    assert secret not in encrypted
    assert decrypt_secret(encrypted) == secret


def test_production_admin_must_enroll_and_use_totp(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://sawa.example.com")
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.login_limits.check_login_budget", lambda db, email: None)
    headers = {"X-Sawa-Request": "1", "Origin": "https://sawa.example.com"}

    response = client.post("/api/v1/auth/login", json={
        "email": "admin@test.local", "password": "Testing!123"
    }, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["mfa_setup_required"] is True
    assert client.get("/api/v1/dashboard").status_code == 403

    setup = client.post("/api/v1/auth/mfa/setup", json={}, headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    confirm = client.post("/api/v1/auth/mfa/confirm", json={
        "code": totp_code(secret, current_counter())
    }, headers=headers)
    assert confirm.status_code == 200, confirm.text
    assert client.get("/api/v1/auth/me").status_code == 200

    client.post("/api/v1/auth/logout", json={}, headers=headers)
    next_code = totp_code(secret, current_counter() + 1)
    login = client.post("/api/v1/auth/login", json={
        "email": "admin@test.local", "password": "Testing!123", "mfa_code": next_code
    }, headers=headers)
    assert login.status_code == 200, login.text
    assert login.json()["mfa_setup_required"] is False
    assert client.get("/api/v1/auth/me").status_code == 200

    replay = client.post("/api/v1/auth/login", json={
        "email": "admin@test.local", "password": "Testing!123", "mfa_code": next_code
    }, headers=headers)
    assert replay.status_code == 401


def test_mfa_encryption_key_required_for_mfa_operations(monkeypatch):
    monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
    try:
        encrypt_secret(new_secret())
    except RuntimeError as exc:
        assert "MFA_ENCRYPTION_KEY" in str(exc)
    else:
        raise AssertionError("MFA encryption should fail closed without a key")


def test_expired_mfa_session_is_rejected(client):
    from app import models as m
    from app.database import get_db
    from app.main import app
    from app.security import COOKIE_NAME, session_token_hash

    token = secrets.token_urlsafe(32)
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        user = db.query(m.User).filter_by(email="admin@test.local").one()
        db.add(m.SessionToken(
            id="expired-mfa-session",
            user_id=user.id,
            token_hash=session_token_hash(token),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            mfa_verified=True,
        ))
        db.commit()
    finally:
        db_generator.close()
    client.cookies.set(COOKIE_NAME, token)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_legacy_sqlite_mfa_columns_added_without_data_loss(monkeypatch):
    import app.main as main

    legacy = create_engine("sqlite://")
    with legacy.begin() as connection:
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(190))"))
        connection.execute(text("CREATE TABLE session_tokens (id VARCHAR(36) PRIMARY KEY, token_hash VARCHAR(64))"))
        connection.execute(text("INSERT INTO users (id, email) VALUES ('legacy-1', 'legacy@example.test')"))
    monkeypatch.setattr(main, "engine", legacy)
    main._upgrade_local_mfa_columns()
    user_columns = {column["name"] for column in inspect(legacy).get_columns("users")}
    session_columns = {column["name"] for column in inspect(legacy).get_columns("session_tokens")}
    assert {"mfa_enabled", "mfa_secret_encrypted", "mfa_pending_secret_encrypted", "mfa_last_counter"} <= user_columns
    assert "mfa_verified" in session_columns
    with legacy.connect() as connection:
        assert connection.execute(text("SELECT email, mfa_enabled, mfa_last_counter FROM users WHERE id='legacy-1'")).one() == (
            "legacy@example.test", 0, -1
        )
    legacy.dispose()

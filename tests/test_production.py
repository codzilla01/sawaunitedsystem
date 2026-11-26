import pytest
from cryptography.fernet import Fernet
from app.production import validate_production


@pytest.fixture
def production_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "test-only-" + "x" * 60)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db/sawa")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://sawa.example.com")
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("S3_BUCKET", "private-test")
    monkeypatch.setenv("S3_REGION", "eu-west-1")
    monkeypatch.setenv("DOCUMENT_SCANNER_URL", "https://scanner.example/scan")
    monkeypatch.setenv("DOCUMENT_SCANNER_TOKEN", "test-scanner-token")


def test_valid_production_settings(production_env):
    validate_production()


@pytest.mark.parametrize("key,value", [
    ("SECRET_KEY", "short"),
    ("SECRET_KEY", "development-" + "x" * 60),
    ("DATABASE_URL", "sqlite:///production.db"),
    ("COOKIE_SECURE", "false"),
    ("PUBLIC_ORIGIN", "http://example.com"),
    ("PUBLIC_ORIGIN", "https://example.com/path"),
    ("MFA_ENCRYPTION_KEY", "invalid-key"),
    ("DOCUMENT_SCANNER_URL", "http://scanner.example/scan"),
    ("DOCUMENT_SCANNER_URL", "https://scanner.example/scan?token=secret"),
    ("S3_ENDPOINT_URL", "http://s3.example"),
    ("S3_ENDPOINT_URL", "https://s3.example?token=secret"),
])
def test_unsafe_production_settings_rejected(production_env, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        validate_production()


def test_security_headers_and_readiness(client):
    response = client.get("/ready", headers={"X-Request-ID": "uat-request-42"})
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "object-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"] == "uat-request-42"


def test_production_csrf(client, monkeypatch):
    # Switch after fixture startup, avoiding any real production database.
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://sawa.example.com")
    monkeypatch.setattr("app.login_limits.check_login_budget", lambda db, email: None)
    payload = {"email": "admin@test.local", "password": "Testing!123"}
    assert client.post("/api/v1/auth/login", json=payload).status_code == 403
    headers = {"X-Sawa-Request": "1", "Origin": "https://attacker.example"}
    assert client.post("/api/v1/auth/login", json=payload, headers=headers).status_code == 403
    headers["Origin"] = "https://sawa.example.com"
    response = client.post("/api/v1/auth/login", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "max-age=" in response.headers["strict-transport-security"]


def test_unscoped_documents_restricted(auth):
    from app.models import User
    from app.database import get_db
    from app.main import app
    factory = app.dependency_overrides[get_db]
    generator = factory()
    db = next(generator)
    user = db.query(User).filter_by(email="admin@test.local").one()
    user.role = "viewer"
    db.commit()
    generator.close()
    response = auth.post("/api/v1/documents", data={"entity_type": "party", "entity_id": "anything"},
                         files={"file": ("test.pdf", b"%PDF-test", "application/pdf")})
    assert response.status_code == 403


def test_vercel_requires_external_storage_and_tls(production_env, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="TLS"):
        validate_production()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db/sawa?sslmode=require")
    monkeypatch.delenv("S3_BUCKET")
    with pytest.raises(RuntimeError, match="S3"):
        validate_production()
    monkeypatch.setenv("S3_BUCKET", "private-test")
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "test-only")
    validate_production()

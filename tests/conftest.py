import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app, UNIT_SEEDS, COUNTRY_SEEDS
from app.models import BusinessUnit, Country, User
from app.security import hash_password

@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    for code, ar, en in UNIT_SEEDS:
        db.add(BusinessUnit(code=code, name_ar=ar, name_en=en))
    for code, ar, en, currency, tz in COUNTRY_SEEDS:
        db.add(Country(code=code, name_ar=ar, name_en=en, default_currency=currency, timezone=tz))
    db.add(User(email="admin@test.local", full_name="Test Admin", password_hash=hash_password("Testing!123"), role="super_admin"))
    db.commit(); db.close()
    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

@pytest.fixture()
def auth(client):
    r = client.post("/api/v1/auth/login", json={"email":"admin@test.local", "password":"Testing!123"})
    assert r.status_code == 200, r.text
    return client

@pytest.fixture()
def party(auth):
    r = auth.post("/api/v1/parties", json={"display_name":"عميل اختبار","party_type":"person","phone":"+20100000000","country_code":"EG"})
    assert r.status_code == 201, r.text
    return r.json()

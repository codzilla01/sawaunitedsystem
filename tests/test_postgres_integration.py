"""Real PostgreSQL tests. CI runs this file only after migrations are applied."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.database import Base
from app import models as m
from app.main import app, fulfill_food_order
from app.security import hash_password


POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="requires TEST_POSTGRES_URL after PostgreSQL migrations")


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_tables = set(Base.metadata.tables) - tables
    missing_columns = {}
    for table_name, table in Base.metadata.tables.items():
        if table_name in tables:
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            absent = {column.name for column in table.columns} - actual
            if absent:
                missing_columns[table_name] = sorted(absent)
    assert not missing_tables and not missing_columns, (
        f"Migrations are incomplete: tables={sorted(missing_tables)}, columns={missing_columns}"
    )
    with engine.connect() as connection:
        constraints = set(connection.execute(text(
            "SELECT conname FROM pg_constraint WHERE conname IN "
            "('property_reservations_no_overlap','car_bookings_no_overlap')"
        )).scalars())
        assert constraints == {"property_reservations_no_overlap", "car_bookings_no_overlap"}
        extensions = set(connection.execute(text("SELECT extname FROM pg_extension")).scalars())
        assert "btree_gist" in extensions
    yield engine
    engine.dispose()


def _new_test_data(engine):
    marker = uuid4().hex[:12]
    with Session(engine) as db, db.begin():
        if not db.get(m.Country, "EG"):
            db.add(m.Country(code="EG", name_ar="مصر", name_en="Egypt", default_currency="EGP", timezone="Africa/Cairo"))
            db.flush()
        units = {}
        for code, name in (("REAL_ESTATE", "Real Estate"), ("SAWA_FOOD", "Sawa Food"), ("MASHARY_CARS", "Mashary Cars")):
            unit = db.query(m.BusinessUnit).filter_by(code=code).first()
            if not unit:
                unit = m.BusinessUnit(code=code, name_ar=name, name_en=name)
                db.add(unit)
                db.flush()
            units[code] = unit
        party = m.Party(display_name=f"PG integration {marker}", party_type="company", country_code="EG")
        user = m.User(email=f"pg-{marker}@test.example", full_name="PG Integration", password_hash=hash_password("Test-only-password-123!"), role="super_admin")
        db.add_all([party, user])
        db.flush()
        project = m.RealEstateProject(name=f"PG project {marker}", country_code="EG", city="Cairo")
        db.add(project)
        db.flush()
        unit = m.PropertyUnit(project_id=project.id, unit_code=f"PG-{marker}", price=Decimal("100000"), currency="EGP")
        car = m.Car(registration_no=f"PG-{marker}", make="Test", model="Model", country_code="EG", city="Cairo", daily_rate=Decimal("100"), currency="EGP")
        product = m.FoodProduct(sku=f"PG-{marker}", name="Concurrent stock", stock_quantity=Decimal("5"), reorder_level=Decimal("0"), currency="EGP")
        db.add_all([unit, car, product])
        db.flush()
        return {"marker": marker, "party_id": party.id, "admin_id": user.id,
                "property_unit_id": unit.id, "car_id": car.id, "product_id": product.id,
                "business_unit_ids": {code: row.id for code, row in units.items()}}


def _race_two_inserts(engine, model, field_values):
    barrier = Barrier(2)

    def insert_one(suffix):
        with Session(engine) as db:
            try:
                barrier.wait(timeout=10)
                db.add(model(**field_values(suffix)))
                db.commit()
                return "accepted"
            except IntegrityError:
                db.rollback()
                return "conflict"
            except OperationalError as exc:
                db.rollback()
                # Concurrent PostgreSQL GiST exclusion checks can deadlock even
                # though one insert is safely aborted. Treat only SQLSTATE 40P01
                # as a conflict; surface all other database failures.
                if getattr(exc.orig, "sqlstate", None) == "40P01":
                    return "conflict"
                raise
            finally:
                db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(insert_one, ("a", "b")))


def test_postgresql_migrations_and_temporal_constraints(pg_engine):
    # The module fixture verifies every ORM table/column and both exclusion constraints.
    assert "session_tokens" in inspect(pg_engine).get_table_names()
    assert {"mfa_verified"} <= {c["name"] for c in inspect(pg_engine).get_columns("session_tokens")}


def test_postgresql_concurrent_property_reservations_are_serialized(pg_engine):
    data = _new_test_data(pg_engine)
    start = datetime.now(timezone.utc) + timedelta(days=20)
    end = start + timedelta(days=3)
    outcomes = _race_two_inserts(pg_engine, m.PropertyReservation, lambda suffix: {
        "unit_id": data["property_unit_id"], "party_id": data["party_id"],
        "start_at": start, "expires_at": end, "deposit_amount": Decimal("0"), "currency": "EGP",
    })
    assert sorted(outcomes) == ["accepted", "conflict"]
    with Session(pg_engine) as db:
        assert db.query(m.PropertyReservation).filter_by(unit_id=data["property_unit_id"]).count() == 1


def test_postgresql_concurrent_car_bookings_are_serialized(pg_engine):
    data = _new_test_data(pg_engine)
    start = datetime.now(timezone.utc) + timedelta(days=30)
    end = start + timedelta(days=2)
    outcomes = _race_two_inserts(pg_engine, m.CarBooking, lambda suffix: {
        "booking_no": f"PG-{data['marker']}-{suffix}", "car_id": data["car_id"],
        "party_id": data["party_id"], "start_at": start, "end_at": end,
        "currency": "EGP", "total_amount": Decimal("200"), "deposit_amount": Decimal("0"),
    })
    assert sorted(outcomes) == ["accepted", "conflict"]
    with Session(pg_engine) as db:
        assert db.query(m.CarBooking).filter_by(car_id=data["car_id"]).count() == 1


def test_postgresql_concurrent_food_fulfilment_cannot_oversell(pg_engine):
    data = _new_test_data(pg_engine)
    order_ids = []
    with Session(pg_engine) as db, db.begin():
        for suffix in ("a", "b"):
            order = m.FoodOrder(order_no=f"PG-{data['marker']}-{suffix}", business_model="direct",
                customer_party_id=data["party_id"], country_code="EG", currency="EGP",
                goods_total=Decimal("400"), commission_rate=Decimal("0"), commission_amount=Decimal("0"), status="draft")
            db.add(order)
            db.flush()
            db.add(m.FoodOrderLine(order_id=order.id, product_id=data["product_id"], quantity=Decimal("4"), unit_price=Decimal("100")))
            order_ids.append(order.id)

    barrier = Barrier(2)

    def fulfill(order_id):
        with Session(pg_engine) as db:
            try:
                barrier.wait(timeout=10)
                admin = db.get(m.User, data["admin_id"])
                order = fulfill_food_order(order_id, db, admin)
                return order.status
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
            finally:
                db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(fulfill, order_ids))
    assert sorted(map(str, outcomes)) == ["409", "fulfilled"]
    with Session(pg_engine) as db:
        product = db.get(m.FoodProduct, data["product_id"])
        movements = db.query(m.StockMovement).filter_by(product_id=data["product_id"]).count()
        assert product.stock_quantity == Decimal("1.000")
        assert movements == 1


def test_postgresql_api_enforces_business_unit_scope(pg_engine, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    admin_email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@ci.example")
    admin_password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "ci-only-bootstrap-password-long")
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"email": admin_email, "password": admin_password})
        assert login.status_code == 200, login.text
        created = client.post("/api/v1/users", json={
            "email": f"scope-{uuid4().hex[:10]}@test.example",
            "full_name": "Scoped PostgreSQL User",
            "password": "Scoped-test-password-123!",
            "role": "sales",
            "business_unit_codes": ["SAWA_FOOD"],
        })
        assert created.status_code == 201, created.text
        client.post("/api/v1/auth/logout", json={})
        user_login = client.post("/api/v1/auth/login", json={
            "email": created.json()["email"], "password": "Scoped-test-password-123!"
        })
        assert user_login.status_code == 200, user_login.text
        assert client.get("/api/v1/food/products").status_code == 200
        assert client.get("/api/v1/real-estate/projects").status_code == 403

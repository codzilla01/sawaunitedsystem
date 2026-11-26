from __future__ import annotations
from datetime import datetime, timezone, date
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Numeric, Integer, Text, Date, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def uid() -> str:
    return str(uuid4())
def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class BusinessUnit(Base, TimestampMixin):
    __tablename__ = "business_units"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class Country(Base, TimestampMixin):
    __tablename__ = "countries"
    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="UTC", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="sales", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(500))
    mfa_pending_secret_encrypted: Mapped[str | None] = mapped_column(String(500))
    mfa_last_counter: Mapped[int] = mapped_column(Integer, default=-1, nullable=False)
    units: Mapped[list[UserBusinessUnit]] = relationship(back_populates="user", cascade="all, delete-orphan")

class UserBusinessUnit(Base):
    __tablename__ = "user_business_units"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), primary_key=True)
    user: Mapped[User] = relationship(back_populates="units")

class SessionToken(Base):
    __tablename__ = "session_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Party(Base, TimestampMixin):
    __tablename__ = "parties"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    party_type: Mapped[str] = mapped_column(String(20), default="person", nullable=False) # person/company
    display_name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(190), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))
    city: Mapped[str | None] = mapped_column(String(100))
    roles: Mapped[str] = mapped_column(String(300), default="customer", nullable=False) # comma-separated categories in MVP
    tax_number: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    units: Mapped[list[PartyBusinessUnit]] = relationship(back_populates="party", cascade="all, delete-orphan")

class PartyBusinessUnit(Base):
    __tablename__ = "party_business_units"
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True)
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), primary_key=True)
    party: Mapped[Party] = relationship(back_populates="units")

class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    party_id: Mapped[str | None] = mapped_column(ForeignKey("parties.id"), index=True)
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), index=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    source: Mapped[str] = mapped_column(String(60), default="manual")
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="new", nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)

class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), index=True)
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), index=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), default="qualified", nullable=False)
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    currency: Mapped[str] = mapped_column(String(3), default="EGP", nullable=False)
    probability: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)

class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    contract_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), index=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), index=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))
    contract_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0.00"), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    previous_version_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"))
    terms: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

class Installment(Base, TimestampMixin):
    __tablename__ = "installments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    description: Mapped[str] = mapped_column(String(160), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="due", nullable=False)

class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    direction: Mapped[str] = mapped_column(String(10), default="receipt", nullable=False) # receipt/payment
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), index=True)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    installment_id: Mapped[str | None] = mapped_column(ForeignKey("installments.id"))
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), index=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(30), default="bank_transfer")
    reference: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="posted", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

class RealEstateProject(Base, TimestampMixin):
    __tablename__ = "real_estate_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    developer_party_id: Mapped[str | None] = mapped_column(ForeignKey("parties.id"))
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str | None] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(30), default="active")
    notes: Mapped[str | None] = mapped_column(Text)

class PropertyUnit(Base, TimestampMixin):
    __tablename__ = "property_units"
    __table_args__ = (UniqueConstraint("project_id", "unit_code", name="uq_property_project_unit"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("real_estate_projects.id", ondelete="CASCADE"), index=True)
    unit_code: Mapped[str] = mapped_column(String(60), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(40), default="apartment")
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10,2))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False)

class PropertyReservation(Base, TimestampMixin):
    __tablename__ = "property_reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    unit_id: Mapped[str] = mapped_column(ForeignKey("property_units.id"), index=True)
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), index=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0.00"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

class FoodProduct(Base, TimestampMixin):
    __tablename__ = "food_products"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    sku: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(30), default="piece")
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(14,3), default=Decimal("0"), nullable=False)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(14,3), default=Decimal("0"), nullable=False)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    currency: Mapped[str] = mapped_column(String(3), default="EGP", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class FoodOrder(Base, TimestampMixin):
    __tablename__ = "food_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    business_model: Mapped[str] = mapped_column(String(20), nullable=False) # direct/brokerage
    customer_party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), index=True)
    supplier_party_id: Mapped[str | None] = mapped_column(ForeignKey("parties.id"))
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    goods_total: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0"), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(7,4), default=Decimal("0"), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0"), nullable=False)

class FoodOrderLine(Base):
    __tablename__ = "food_order_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("food_orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("food_products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14,3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)

class StockMovement(Base, TimestampMixin):
    __tablename__ = "stock_movements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    product_id: Mapped[str] = mapped_column(ForeignKey("food_products.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("food_orders.id"))
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14,3), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))

class Car(Base, TimestampMixin):
    __tablename__ = "cars"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    registration_no: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    make: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    model_year: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(40), default="sedan")
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False)
    odometer_km: Mapped[int] = mapped_column(Integer, default=0)

class CarBooking(Base, TimestampMixin):
    __tablename__ = "car_bookings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    car_id: Mapped[str] = mapped_column(ForeignKey("cars.id"), index=True)
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

class CarMaintenanceBlock(Base, TimestampMixin):
    __tablename__ = "car_maintenance_blocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    car_id: Mapped[str] = mapped_column(ForeignKey("cars.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")

class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), index=True)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    related_type: Mapped[str | None] = mapped_column(String(40))
    related_id: Mapped[str | None] = mapped_column(String(36))

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

Index("ix_opportunity_unit_stage", Opportunity.business_unit_id, Opportunity.stage)
Index("ix_contract_unit_status", Contract.business_unit_id, Contract.status)
Index("ix_reservation_unit_period", PropertyReservation.unit_id, PropertyReservation.start_at, PropertyReservation.expires_at)
Index("ix_car_booking_period", CarBooking.car_id, CarBooking.start_at, CarBooking.end_at)

class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    business_unit_id: Mapped[str | None] = mapped_column(ForeignKey("business_units.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

class LoginBudget(Base):
    __tablename__ = "login_budgets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)

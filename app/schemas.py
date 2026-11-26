from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class LoginIn(BaseModel):
    email: str
    password: str

class PartyIn(BaseModel):
    party_type: str = "person"
    display_name: str = Field(min_length=2, max_length=180)
    legal_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country_code: str | None = None
    city: str | None = None
    roles: str = "customer"
    business_unit_codes: list[str] = []
    notes: str | None = None

class LeadIn(BaseModel):
    party_id: str | None = None
    business_unit_code: str
    country_code: str
    source: str = "manual"
    subject: str
    assigned_to: str | None = None
    notes: str | None = None

class OpportunityIn(BaseModel):
    party_id: str
    business_unit_code: str
    country_code: str
    lead_id: str | None = None
    title: str
    expected_value: Decimal | None = None
    currency: str = "EGP"
    probability: int = Field(default=20, ge=0, le=100)
    notes: str | None = None

class ContractIn(BaseModel):
    contract_no: str
    title: str
    business_unit_code: str
    country_code: str
    party_id: str
    opportunity_id: str | None = None
    contract_type: str
    currency: str
    total_value: Decimal = Field(ge=0)
    start_date: date | None = None
    end_date: date | None = None
    terms: str | None = None

class PaymentIn(BaseModel):
    direction: str = "receipt"
    party_id: str
    contract_id: str | None = None
    installment_id: str | None = None
    business_unit_code: str
    country_code: str
    amount: Decimal = Field(gt=0)
    currency: str
    method: str = "bank_transfer"
    reference: str | None = None
    notes: str | None = None

class ProjectIn(BaseModel):
    name: str
    developer_party_id: str | None = None
    country_code: str
    city: str
    address: str | None = None
    notes: str | None = None

class PropertyUnitIn(BaseModel):
    unit_code: str
    unit_type: str = "apartment"
    area_sqm: Decimal | None = None
    bedrooms: int | None = None
    price: Decimal = Field(gt=0)
    currency: str

class PropertyReservationIn(BaseModel):
    unit_id: str
    party_id: str
    start_at: datetime
    expires_at: datetime
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str

class FoodProductIn(BaseModel):
    sku: str
    name: str
    brand: str | None = None
    unit: str = "piece"
    stock_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)
    cost_price: Decimal | None = None
    sale_price: Decimal | None = None
    currency: str = "EGP"

class FoodLineIn(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)

class FoodOrderIn(BaseModel):
    business_model: str # direct / brokerage
    customer_party_id: str
    supplier_party_id: str | None = None
    country_code: str
    currency: str
    commission_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    lines: list[FoodLineIn] = Field(min_length=1)

class CarIn(BaseModel):
    registration_no: str
    make: str
    model: str
    model_year: int | None = None
    category: str = "sedan"
    country_code: str
    city: str
    daily_rate: Decimal = Field(gt=0)
    currency: str
    odometer_km: int = Field(default=0, ge=0)

class CarBookingIn(BaseModel):
    car_id: str
    party_id: str
    start_at: datetime
    end_at: datetime
    currency: str
    total_amount: Decimal = Field(gt=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)

class MaintenanceIn(BaseModel):
    car_id: str
    start_at: datetime
    end_at: datetime
    reason: str

class TaskIn(BaseModel):
    title: str
    business_unit_code: str
    assigned_to: str | None = None
    due_at: datetime | None = None
    priority: str = "normal"
    related_type: str | None = None
    related_id: str | None = None

class UserIn(BaseModel):
    email: str
    full_name: str
    password: str = Field(min_length=12)
    role: str
    business_unit_codes: list[str] = []


class CountryIn(BaseModel):
    code: str = Field(min_length=2, max_length=2)
    name_ar: str
    name_en: str
    default_currency: str = Field(min_length=3, max_length=3)
    timezone: str = "UTC"

class BusinessUnitIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name_ar: str
    name_en: str

class PasswordResetIn(BaseModel):
    password: str = Field(min_length=12)

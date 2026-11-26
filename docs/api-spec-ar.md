# REST API Specification — SAWA UNITED BMS

**Base URL:** `/api/v1`  
**Authentication:** session cookie `sawa_session` (HttpOnly)  
**Format:** JSON (`multipart/form-data` for document upload)  
**Interactive spec:** `/docs` · Exported file: `openapi.json`

## 1. Conventions

- IDs are UUID strings.
- Timestamps accept ISO-8601; API stores normalized UTC.
- Dates use `YYYY-MM-DD`.
- Money values are decimal strings/numbers plus separate ISO currency code.
- List endpoints in MVP cap results at 250; cursor pagination is required before production scaling.
- Unauthorized `401`; scope/role failure `403`; missing entity `404`; validation `422`; state conflict/duplicate/overlap `409`.
- All write calls are authenticated. No public create endpoint is exposed in the current build.

## 2. Authentication and reference data

| Method | Path | Purpose | Access |
|---|---|---|---|
| POST | `/auth/login` | Login and issue HttpOnly session cookie | Public |
| POST | `/auth/logout` | Revoke current session | Authenticated |
| GET | `/auth/me` | Current user and scope | Authenticated |
| GET | `/reference/business-units` | List visible activities | Authenticated |
| POST | `/reference/business-units` | Add brand/business unit | Super Admin |
| GET | `/reference/countries` | List enabled countries | Authenticated |
| POST | `/reference/countries` | Add country/currency/timezone | Super Admin |
| GET | `/users` | User directory without credential hashes | Super Admin / Group Manager |
| POST | `/users` | Create scoped user | Super Admin |
| POST | `/users/{id}/reset-password` | Reset password and revoke sessions | Super Admin |
| POST | `/users/{id}/deactivate` | Deactivate account and revoke sessions | Super Admin |
| GET | `/dashboard` | Aggregated accessible KPIs | Authenticated |

### Example login

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email":"admin@example.com","password":"<secure-password>"}
```

Successful response includes `id`, `email`, `full_name`, `role`; session is set as an HttpOnly cookie. Passwords are never returned.

## 3. CRM and Sales

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/parties?q=` | Search accessible parties | Scope-filtered by linked business units |
| POST | `/parties` | Create person/company | Scoped users must supply `business_unit_codes` |
| GET | `/leads?business_unit_code=` | List leads | Unit scope enforced |
| POST | `/leads` | Create lead | Requires activity and country |
| GET | `/opportunities?business_unit_code=` | List opportunities | Unit scope enforced |
| POST | `/opportunities` | Create opportunity | Customer must be accessible in selected activity |

### Example party

```json
{
  "party_type": "company",
  "display_name": "Example Distribution Co.",
  "email": "sales@example.test",
  "phone": "+201000000000",
  "country_code": "EG",
  "city": "Cairo",
  "roles": "customer,supplier",
  "business_unit_codes": ["SAWA_FOOD"]
}
```

### Example opportunity

```json
{
  "party_id": "<party-uuid>",
  "business_unit_code": "REAL_ESTATE",
  "country_code": "EG",
  "title": "Buyer inquiry — Project A",
  "expected_value": "2500000.00",
  "currency": "EGP",
  "probability": 45
}
```

## 4. Contracts and Finance

| Method | Path | Purpose | Access |
|---|---|---|---|
| GET | `/contracts?business_unit_code=` | List contracts | Scoped |
| POST | `/contracts` | Create draft contract | Scoped |
| POST | `/contracts/{id}/transition?new_status=` | Transition contract status | Higher privilege for approval/signature/activation |
| GET | `/finance/payments?business_unit_code=` | List payments | Scoped |
| POST | `/finance/payments` | Record receipt/payment | Accountant / Business Manager / Group Manager / Super Admin |

### Contract status graph

`draft → review → approved → sent → signed → active → expired/terminated`.

Invalid transitions return 409. `approved`, `signed`, `active`, and `terminated` require an elevated role. A signed contract's binary file must not be overwritten; a contract amendment/version API is still a planned enhancement.

### Payment validation

If `contract_id` is supplied, the payment currency must equal the contract currency. The current MVP does not yet provide allocation across multiple installments, refunds/reversals, bank reconciliation, or FX conversion.

## 5. Real Estate

| Method | Path | Purpose |
|---|---|---|
| GET | `/real-estate/projects` | List projects |
| POST | `/real-estate/projects` | Create project |
| GET | `/real-estate/projects/{project_id}/units` | List project units |
| POST | `/real-estate/projects/{project_id}/units` | Add unit |
| GET | `/real-estate/units` | List all visible units |
| GET | `/real-estate/reservations` | List reservations |
| POST | `/real-estate/reservations` | Create temporary reservation |
| POST | `/real-estate/reservations/{id}/cancel` | Cancel active reservation |

A reservation body includes `unit_id`, `party_id`, `start_at`, `expires_at`, `deposit_amount`, `currency`. An overlapping pending/confirmed reservation or a sold/blocked unit returns 409.

## 6. Sawa Food

| Method | Path | Purpose |
|---|---|---|
| GET | `/food/products` | Product catalog and current owned stock |
| POST | `/food/products` | Add SKU/product |
| GET | `/food/orders` | List orders |
| POST | `/food/orders` | Create draft direct or brokerage order |
| POST | `/food/orders/{id}/fulfill` | Fulfill a draft order |

Order body:

```json
{
  "business_model": "brokerage",
  "customer_party_id": "<customer-uuid>",
  "supplier_party_id": "<supplier-uuid>",
  "country_code": "EG",
  "currency": "EGP",
  "commission_rate": "5.00",
  "lines": [{"product_id":"<sku-uuid>","quantity":"10.000","unit_price":"125.00"}]
}
```

`direct` fulfillment checks and decreases owned stock, creating stock movement. `brokerage` requires a supplier and records fee/commission without stock decrement.

## 7. Mashary Cars

| Method | Path | Purpose |
|---|---|---|
| GET | `/cars` | Fleet list |
| POST | `/cars` | Register company-owned vehicle |
| POST | `/cars/maintenance` | Create maintenance block |
| GET | `/cars/bookings` | List bookings |
| POST | `/cars/bookings` | Request booking |
| POST | `/cars/bookings/{id}/confirm` | Confirm pending booking |

A booking includes car/customer, start/end timestamps, currency, total, and deposit. Overlap with pending/confirmed/active bookings or scheduled maintenance returns 409.

## 8. Tasks, documents, and audit

| Method | Path | Purpose | Access |
|---|---|---|---|
| GET | `/tasks` | List in-scope tasks | Scoped |
| POST | `/tasks` | Create task | Scoped |
| POST | `/documents` | Upload private file | Authenticated + scope |
| GET | `/documents/{id}/download` | Download private file | Authenticated + scope |
| GET | `/audit-logs?limit=100` | Inspect audit history | Super Admin / Group Manager |

Document upload uses multipart fields: `file`, `entity_type`, `entity_id`, optional `business_unit_code`. Allowed formats: PDF, JPEG, PNG, WEBP, DOCX, XLSX. Maximum size: 15 MB. On Vercel the limit is 3 MiB; production uses private S3 storage and requires a trusted HTTPS malware scanner. Supported entity types are party and contract and the referenced record must exist. GET /documents returns scoped metadata.

## 9. Error example

```json
{"detail":"السيارة محجوزة أو خاضعة للصيانة خلال الفترة المطلوبة"}
```

## 10. Integration readiness

The current API is first-party and does not yet expose completed Meta/TikTok/WhatsApp webhooks or outbound integrations. Before enabling a provider, implement provider signature verification, idempotency keys, retry queue, consent policy, connection status, and secrets management. Never store provider secrets in source code.

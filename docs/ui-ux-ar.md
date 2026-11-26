# UI/UX Specification — SAWA UNITED

## 1. Design language

- Desktop-first management workspace with fully responsive tablet/mobile behavior.
- Arabic RTL is the default; components are structured so EN/LTR can be added without rebuilding page layout.
- Dark operational interface: navy background, layered panels, restrained blue/cyan accent, green success and amber pending states.
- Typography: Cairo with system fallback.
- Navigation: persistent right-to-left sidebar on desktop; horizontal scrollable module navigation on mobile.
- Forms use explicit labels, validation, status feedback, and clear action buttons.
- Tables are searchable and horizontally scrollable on smaller screens.

## 2. Navigation and screens

| Screen | Main purpose | Primary actions |
|---|---|---|
| Login | Secure employee access | Sign in |
| Executive Dashboard | Group-wide KPI snapshot | Open business module |
| Parties | Unified customer/supplier/developer records | Add party; link to activities |
| Leads | Initial inquiries | Create lead; assign activity/country/source |
| Opportunities | Sales pipeline records | Create opportunity; track stage/value/probability |
| Contracts | Contract register | Create draft; progress through approval/signature lifecycle |
| Real Estate | Projects, units, reservations | Add project; add unit; reserve/cancel unit |
| Sawa Food | Product catalog, orders | Add SKU; direct/brokerage order; fulfill |
| Mashary Cars | Owned fleet, bookings | Add car; request/confirm booking |
| Finance | Operational receipts/payments | Record transaction; filter by activity/currency |
| Tasks | Team follow-up | Create assigned task and due date |
| Users & Permissions | Account and role setup | Create scoped user; reset password/deactivate via API |

## 3. Core interaction patterns

### Dashboard

- Four top KPI cards: total parties, available fleet, active food SKUs, open tasks.
- Business-unit table with leads, opportunities, and contracts.
- KPIs are counts in MVP; revenue/profit/collection metrics wait for complete financial definitions.

### Customer record

- Record type: individual/company.
- Contact details and country/city.
- Role tags (customer, supplier, developer, etc.).
- Activity association checkboxes. Restricted users must associate each new party to an activity they can access.
- Notes and a single searchable list.

### Contract workflow

- A contract starts as Draft.
- Status dropdown offers only valid next transitions.
- API enforces elevated roles for approvals, signatures, and activation; frontend does not replace authorization.
- A production-ready contract detail page should add parties, obligations, payment schedule, file versions, reviewers, signatures, and amendment timeline.

### Real estate

1. Create project.
2. Add one or more units with unique project/unit code.
3. Create a temporary reservation using a client and period.
4. View current projects, inventory, and reservations.
5. Cancellation releases a reserved unit if no other active reservation remains.

### Sawa Food

- Product catalog indicates owned stock quantity/reorder level.
- Direct/brokerage is selected for every order.
- Direct fulfillment can fail when stock is insufficient.
- Brokerage fulfillment never changes owned stock.

### Mashary Cars

- Register company-owned car and daily rate.
- Create booking with start/end and customer.
- Confirm a pending booking only after review.
- API rejects overlaps with other active bookings or scheduled maintenance.

## 4. Responsive behavior

- Desktop: sidebar 258 px; forms three columns; four KPI cards.
- Tablet: sidebar 220 px; dashboard panels stack; two-column metrics.
- Mobile: top-level module navigation scrolls horizontally; forms collapse to one/two columns; data tables scroll horizontally.

## 5. Accessibility and usability

- Use labels and semantic form controls.
- Keyboard focus state visible on fields/buttons.
- Error messages appear near forms and as toast feedback.
- Status labels use text in addition to color.
- Production follow-up: add table pagination, accessible modal patterns, explicit focus management, screen-reader testing, and EN/LTR plus French language bundles.

## 6. Wireframe map

```text
┌─────────────────────────────────────────────────────────────────┐
│ SAWA UNITED / CURRENT PAGE                 ONLINE     USER MENU  │
├──────────────┬──────────────────────────────────────────────────┤
│ BRAND        │ PAGE TITLE + DESCRIPTION            PRIMARY CTA  │
│              ├──────────────────────────────────────────────────┤
│ Dashboard    │ KPI 01      KPI 02      KPI 03      KPI 04         │
│ Customers    ├────────────────────────────┬─────────────────────┤
│ Leads        │ BUSINESS UNIT SUMMARY      │ OPERATIONS SNAPSHOT │
│ Opportunities│                            │                     │
│ Contracts    ├────────────────────────────┴─────────────────────┤
│ Real Estate  │ FORM CARD / FILTER BAR / SEARCH                  │
│ Sawa Food    ├──────────────────────────────────────────────────┤
│ Cars         │ DATA TABLE / STATUS / ACTION                     │
│ Finance      │                                                  │
│ Tasks        │                                                  │
│ Users        │                                                  │
└──────────────┴──────────────────────────────────────────────────┘
```

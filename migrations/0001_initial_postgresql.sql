-- Initial PostgreSQL schema generated from SQLAlchemy metadata. Review before production use.

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE business_units (
	id VARCHAR(36) NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	name_ar VARCHAR(120) NOT NULL, 
	name_en VARCHAR(120) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE countries (
	code VARCHAR(2) NOT NULL, 
	name_ar VARCHAR(100) NOT NULL, 
	name_en VARCHAR(100) NOT NULL, 
	default_currency VARCHAR(3) NOT NULL, 
	timezone VARCHAR(60) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (code)
);

CREATE TABLE food_products (
	id VARCHAR(36) NOT NULL, 
	sku VARCHAR(60) NOT NULL, 
	name VARCHAR(180) NOT NULL, 
	brand VARCHAR(120), 
	unit VARCHAR(30) NOT NULL, 
	stock_quantity NUMERIC(14, 3) NOT NULL, 
	reorder_level NUMERIC(14, 3) NOT NULL, 
	cost_price NUMERIC(18, 2), 
	sale_price NUMERIC(18, 2), 
	currency VARCHAR(3) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (sku)
);

CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	email VARCHAR(190) NOT NULL, 
	full_name VARCHAR(160) NOT NULL, 
	password_hash VARCHAR(300) NOT NULL, 
	role VARCHAR(40) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE audit_logs (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36), 
	action VARCHAR(80) NOT NULL, 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(36), 
	details TEXT, 
	ip_address VARCHAR(60), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE cars (
	id VARCHAR(36) NOT NULL, 
	registration_no VARCHAR(60) NOT NULL, 
	make VARCHAR(80) NOT NULL, 
	model VARCHAR(80) NOT NULL, 
	model_year INTEGER, 
	category VARCHAR(40) NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	city VARCHAR(100) NOT NULL, 
	daily_rate NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	odometer_km INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (registration_no), 
	FOREIGN KEY(country_code) REFERENCES countries (code)
);

CREATE TABLE documents (
	id VARCHAR(36) NOT NULL, 
	original_filename VARCHAR(255) NOT NULL, 
	storage_key VARCHAR(100) NOT NULL, 
	content_type VARCHAR(120) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	business_unit_id VARCHAR(36), 
	uploaded_by VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (storage_key), 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id), 
	FOREIGN KEY(uploaded_by) REFERENCES users (id)
);

CREATE TABLE parties (
	id VARCHAR(36) NOT NULL, 
	party_type VARCHAR(20) NOT NULL, 
	display_name VARCHAR(180) NOT NULL, 
	legal_name VARCHAR(200), 
	email VARCHAR(190), 
	phone VARCHAR(40), 
	country_code VARCHAR(2), 
	city VARCHAR(100), 
	roles VARCHAR(300) NOT NULL, 
	tax_number VARCHAR(100), 
	notes TEXT, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(country_code) REFERENCES countries (code)
);

CREATE TABLE session_tokens (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	UNIQUE (token_hash)
);

CREATE TABLE tasks (
	id VARCHAR(36) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	business_unit_id VARCHAR(36) NOT NULL, 
	assigned_to VARCHAR(36), 
	due_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	priority VARCHAR(20) NOT NULL, 
	related_type VARCHAR(40), 
	related_id VARCHAR(36), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id), 
	FOREIGN KEY(assigned_to) REFERENCES users (id)
);

CREATE TABLE user_business_units (
	user_id VARCHAR(36) NOT NULL, 
	business_unit_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (user_id, business_unit_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id)
);

CREATE TABLE car_bookings (
	id VARCHAR(36) NOT NULL, 
	booking_no VARCHAR(50) NOT NULL, 
	car_id VARCHAR(36) NOT NULL, 
	party_id VARCHAR(36) NOT NULL, 
	start_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	end_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	total_amount NUMERIC(18, 2) NOT NULL, 
	deposit_amount NUMERIC(18, 2) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (booking_no), 
	FOREIGN KEY(car_id) REFERENCES cars (id), 
	FOREIGN KEY(party_id) REFERENCES parties (id)
);

CREATE TABLE car_maintenance_blocks (
	id VARCHAR(36) NOT NULL, 
	car_id VARCHAR(36) NOT NULL, 
	start_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	end_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reason VARCHAR(200) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(car_id) REFERENCES cars (id)
);

CREATE TABLE food_orders (
	id VARCHAR(36) NOT NULL, 
	order_no VARCHAR(50) NOT NULL, 
	business_model VARCHAR(20) NOT NULL, 
	customer_party_id VARCHAR(36) NOT NULL, 
	supplier_party_id VARCHAR(36), 
	country_code VARCHAR(2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	goods_total NUMERIC(18, 2) NOT NULL, 
	commission_rate NUMERIC(7, 4) NOT NULL, 
	commission_amount NUMERIC(18, 2) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (order_no), 
	FOREIGN KEY(customer_party_id) REFERENCES parties (id), 
	FOREIGN KEY(supplier_party_id) REFERENCES parties (id), 
	FOREIGN KEY(country_code) REFERENCES countries (code)
);

CREATE TABLE leads (
	id VARCHAR(36) NOT NULL, 
	party_id VARCHAR(36), 
	business_unit_id VARCHAR(36) NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	source VARCHAR(60) NOT NULL, 
	subject VARCHAR(200) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	assigned_to VARCHAR(36), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(party_id) REFERENCES parties (id), 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id), 
	FOREIGN KEY(country_code) REFERENCES countries (code), 
	FOREIGN KEY(assigned_to) REFERENCES users (id)
);

CREATE TABLE party_business_units (
	party_id VARCHAR(36) NOT NULL, 
	business_unit_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (party_id, business_unit_id), 
	FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE CASCADE, 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id)
);

CREATE TABLE real_estate_projects (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(180) NOT NULL, 
	developer_party_id VARCHAR(36), 
	country_code VARCHAR(2) NOT NULL, 
	city VARCHAR(100) NOT NULL, 
	address VARCHAR(250), 
	status VARCHAR(30) NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(developer_party_id) REFERENCES parties (id), 
	FOREIGN KEY(country_code) REFERENCES countries (code)
);

CREATE TABLE food_order_lines (
	id VARCHAR(36) NOT NULL, 
	order_id VARCHAR(36) NOT NULL, 
	product_id VARCHAR(36) NOT NULL, 
	quantity NUMERIC(14, 3) NOT NULL, 
	unit_price NUMERIC(18, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES food_orders (id) ON DELETE CASCADE, 
	FOREIGN KEY(product_id) REFERENCES food_products (id)
);

CREATE TABLE opportunities (
	id VARCHAR(36) NOT NULL, 
	party_id VARCHAR(36) NOT NULL, 
	business_unit_id VARCHAR(36) NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	lead_id VARCHAR(36), 
	title VARCHAR(200) NOT NULL, 
	stage VARCHAR(30) NOT NULL, 
	expected_value NUMERIC(18, 2), 
	currency VARCHAR(3) NOT NULL, 
	probability INTEGER NOT NULL, 
	owner_id VARCHAR(36), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(party_id) REFERENCES parties (id), 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id), 
	FOREIGN KEY(country_code) REFERENCES countries (code), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE property_units (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	unit_code VARCHAR(60) NOT NULL, 
	unit_type VARCHAR(40) NOT NULL, 
	area_sqm NUMERIC(10, 2), 
	bedrooms INTEGER, 
	price NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_property_project_unit UNIQUE (project_id, unit_code), 
	FOREIGN KEY(project_id) REFERENCES real_estate_projects (id) ON DELETE CASCADE
);

CREATE TABLE stock_movements (
	id VARCHAR(36) NOT NULL, 
	product_id VARCHAR(36) NOT NULL, 
	order_id VARCHAR(36), 
	movement_type VARCHAR(20) NOT NULL, 
	quantity NUMERIC(14, 3) NOT NULL, 
	reference VARCHAR(100), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(product_id) REFERENCES food_products (id), 
	FOREIGN KEY(order_id) REFERENCES food_orders (id)
);

CREATE TABLE contracts (
	id VARCHAR(36) NOT NULL, 
	contract_no VARCHAR(50) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	business_unit_id VARCHAR(36) NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	party_id VARCHAR(36) NOT NULL, 
	opportunity_id VARCHAR(36), 
	contract_type VARCHAR(50) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	total_value NUMERIC(18, 2) NOT NULL, 
	start_date DATE, 
	end_date DATE, 
	version INTEGER NOT NULL, 
	previous_version_id VARCHAR(36), 
	terms TEXT, 
	created_by VARCHAR(36), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id), 
	FOREIGN KEY(country_code) REFERENCES countries (code), 
	FOREIGN KEY(party_id) REFERENCES parties (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(previous_version_id) REFERENCES contracts (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE property_reservations (
	id VARCHAR(36) NOT NULL, 
	unit_id VARCHAR(36) NOT NULL, 
	party_id VARCHAR(36) NOT NULL, 
	opportunity_id VARCHAR(36), 
	start_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	deposit_amount NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(unit_id) REFERENCES property_units (id), 
	FOREIGN KEY(party_id) REFERENCES parties (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE installments (
	id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(36) NOT NULL, 
	description VARCHAR(160) NOT NULL, 
	due_date DATE NOT NULL, 
	amount NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (id)
);

CREATE TABLE payments (
	id VARCHAR(36) NOT NULL, 
	direction VARCHAR(10) NOT NULL, 
	party_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(36), 
	installment_id VARCHAR(36), 
	business_unit_id VARCHAR(36) NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	amount NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	method VARCHAR(30) NOT NULL, 
	reference VARCHAR(120), 
	status VARCHAR(20) NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(party_id) REFERENCES parties (id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (id), 
	FOREIGN KEY(installment_id) REFERENCES installments (id), 
	FOREIGN KEY(business_unit_id) REFERENCES business_units (id), 
	FOREIGN KEY(country_code) REFERENCES countries (code)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE INDEX ix_documents_entity_id ON documents (entity_id);

CREATE INDEX ix_documents_business_unit_id ON documents (business_unit_id);

CREATE INDEX ix_parties_display_name ON parties (display_name);

CREATE INDEX ix_parties_email ON parties (email);

CREATE INDEX ix_parties_phone ON parties (phone);

CREATE INDEX ix_session_tokens_user_id ON session_tokens (user_id);

CREATE INDEX ix_tasks_business_unit_id ON tasks (business_unit_id);

CREATE INDEX ix_car_bookings_party_id ON car_bookings (party_id);

CREATE INDEX ix_car_booking_period ON car_bookings (car_id, start_at, end_at);

CREATE INDEX ix_car_bookings_car_id ON car_bookings (car_id);

CREATE INDEX ix_car_maintenance_blocks_car_id ON car_maintenance_blocks (car_id);

CREATE INDEX ix_food_orders_customer_party_id ON food_orders (customer_party_id);

CREATE INDEX ix_leads_party_id ON leads (party_id);

CREATE INDEX ix_leads_business_unit_id ON leads (business_unit_id);

CREATE INDEX ix_food_order_lines_order_id ON food_order_lines (order_id);

CREATE INDEX ix_opportunities_party_id ON opportunities (party_id);

CREATE INDEX ix_opportunity_unit_stage ON opportunities (business_unit_id, stage);

CREATE INDEX ix_opportunities_business_unit_id ON opportunities (business_unit_id);

CREATE INDEX ix_property_units_project_id ON property_units (project_id);

CREATE INDEX ix_stock_movements_product_id ON stock_movements (product_id);

CREATE INDEX ix_contracts_business_unit_id ON contracts (business_unit_id);

CREATE INDEX ix_contracts_party_id ON contracts (party_id);

CREATE UNIQUE INDEX ix_contracts_contract_no ON contracts (contract_no);

CREATE INDEX ix_contract_unit_status ON contracts (business_unit_id, status);

CREATE INDEX ix_property_reservations_unit_id ON property_reservations (unit_id);

CREATE INDEX ix_property_reservations_party_id ON property_reservations (party_id);

CREATE INDEX ix_reservation_unit_period ON property_reservations (unit_id, start_at, expires_at);

CREATE INDEX ix_installments_contract_id ON installments (contract_id);

CREATE INDEX ix_payments_party_id ON payments (party_id);

CREATE INDEX ix_payments_contract_id ON payments (contract_id);

CREATE INDEX ix_payments_business_unit_id ON payments (business_unit_id);


-- Prevent overlapping reservations for the same property unit.
ALTER TABLE property_reservations
ADD CONSTRAINT property_reservations_no_overlap
EXCLUDE USING gist (unit_id WITH =, tstzrange(start_at, expires_at, '[)') WITH &&)
WHERE (status IN ('pending','confirmed'));

-- Prevent overlapping active/pending bookings for the same car.
ALTER TABLE car_bookings
ADD CONSTRAINT car_bookings_no_overlap
EXCLUDE USING gist (car_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&)
WHERE (status IN ('pending','confirmed','active'));

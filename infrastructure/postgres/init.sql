-- Everywhere Travel — Schema inicial
-- Extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ─── Enums ──────────────────────────────────────────────────────────────────
CREATE TYPE quotation_status AS ENUM ('DRAFT', 'VALIDATED', 'REJECTED', 'EXPIRED');
CREATE TYPE reservation_status AS ENUM ('PENDING_PAYMENT', 'CONFIRMED', 'CANCELLED', 'REFUNDED');
CREATE TYPE liquidation_status AS ENUM ('PARTIAL', 'COMPLETE', 'OVERDUE');
CREATE TYPE document_type AS ENUM ('VOUCHER', 'INVOICE', 'LIQUIDATION', 'REPORT', 'CONTRACT', 'ITINERARY', 'RECEIPT');
CREATE TYPE document_job_status AS ENUM ('QUEUED', 'PROCESSING', 'COMPLETE', 'FAILED');
CREATE TYPE saga_status AS ENUM ('RUNNING', 'COMPLETED', 'COMPENSATING', 'FAILED', 'REQUIRES_MANUAL');
CREATE TYPE validation_severity AS ENUM ('INFO', 'WARNING', 'ERROR', 'BLOCKING');
CREATE TYPE circuit_state AS ENUM ('CLOSED', 'OPEN', 'HALF_OPEN');
CREATE TYPE package_type AS ENUM ('PREDEFINED', 'CUSTOM');
CREATE TYPE priority_level AS ENUM ('LOW', 'NORMAL', 'HIGH', 'CRITICAL');

-- ─── Clientes ────────────────────────────────────────────────────────────────
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(50),
    document_type VARCHAR(20),
    document_number VARCHAR(50) UNIQUE,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Paquetes turísticos ──────────────────────────────────────────────────────
CREATE TABLE packages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    package_type package_type NOT NULL DEFAULT 'PREDEFINED',
    destination VARCHAR(255) NOT NULL,
    description TEXT,
    base_price NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'PEN',
    duration_days INTEGER NOT NULL,
    includes JSONB DEFAULT '[]',
    excludes JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Cotizaciones (versionadas, inmutables por versión) ───────────────────────
CREATE TABLE quotations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quote_id UUID NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    client_id UUID REFERENCES clients(id),
    package_id UUID REFERENCES packages(id),
    line_items JSONB NOT NULL DEFAULT '[]',
    total_cost NUMERIC(12, 2) NOT NULL,
    margin_pct NUMERIC(5, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'PEN',
    valid_until TIMESTAMPTZ NOT NULL,
    status quotation_status DEFAULT 'DRAFT',
    customizations JSONB DEFAULT '{}',
    created_by_agent VARCHAR(100),
    validated_by_agent VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(quote_id, version)
);
CREATE INDEX idx_quotations_client ON quotations(client_id);
CREATE INDEX idx_quotations_status ON quotations(status);
CREATE INDEX idx_quotations_quote_id ON quotations(quote_id);

-- ─── Reservas ────────────────────────────────────────────────────────────────
CREATE TABLE reservations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reservation_code VARCHAR(20) UNIQUE NOT NULL,
    quote_id UUID NOT NULL,
    client_id UUID REFERENCES clients(id),
    package_id UUID REFERENCES packages(id),
    travel_start TIMESTAMPTZ NOT NULL,
    travel_end TIMESTAMPTZ NOT NULL,
    traveler_count INTEGER NOT NULL DEFAULT 1,
    status reservation_status DEFAULT 'PENDING_PAYMENT',
    version INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_by_agent VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_reservations_client ON reservations(client_id);
CREATE INDEX idx_reservations_status ON reservations(status);

-- ─── Liquidaciones ────────────────────────────────────────────────────────────
CREATE TABLE liquidations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    liquidation_code VARCHAR(20) UNIQUE NOT NULL,
    reservation_id UUID REFERENCES reservations(id),
    total_charged NUMERIC(12, 2) NOT NULL,
    total_paid NUMERIC(12, 2) DEFAULT 0,
    balance NUMERIC(12, 2) GENERATED ALWAYS AS (total_charged - total_paid) STORED,
    commission_amount NUMERIC(12, 2) DEFAULT 0,
    commission_agent_id VARCHAR(100),
    status liquidation_status DEFAULT 'PARTIAL',
    payment_schedule JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    liquidation_id UUID REFERENCES liquidations(id),
    amount NUMERIC(12, 2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    reference VARCHAR(255),
    recorded_by_agent VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Documentos ───────────────────────────────────────────────────────────────
CREATE TABLE document_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_type document_type NOT NULL,
    reference_id UUID,
    reference_type VARCHAR(100),
    template_data JSONB NOT NULL,
    priority priority_level DEFAULT 'NORMAL',
    status document_job_status DEFAULT 'QUEUED',
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    requested_by_agent VARCHAR(100),
    document_url TEXT,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ─── Sagas (trazabilidad de flujos) ───────────────────────────────────────────
CREATE TABLE sagas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    saga_type VARCHAR(100) NOT NULL,
    status saga_status DEFAULT 'RUNNING',
    initiated_by VARCHAR(100),
    context JSONB DEFAULT '{}',
    steps JSONB DEFAULT '[]',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX idx_sagas_status ON sagas(status);
CREATE INDEX idx_sagas_created ON sagas(created_at);

-- ─── Auditoría de validaciones (inmutable) ────────────────────────────────────
CREATE TABLE validation_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    rules_checked JSONB NOT NULL,
    overall_status VARCHAR(10) NOT NULL,
    compliance_flags JSONB DEFAULT '[]',
    audited_by_agent VARCHAR(100),
    audited_at TIMESTAMPTZ DEFAULT NOW()
);
-- Tabla inmutable: sin UPDATE ni DELETE permitidos en producción

-- ─── Logs de interacción de agentes ──────────────────────────────────────────
CREATE TABLE agent_interaction_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    saga_id UUID,
    agent_id VARCHAR(100) NOT NULL,
    action VARCHAR(255) NOT NULL,
    input_schema JSONB,
    output_schema JSONB,
    duration_ms INTEGER,
    tokens_used INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_agent_logs_saga ON agent_interaction_logs(saga_id);
CREATE INDEX idx_agent_logs_agent ON agent_interaction_logs(agent_id);
CREATE INDEX idx_agent_logs_created ON agent_interaction_logs(created_at DESC);

-- ─── Usuarios internos ────────────────────────────────────────────────────────
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'sales_agent',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Usuario administrador por defecto (password: admin1234)
INSERT INTO users (username, email, hashed_password, role) VALUES
('admin', 'admin@everywheretravel.com',
 '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
 'admin');

-- Paquetes de ejemplo
INSERT INTO packages (name, package_type, destination, description, base_price, duration_days, includes) VALUES
('Cusco Mágico', 'PREDEFINED', 'Cusco, Perú',
 'Tour completo Machu Picchu + Valle Sagrado', 1800.00, 5,
 '["Vuelos Lima-Cusco-Lima", "Hotel 3*", "Guía turístico", "Entradas"]'),
('Cancún Todo Incluido', 'PREDEFINED', 'Cancún, México',
 'Resort todo incluido frente al mar', 3200.00, 7,
 '["Vuelos", "Resort 5* todo incluido", "Transfers"]'),
('Europa Express', 'PREDEFINED', 'Europa (3 países)',
 'Madrid, París, Roma en 12 días', 5500.00, 12,
 '["Vuelos internacionales", "Hoteles 4*", "Tren interurbano", "Guía"]'),
('Paquete Personalizable', 'CUSTOM', 'A definir',
 'Paquete diseñado según preferencias del cliente', 0.00, 0,
 '[]');

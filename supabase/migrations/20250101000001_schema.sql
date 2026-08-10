-- MaríliaBot — Schema Principal
-- Sprint 1: Tabelas core para coleta e normalização

-- Extensões
CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector para embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fuzzy matching para deduplicação

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE property_type AS ENUM (
    'apartment', 'house', 'land', 'commercial', 'rural',
    'condo_house', 'farm', 'other'
);

CREATE TYPE business_type AS ENUM ('sale', 'rent', 'both');

CREATE TYPE source_portal AS ENUM (
    'uniao', 'toca', 'vivareal', 'chavesnamao', 'imovelweb', 'olx'
);

CREATE TYPE agent_status AS ENUM ('running', 'completed', 'failed');

-- ============================================================
-- LISTINGS — Dados normalizados (tabela principal)
-- ============================================================

CREATE TABLE listings (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source              source_portal NOT NULL,
    source_id           TEXT NOT NULL,
    url                 TEXT,

    -- Classificação
    property_type       property_type NOT NULL,
    business_type       business_type NOT NULL DEFAULT 'sale',

    -- Localização
    title               TEXT,
    address             TEXT,
    street              TEXT,
    number              TEXT,
    complement          TEXT,
    neighborhood        TEXT,
    city                TEXT NOT NULL DEFAULT 'Marília',
    state               TEXT NOT NULL DEFAULT 'SP',
    zip_code            TEXT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,

    -- Valores
    sale_price          NUMERIC(14, 2),
    rent_price          NUMERIC(14, 2),
    condominium_fee     NUMERIC(10, 2),
    iptu                NUMERIC(10, 2),
    price_per_m2        NUMERIC(10, 2),

    -- Características
    total_area          NUMERIC(10, 2),
    built_area          NUMERIC(10, 2),
    bedrooms            SMALLINT,
    bathrooms           SMALLINT,
    suites              SMALLINT,
    parking_spaces      SMALLINT,
    description         TEXT,
    features            JSONB DEFAULT '[]',

    -- Flags
    is_mcmv             BOOLEAN DEFAULT FALSE,
    is_featured         BOOLEAN DEFAULT FALSE,
    is_active           BOOLEAN DEFAULT TRUE,

    -- Imagens
    main_image_url      TEXT,
    images              JSONB DEFAULT '[]',

    -- Metadata
    confidence_score    NUMERIC(3, 2),
    embedding           vector(1536),
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (source, source_id)
);

CREATE INDEX idx_listings_type ON listings (property_type);
CREATE INDEX idx_listings_neighborhood ON listings (neighborhood);
CREATE INDEX idx_listings_price ON listings (sale_price) WHERE sale_price IS NOT NULL;
CREATE INDEX idx_listings_area ON listings (total_area) WHERE total_area IS NOT NULL;
CREATE INDEX idx_listings_active ON listings (is_active) WHERE is_active;
CREATE INDEX idx_listings_lat ON listings (latitude) WHERE latitude IS NOT NULL;
CREATE INDEX idx_listings_lng ON listings (longitude) WHERE longitude IS NOT NULL;
CREATE INDEX idx_listings_trgm_address ON listings USING gin (address gin_trgm_ops);
CREATE INDEX idx_listings_trgm_neighborhood ON listings USING gin (neighborhood gin_trgm_ops);

-- ============================================================
-- RAW_LISTINGS — Dados brutos dos coletores
-- ============================================================

CREATE TABLE raw_listings (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          source_portal NOT NULL,
    source_id       TEXT NOT NULL,
    raw_data        JSONB NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed       BOOLEAN NOT NULL DEFAULT FALSE,
    listing_id      BIGINT REFERENCES listings(id),

    UNIQUE (source, source_id)
);

CREATE INDEX idx_raw_listings_source ON raw_listings (source);
CREATE INDEX idx_raw_listings_processed ON raw_listings (processed) WHERE NOT processed;
CREATE INDEX idx_raw_listings_collected ON raw_listings (collected_at DESC);

-- ============================================================
-- NEIGHBORHOODS — Bairros com dados agregados
-- ============================================================

CREATE TABLE neighborhoods (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    zone                TEXT,
    avg_price_m2_land   NUMERIC(10, 2),
    avg_price_m2_house  NUMERIC(10, 2),
    avg_price_m2_apt    NUMERIC(10, 2),
    total_listings      INT DEFAULT 0,
    total_land          INT DEFAULT 0,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- MARKET_SNAPSHOTS — Série temporal de métricas
-- ============================================================

CREATE TABLE market_snapshots (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_date       DATE NOT NULL DEFAULT CURRENT_DATE,
    property_type       property_type,
    neighborhood        TEXT,

    total_listings      INT,
    new_listings        INT,
    removed_listings    INT,
    avg_price           NUMERIC(14, 2),
    median_price        NUMERIC(14, 2),
    avg_price_m2        NUMERIC(10, 2),
    min_price           NUMERIC(14, 2),
    max_price           NUMERIC(14, 2),
    avg_area            NUMERIC(10, 2),
    avg_days_on_market  INT,

    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (snapshot_date, property_type, neighborhood)
);

-- ============================================================
-- OPPORTUNITIES — Terrenos pontuados pelo Caçador
-- ============================================================

CREATE TABLE opportunities (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id          BIGINT NOT NULL REFERENCES listings(id),
    score               NUMERIC(5, 2) NOT NULL,
    score_breakdown     JSONB NOT NULL DEFAULT '{}',
    reason              TEXT,
    is_notified         BOOLEAN DEFAULT FALSE,
    notified_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_opportunities_score ON opportunities (score DESC);

-- ============================================================
-- VIABILITY_STUDIES — Estudos de viabilidade
-- ============================================================

CREATE TABLE viability_studies (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id          BIGINT NOT NULL REFERENCES listings(id),
    scenario            TEXT NOT NULL,
    inputs              JSONB NOT NULL,
    outputs             JSONB NOT NULL,
    is_viable           BOOLEAN,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- AGENT_RUNS — Log de execução dos agentes
-- ============================================================

CREATE TABLE agent_runs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_name          TEXT NOT NULL,
    status              agent_status NOT NULL DEFAULT 'running',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    items_processed     INT DEFAULT 0,
    items_created       INT DEFAULT 0,
    items_updated       INT DEFAULT 0,
    items_failed        INT DEFAULT 0,
    error_message       TEXT,
    metadata            JSONB DEFAULT '{}'
);

CREATE INDEX idx_agent_runs_agent ON agent_runs (agent_name, started_at DESC);

-- ============================================================
-- PRICE_HISTORY — Tracking de mudanças de preço
-- ============================================================

CREATE TABLE price_history (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id          BIGINT NOT NULL REFERENCES listings(id),
    old_price           NUMERIC(14, 2),
    new_price           NUMERIC(14, 2),
    change_pct          NUMERIC(6, 2),
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_price_history_listing ON price_history (listing_id, detected_at DESC);

-- ============================================================
-- LISTING_MATCHES — Deduplicação cross-portal
-- ============================================================

CREATE TABLE listing_matches (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_a_id        BIGINT NOT NULL REFERENCES listings(id),
    listing_b_id        BIGINT NOT NULL REFERENCES listings(id),
    match_score         NUMERIC(3, 2) NOT NULL,
    match_method        TEXT NOT NULL,
    confirmed           BOOLEAN,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (listing_a_id, listing_b_id),
    CHECK (listing_a_id < listing_b_id)
);

-- ============================================================
-- MCMV_RULES — Regras Minha Casa Minha Vida
-- ============================================================

CREATE TABLE mcmv_rules (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    faixa               TEXT NOT NULL,
    renda_min           NUMERIC(10, 2),
    renda_max           NUMERIC(10, 2),
    valor_max_imovel    NUMERIC(14, 2),
    taxa_juros          NUMERIC(5, 2),
    subsidio_max        NUMERIC(14, 2),
    valid_from          DATE NOT NULL,
    valid_until         DATE,
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

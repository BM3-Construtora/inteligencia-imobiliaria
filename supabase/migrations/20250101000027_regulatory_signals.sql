-- 023_regulatory_signals.sql — Track C: regulatory & compliance flags
-- BM3 já se queimou com problemas de desdobramento + APP + zoneamento.
-- Este módulo emite SINAIS (não bloqueios) para revisão humana via dashboard/telegram.
--
-- Tabelas:
--   zoning_zones        — zonas do plano diretor de Marília (parseadas do PDF ou fallback)
--   regulatory_signals  — flags por listing (zoning_mismatch, app_overlap, litigation, etc)
--   seller_history      — histórico de litígio do vendedor (hash do CPF/CNPJ)

CREATE TABLE IF NOT EXISTS zoning_zones (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_code       TEXT NOT NULL UNIQUE,
    zone_name       TEXT NOT NULL,
    allowed_uses    TEXT[] DEFAULT '{}',   -- residencial, comercial, misto, industrial
    min_lot_area_m2 NUMERIC,
    max_height_m    NUMERIC,
    max_coverage_pct NUMERIC,
    max_far         NUMERIC,               -- coeficiente de aproveitamento
    description     TEXT,
    geom_wkt        TEXT,                  -- polígono em WKT (PostGIS later)
    source_doc_url  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_zoning_zones_code ON zoning_zones (zone_code);


CREATE TABLE IF NOT EXISTS regulatory_signals (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id      BIGINT REFERENCES listings(id) ON DELETE CASCADE,
    neighborhood    TEXT,
    signal_type     TEXT NOT NULL CHECK (signal_type IN (
        'zoning_mismatch',
        'app_overlap',
        'reserva_legal',
        'distance_water',
        'seller_litigation',
        'generic_warning'
    )),
    severity        TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    title           TEXT NOT NULL,
    description     TEXT,
    source          TEXT,
    raw             JSONB DEFAULT '{}',
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_regulatory_signals_listing
    ON regulatory_signals (listing_id);
CREATE INDEX IF NOT EXISTS idx_regulatory_signals_neighborhood
    ON regulatory_signals (neighborhood);
CREATE INDEX IF NOT EXISTS idx_regulatory_signals_severity
    ON regulatory_signals (severity);
CREATE INDEX IF NOT EXISTS idx_regulatory_signals_type
    ON regulatory_signals (signal_type);


CREATE TABLE IF NOT EXISTS seller_history (
    doc_hash            TEXT PRIMARY KEY,           -- sha256 do CPF/CNPJ normalizado
    seller_type         TEXT CHECK (seller_type IN ('pf', 'pj')),
    litigation_count    INT DEFAULT 0,
    last_litigation_at  TIMESTAMPTZ,
    complaints          JSONB DEFAULT '[]',
    last_updated        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seller_history_litigation
    ON seller_history (litigation_count DESC)
    WHERE litigation_count > 0;


-- RLS — padrão Marília (service_role full, anon SELECT)
ALTER TABLE zoning_zones ENABLE ROW LEVEL SECURITY;
ALTER TABLE regulatory_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE seller_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on zoning_zones" ON zoning_zones;
CREATE POLICY "service_role full access on zoning_zones"
    ON zoning_zones FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on zoning_zones" ON zoning_zones;
CREATE POLICY "Allow public read on zoning_zones"
    ON zoning_zones FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS "service_role full access on regulatory_signals" ON regulatory_signals;
CREATE POLICY "service_role full access on regulatory_signals"
    ON regulatory_signals FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on regulatory_signals" ON regulatory_signals;
CREATE POLICY "Allow public read on regulatory_signals"
    ON regulatory_signals FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS "service_role full access on seller_history" ON seller_history;
CREATE POLICY "service_role full access on seller_history"
    ON seller_history FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on seller_history" ON seller_history;
CREATE POLICY "Allow public read on seller_history"
    ON seller_history FOR SELECT TO anon USING (true);

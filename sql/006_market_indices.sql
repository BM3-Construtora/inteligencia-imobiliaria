-- 006_market_indices.sql — Dados agregados de fontes públicas (CRECI, Prefeitura, etc.)

CREATE TABLE IF NOT EXISTS market_indices (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          TEXT NOT NULL,           -- 'creci_sp', 'prefeitura', 'fipezap'
    region          TEXT NOT NULL,           -- 'marilia', 'interior_sp'
    period          TEXT NOT NULL,           -- '2026-Q1', '2026-03'
    metric_name     TEXT NOT NULL,           -- 'median_price_m2_land', 'sales_volume', etc.
    metric_value    NUMERIC(14, 2),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, region, period, metric_name)
);

-- RLS: public read for dashboard
ALTER TABLE market_indices ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read market_indices" ON market_indices
    FOR SELECT USING (true);

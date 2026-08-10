-- 019_off_market_signals.sql — Off-market opportunity signals
-- Sinais de oportunidade FORA dos portais (leilão Caixa, IPTU devedores,
-- alvarás prefeitura, inventários TJ-SP). Geram leads barateados.

CREATE TABLE IF NOT EXISTS off_market_signals (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN (
        'leilao_caixa',
        'iptu_devedor',
        'alvara_prefeitura',
        'inventario_tjsp',
        'leilao_judicial'
    )),
    source_id TEXT,
    signal_type TEXT NOT NULL CHECK (signal_type IN (
        'distress',
        'permit',
        'heritage',
        'auction'
    )),
    title TEXT,
    description TEXT,
    address TEXT,
    neighborhood TEXT,
    city TEXT DEFAULT 'Marília',
    state TEXT DEFAULT 'SP',
    latitude NUMERIC,
    longitude NUMERIC,
    estimated_value NUMERIC,
    area_m2 NUMERIC,
    owner_name TEXT,
    owner_doc TEXT,
    event_date TIMESTAMPTZ,
    deadline TIMESTAMPTZ,
    raw_payload JSONB,
    url TEXT,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    distress_score NUMERIC,
    distress_reasons JSONB,
    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_off_market_signals_source
    ON off_market_signals (source);
CREATE INDEX IF NOT EXISTS idx_off_market_signals_signal_type
    ON off_market_signals (signal_type);
CREATE INDEX IF NOT EXISTS idx_off_market_signals_neighborhood
    ON off_market_signals (neighborhood);
CREATE INDEX IF NOT EXISTS idx_off_market_signals_event_date
    ON off_market_signals (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_off_market_signals_distress_score
    ON off_market_signals (distress_score DESC)
    WHERE is_active;

-- RLS
ALTER TABLE off_market_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on off_market_signals"
    ON off_market_signals;
CREATE POLICY "service_role full access on off_market_signals"
    ON off_market_signals
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on off_market_signals"
    ON off_market_signals;
CREATE POLICY "Allow public read on off_market_signals"
    ON off_market_signals
    FOR SELECT
    TO anon
    USING (true);

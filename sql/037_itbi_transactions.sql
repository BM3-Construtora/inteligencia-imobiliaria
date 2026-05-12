-- 031_itbi_transactions.sql — Transações de ITBI (preço real de venda)
-- ITBI = Imposto sobre Transmissão de Bens Imóveis. Cada linha equivale a
-- uma DTI (Declaração de Transações Imobiliárias) recolhida no município.
-- Diferente de listings: este é o PREÇO FECHADO real, não anúncio.

CREATE TABLE IF NOT EXISTS itbi_transactions (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL UNIQUE,
    transaction_date DATE,
    address TEXT,
    neighborhood TEXT,
    city TEXT DEFAULT 'Marília',
    state TEXT DEFAULT 'SP',
    latitude NUMERIC,
    longitude NUMERIC,
    property_type TEXT,  -- terreno | casa | apartamento | comercial | rural | outro
    area_m2 NUMERIC,
    declared_value NUMERIC,  -- valor declarado pelas partes (R$)
    market_value NUMERIC,    -- valor venal/de mercado usado como base ITBI (R$)
    buyer_doc TEXT,          -- CPF/CNPJ parcial ou hash
    seller_doc TEXT,
    registry_number TEXT,    -- número da matrícula / cartório
    raw_payload JSONB,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_itbi_transaction_date
    ON itbi_transactions (transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_itbi_neighborhood
    ON itbi_transactions (neighborhood);
CREATE INDEX IF NOT EXISTS idx_itbi_declared_value
    ON itbi_transactions (declared_value DESC);
CREATE INDEX IF NOT EXISTS idx_itbi_city_state
    ON itbi_transactions (city, state);

-- RLS
ALTER TABLE itbi_transactions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on itbi_transactions"
    ON itbi_transactions;
CREATE POLICY "service_role full access on itbi_transactions"
    ON itbi_transactions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on itbi_transactions"
    ON itbi_transactions;
CREATE POLICY "Allow public read on itbi_transactions"
    ON itbi_transactions
    FOR SELECT
    TO anon
    USING (true);

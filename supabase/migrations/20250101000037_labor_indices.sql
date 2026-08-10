-- 034_labor_indices.sql — Índices de mão-de-obra (rendimento e ocupação)
-- Fonte: SIDRA/IBGE PNAD Contínua trimestral por atividade econômica (Construção)
-- Usado para calibrar custo de mão-de-obra em viability.py (complementar ao SINAPI nacional)

CREATE TABLE IF NOT EXISTS labor_indices (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          TEXT NOT NULL,           -- 'sidra_pnad', 'caged', 'rais'
    period_code     TEXT NOT NULL,           -- '2025T1', '2024-09'
    region_code     TEXT NOT NULL,           -- '35' (SP), '00' (Brasil), IBGE UF code
    indicator       TEXT NOT NULL,           -- 'rendimento_medio', 'ocupados', 'admissoes', 'demissoes'
    sector          TEXT NOT NULL,           -- 'construcao_civil', 'total'
    value           NUMERIC(14, 2),
    unit            TEXT,                    -- 'R$/mes', 'mil_pessoas', 'pessoas'
    raw_payload     JSONB DEFAULT '{}',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, period_code, region_code, indicator, sector)
);

CREATE INDEX IF NOT EXISTS idx_labor_indices_sector_period
    ON labor_indices (sector, period_code DESC);

-- RLS
ALTER TABLE labor_indices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "labor_indices service role full access" ON labor_indices;
CREATE POLICY "labor_indices service role full access" ON labor_indices
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "labor_indices public read" ON labor_indices;
CREATE POLICY "labor_indices public read" ON labor_indices
    FOR SELECT USING (true);

-- 032_habite_se.sql — Habite-se (certificados de conclusão de obra) Marília-SP
-- Habite-se = obra finalizada. Cruzando com alvará (off_market_signals signal_type=permit)
-- conseguimos: prazo médio obra, custo real por m², densidade de novas entregas por bairro.
-- Tabela separada (não usa off_market_signals) porque tem campos específicos
-- (área construída, custo declarado, referência ao alvará original).

CREATE TABLE IF NOT EXISTS habite_se_records (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT NOT NULL UNIQUE,         -- número do processo/protocolo ou hash do snippet
    issue_date          DATE,                         -- data de emissão do habite-se
    process_number      TEXT,                         -- processo administrativo (ex: 12345/2024)
    address             TEXT,
    neighborhood        TEXT,
    city                TEXT NOT NULL DEFAULT 'Marília',
    state               TEXT NOT NULL DEFAULT 'SP',
    latitude            NUMERIC,
    longitude           NUMERIC,
    area_built_m2       NUMERIC,                      -- área construída
    area_terrain_m2     NUMERIC,                      -- área do terreno
    declared_cost       NUMERIC,                      -- custo declarado (R$) quando publicado
    owner_name          TEXT,
    owner_doc           TEXT,                         -- CPF/CNPJ (raw — hashear no consumer se precisar)
    alvara_reference    TEXT,                         -- FK lógico p/ off_market_signals.source_id (signal_type=permit)
    raw_payload         JSONB,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_habite_se_issue_date
    ON habite_se_records (issue_date DESC);
CREATE INDEX IF NOT EXISTS idx_habite_se_neighborhood
    ON habite_se_records (neighborhood);
CREATE INDEX IF NOT EXISTS idx_habite_se_area_built
    ON habite_se_records (area_built_m2);
CREATE INDEX IF NOT EXISTS idx_habite_se_alvara_ref
    ON habite_se_records (alvara_reference)
    WHERE alvara_reference IS NOT NULL;

-- RLS — padrão Marília (service_role full, anon SELECT)
ALTER TABLE habite_se_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on habite_se_records"
    ON habite_se_records;
CREATE POLICY "service_role full access on habite_se_records"
    ON habite_se_records FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on habite_se_records"
    ON habite_se_records;
CREATE POLICY "Allow public read on habite_se_records"
    ON habite_se_records FOR SELECT TO anon
    USING (true);

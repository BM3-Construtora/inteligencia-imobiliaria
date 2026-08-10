-- 036_construction_timeline.sql — Cruzamento Alvará × Habite-se = prazo real de obra
--
-- Tabela materializa o JOIN entre off_market_signals (source='alvara_prefeitura',
-- signal_type='permit') e habite_se_records. Cada linha = 1 obra completa
-- (permit_date -> completion_date). Alimenta:
--   * viability.py — substitui prazo default por mediana real por bairro
--   * análise de custo real por m² (declared_cost / area_built_m2)
--   * dashboards de absorção por bairro

CREATE TABLE IF NOT EXISTS construction_timeline (
    id                   BIGSERIAL PRIMARY KEY,
    alvara_signal_id     BIGINT NOT NULL
                         REFERENCES off_market_signals(id) ON DELETE CASCADE,
    habite_se_id         BIGINT NOT NULL
                         REFERENCES habite_se_records(id) ON DELETE CASCADE,
    permit_date          DATE NOT NULL,
    completion_date      DATE NOT NULL,
    duration_days        INTEGER NOT NULL,
    neighborhood         TEXT,
    area_m2              NUMERIC,
    declared_cost_brl    NUMERIC,                -- nullable: nem todo habite-se traz custo
    cost_per_m2          NUMERIC,                -- nullable: declared_cost/area_m2 quando ambos > 0
    match_strategy       TEXT NOT NULL DEFAULT 'process_number'
                         CHECK (match_strategy IN ('process_number', 'address_area_window')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (alvara_signal_id, habite_se_id)
);

CREATE INDEX IF NOT EXISTS idx_construction_timeline_neighborhood
    ON construction_timeline (neighborhood);
CREATE INDEX IF NOT EXISTS idx_construction_timeline_duration
    ON construction_timeline (duration_days);
CREATE INDEX IF NOT EXISTS idx_construction_timeline_completion
    ON construction_timeline (completion_date DESC);

-- View agregada por bairro: estatísticas de prazo e custo.
-- VIEW (não materializada) — volume baixo, refresh contínuo do upsert basta.
CREATE OR REPLACE VIEW v_construction_stats_by_neighborhood AS
SELECT
    neighborhood,
    COUNT(*) AS sample_size,
    percentile_cont(0.5)  WITHIN GROUP (ORDER BY duration_days)::INT AS median_duration_days,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY duration_days)::INT AS p25_duration_days,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY duration_days)::INT AS p75_duration_days,
    percentile_cont(0.5)  WITHIN GROUP (ORDER BY cost_per_m2)
        FILTER (WHERE cost_per_m2 IS NOT NULL AND cost_per_m2 > 0) AS median_cost_per_m2,
    MIN(completion_date) AS first_completion,
    MAX(completion_date) AS last_completion
FROM construction_timeline
WHERE neighborhood IS NOT NULL
GROUP BY neighborhood;

-- RLS — padrão Marília
ALTER TABLE construction_timeline ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on construction_timeline"
    ON construction_timeline;
CREATE POLICY "service_role full access on construction_timeline"
    ON construction_timeline FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on construction_timeline"
    ON construction_timeline;
CREATE POLICY "Allow public read on construction_timeline"
    ON construction_timeline FOR SELECT TO anon
    USING (true);

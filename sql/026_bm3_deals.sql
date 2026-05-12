-- 021_bm3_deals.sql — Track D — Feedback loop / decision calibration
-- Registra TODA visita/oferta/resultado real para fechar o loop entre
-- recomendação (Hunter/AVM/Viability) e realidade observada.

-- ----------------------------------------------------------------------
-- Tabela principal: bm3_deals
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bm3_deals (
    id                          BIGSERIAL PRIMARY KEY,
    listing_id                  BIGINT REFERENCES listings(id) ON DELETE SET NULL,
    -- off_market_signal_id é adicionado abaixo via DO block (se a tabela existir)
    stage                       TEXT NOT NULL CHECK (stage IN (
        'visited',
        'offered',
        'negotiating',
        'accepted',
        'rejected',
        'closed_won',
        'closed_lost',
        'abandoned'
    )),
    visited_at                  TIMESTAMPTZ,
    offered_at                  TIMESTAMPTZ,
    closed_at                   TIMESTAMPTZ,
    asking_price                NUMERIC(14, 2),
    offered_price               NUMERIC(14, 2),
    accepted_price              NUMERIC(14, 2),
    hunter_score_at_visit       NUMERIC(6, 2),
    avm_p25_at_visit            NUMERIC(14, 2),
    avm_p50_at_visit            NUMERIC(14, 2),
    avm_p75_at_visit            NUMERIC(14, 2),
    viability_margin_at_visit   NUMERIC(6, 2),
    actual_outcome_margin_pct   NUMERIC(6, 2),
    actual_outcome_payback_months INT,
    notes                       TEXT,
    rejection_reason            TEXT,
    created_by                  TEXT NOT NULL DEFAULT 'matheus',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Adiciona FK para off_market_signals se a tabela existir (Track A)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'off_market_signals'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'bm3_deals'
              AND column_name = 'off_market_signal_id'
        ) THEN
            ALTER TABLE bm3_deals
                ADD COLUMN off_market_signal_id BIGINT
                REFERENCES off_market_signals(id) ON DELETE SET NULL;
        END IF;
    ELSE
        -- Se Track A ainda não rodou, deixa a coluna como BIGINT sem FK
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'bm3_deals'
              AND column_name = 'off_market_signal_id'
        ) THEN
            ALTER TABLE bm3_deals ADD COLUMN off_market_signal_id BIGINT;
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_bm3_deals_listing      ON bm3_deals (listing_id);
CREATE INDEX IF NOT EXISTS idx_bm3_deals_stage        ON bm3_deals (stage);
CREATE INDEX IF NOT EXISTS idx_bm3_deals_created_at   ON bm3_deals (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bm3_deals_closed_at    ON bm3_deals (closed_at DESC);

-- ----------------------------------------------------------------------
-- Trigger updated_at
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION bm3_deals_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bm3_deals_updated_at ON bm3_deals;
CREATE TRIGGER trg_bm3_deals_updated_at
    BEFORE UPDATE ON bm3_deals
    FOR EACH ROW
    EXECUTE FUNCTION bm3_deals_set_updated_at();

-- ----------------------------------------------------------------------
-- Tabela: recommendation_calibration
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_calibration (
    id                       BIGSERIAL PRIMARY KEY,
    run_date                 DATE NOT NULL DEFAULT CURRENT_DATE,
    total_recommendations    INT,
    visited                  INT,
    offered                  INT,
    accepted                 INT,
    hunter_hit_rate          NUMERIC(6, 4),
    avm_mean_error_pct       NUMERIC(6, 2),
    viability_mean_error_pct NUMERIC(6, 2),
    notes                    TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_calibration_run_date
    ON recommendation_calibration (run_date DESC);

-- ----------------------------------------------------------------------
-- RLS
-- ----------------------------------------------------------------------
ALTER TABLE bm3_deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_calibration ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on bm3_deals" ON bm3_deals;
CREATE POLICY "service_role full access on bm3_deals"
    ON bm3_deals FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on bm3_deals" ON bm3_deals;
CREATE POLICY "Allow public read on bm3_deals"
    ON bm3_deals FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS "service_role full access on recommendation_calibration"
    ON recommendation_calibration;
CREATE POLICY "service_role full access on recommendation_calibration"
    ON recommendation_calibration FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on recommendation_calibration"
    ON recommendation_calibration;
CREATE POLICY "Allow public read on recommendation_calibration"
    ON recommendation_calibration FOR SELECT TO anon USING (true);

-- Hunter score history — para calibrar percentil.
-- Hoje top score 77/95: critérios "perfeito" inatingíveis. Histórico permite
-- normalizar via percentil ao invés de absoluto.

CREATE TABLE IF NOT EXISTS hunter_score_history (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id      BIGINT NOT NULL REFERENCES listings(id),
    raw_score       NUMERIC(5, 2) NOT NULL,
    percentile      NUMERIC(5, 2),
    score_breakdown JSONB,
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hunter_history_listing
    ON hunter_score_history (listing_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_hunter_history_date
    ON hunter_score_history (snapshot_date DESC);

ALTER TABLE opportunities
    ADD COLUMN IF NOT EXISTS percentile_score NUMERIC(5, 2);

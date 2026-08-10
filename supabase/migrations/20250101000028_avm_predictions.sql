-- AVM (Automated Valuation Model) predictions — Track E
-- Stores per-listing quantile predictions (P10/P25/P50/P75/P90) + SHAP
-- explanations for negotiation support.

CREATE TABLE IF NOT EXISTS avm_predictions (
    id                  BIGSERIAL PRIMARY KEY,
    listing_id          BIGINT NOT NULL UNIQUE
                          REFERENCES listings(id) ON DELETE CASCADE,

    -- Quantile predictions (absolute price)
    p10                 NUMERIC(14, 2),
    p25                 NUMERIC(14, 2),
    p50                 NUMERIC(14, 2),
    p75                 NUMERIC(14, 2),
    p90                 NUMERIC(14, 2),

    -- Per-m² quantiles (convenience)
    p10_per_m2          NUMERIC(12, 2),
    p50_per_m2          NUMERIC(12, 2),
    p75_per_m2          NUMERIC(12, 2),

    -- Asking price snapshot + mispricing signal
    actual_price        NUMERIC(14, 2),
    mispricing_pct      NUMERIC(8, 2),    -- (p50 - actual) / p50 * 100
    is_undervalued      BOOLEAN DEFAULT FALSE,  -- actual < p25

    -- Explainability
    shap_top_features   JSONB,            -- [{feature, value, contribution}]
    shap_summary        TEXT,             -- human-readable PT-BR

    -- Bookkeeping
    model_version       TEXT,
    features_used       JSONB,
    confidence          NUMERIC(4, 3),    -- 0..1 (based on n neighbors)
    predicted_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_avm_predictions_listing
    ON avm_predictions (listing_id);

CREATE INDEX IF NOT EXISTS idx_avm_predictions_undervalued
    ON avm_predictions (listing_id)
    WHERE is_undervalued IS TRUE;

CREATE INDEX IF NOT EXISTS idx_avm_predictions_mispricing
    ON avm_predictions (mispricing_pct DESC);

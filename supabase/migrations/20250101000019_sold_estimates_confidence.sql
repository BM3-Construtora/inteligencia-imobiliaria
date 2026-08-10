-- Sales tracker confidence scoring (cross-references price_history).
-- Columns optional: sales_tracker falls back to legacy insert if missing.

ALTER TABLE sold_estimates
    ADD COLUMN IF NOT EXISTS confidence TEXT,
    ADD COLUMN IF NOT EXISTS signals JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_sold_estimates_confidence
    ON sold_estimates (confidence) WHERE confidence IS NOT NULL;

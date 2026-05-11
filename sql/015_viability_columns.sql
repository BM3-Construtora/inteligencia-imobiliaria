-- Promote key metrics from JSON to columns for analytics queries.
-- Migration is non-destructive: keeps `inputs`/`outputs` JSON, adds typed cols.

ALTER TABLE viability_studies
    ADD COLUMN IF NOT EXISTS land_cost          NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS construction_cost  NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS total_cost         NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS vgv                NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS gross_margin_pct   NUMERIC(6, 2),
    ADD COLUMN IF NOT EXISTS net_margin_pct     NUMERIC(6, 2),
    ADD COLUMN IF NOT EXISTS roi_pct            NUMERIC(8, 2),
    ADD COLUMN IF NOT EXISTS irr_annual_pct     NUMERIC(8, 2),
    ADD COLUMN IF NOT EXISTS payback_months     NUMERIC(6, 1),
    ADD COLUMN IF NOT EXISTS units              INT;

CREATE INDEX IF NOT EXISTS idx_viability_listing
    ON viability_studies (listing_id, scenario);
CREATE INDEX IF NOT EXISTS idx_viability_margin
    ON viability_studies (net_margin_pct DESC) WHERE is_viable;

-- Backfill from JSON (best-effort)
UPDATE viability_studies SET
    land_cost = (inputs->>'land_price')::NUMERIC,
    construction_cost = (outputs->>'construction_cost')::NUMERIC,
    total_cost = (outputs->>'total_cost')::NUMERIC,
    vgv = (outputs->>'vgv')::NUMERIC,
    gross_margin_pct = (outputs->>'gross_margin_pct')::NUMERIC,
    net_margin_pct = (outputs->>'net_margin_pct')::NUMERIC,
    roi_pct = (outputs->>'roi_pct')::NUMERIC,
    payback_months = (outputs->>'payback_months')::NUMERIC,
    units = (outputs->>'units')::INT
WHERE land_cost IS NULL;

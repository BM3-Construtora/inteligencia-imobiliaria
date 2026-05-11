-- Sprint Data Quality — fixes P0/P1
-- 1. Widen narrow NUMERIC columns causing overflow
-- 2. Add quarantine flag for invalid listings
-- 3. Add city to neighborhoods
-- 4. Add unique constraint for hunter opportunities upsert
-- 5. Data quality log table

-- ============================================================
-- 1. Widen narrow numeric cols (analyst overflow fix)
-- ============================================================
ALTER TABLE neighborhoods
    ALTER COLUMN absorption_rate TYPE NUMERIC(10, 2),
    ALTER COLUMN avg_risk_score  TYPE NUMERIC(6, 2),
    ALTER COLUMN months_of_inventory TYPE NUMERIC(10, 2);

ALTER TABLE listings
    ALTER COLUMN price_per_m2 TYPE NUMERIC(12, 2);

-- ============================================================
-- 2. Quarantine flag + reason on listings (validation fail)
-- ============================================================
ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS quarantined BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS quarantine_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_listings_quarantined
    ON listings (quarantined) WHERE quarantined;

-- ============================================================
-- 3. Neighborhoods: add city, compound unique
-- ============================================================
ALTER TABLE neighborhoods
    ADD COLUMN IF NOT EXISTS city TEXT NOT NULL DEFAULT 'Marília';

-- Drop old unique-on-name, add (name, city)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'neighborhoods_name_key'
    ) THEN
        ALTER TABLE neighborhoods DROP CONSTRAINT neighborhoods_name_key;
    END IF;
END$$;

ALTER TABLE neighborhoods
    ADD CONSTRAINT neighborhoods_name_city_key UNIQUE (name, city);

-- ============================================================
-- 4. Opportunities: unique on listing_id for upsert
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'opportunities_listing_id_key'
    ) THEN
        ALTER TABLE opportunities
            ADD CONSTRAINT opportunities_listing_id_key UNIQUE (listing_id);
    END IF;
END$$;

-- ============================================================
-- 5. Data quality log — track rejections
-- ============================================================
CREATE TABLE IF NOT EXISTS data_quality_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_listing_id  BIGINT REFERENCES raw_listings(id) ON DELETE SET NULL,
    listing_id      BIGINT REFERENCES listings(id) ON DELETE SET NULL,
    source          TEXT,
    source_id       TEXT,
    severity        TEXT NOT NULL,    -- 'reject' | 'quarantine' | 'warn'
    rule            TEXT NOT NULL,    -- 'price_too_low' | 'area_too_large' | ...
    details         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dq_log_rule ON data_quality_log (rule, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dq_log_source ON data_quality_log (source, created_at DESC);

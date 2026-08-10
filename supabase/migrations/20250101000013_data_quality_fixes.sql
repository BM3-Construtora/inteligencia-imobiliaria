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

-- price_per_m2 widening: drop dependent views, alter, recreate
DROP VIEW IF EXISTS property_price_timeline;
DROP VIEW IF EXISTS property_summary;

ALTER TABLE listings
    ALTER COLUMN price_per_m2 TYPE NUMERIC(12, 2);

CREATE OR REPLACE VIEW property_price_timeline AS
SELECT
  COALESCE(l.canonical_listing_id, l.id) AS property_id,
  l.id AS listing_id,
  l.source,
  l.source_id,
  l.sale_price AS current_price,
  l.price_per_m2 AS current_price_m2,
  l.total_area,
  l.neighborhood,
  l.property_type,
  l.title,
  l.url,
  l.first_seen_at,
  l.last_seen_at,
  l.is_active,
  (
    SELECT json_agg(json_build_object(
      'old_price', ph.old_price,
      'new_price', ph.new_price,
      'change_pct', ph.change_pct,
      'changed_at', ph.detected_at,
      'source', ph.source
    ) ORDER BY ph.detected_at DESC)
    FROM price_history ph WHERE ph.listing_id = l.id
  ) AS price_changes
FROM listings l
WHERE l.sale_price IS NOT NULL AND l.sale_price > 0
ORDER BY COALESCE(l.canonical_listing_id, l.id), l.source;

CREATE OR REPLACE VIEW property_summary AS
SELECT
  COALESCE(l.canonical_listing_id, l.id) AS property_id,
  MIN(l.neighborhood) AS neighborhood,
  MIN(l.property_type) AS property_type,
  MAX(l.total_area) AS total_area,
  COUNT(*) AS num_sources,
  json_agg(DISTINCT l.source) AS sources,
  MIN(l.sale_price) AS min_price,
  MAX(l.sale_price) AS max_price,
  AVG(l.sale_price)::NUMERIC(14,2) AS avg_price,
  MAX(l.sale_price) - MIN(l.sale_price) AS price_spread,
  MIN(l.first_seen_at) AS first_seen,
  MAX(l.last_seen_at) AS last_seen,
  BOOL_OR(l.is_active) AS is_active,
  json_agg(json_build_object(
    'source', l.source,
    'price', l.sale_price,
    'url', l.url,
    'listing_id', l.id,
    'is_active', l.is_active
  )) AS listings
FROM listings l
WHERE l.sale_price IS NOT NULL AND l.sale_price > 0
GROUP BY COALESCE(l.canonical_listing_id, l.id);

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

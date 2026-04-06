-- 012: Cross-platform price history & property grouping
--
-- Conceito: um IMÓVEL FÍSICO pode ter N listings em portais diferentes.
-- O deduplicator detecta quais listings são o mesmo imóvel e seta
-- canonical_listing_id no listing "inferior".
--
-- property_id = COALESCE(canonical_listing_id, id) agrupa todos.

-- Add source to price_history if not present
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'price_history' AND column_name = 'source'
  ) THEN
    ALTER TABLE price_history ADD COLUMN source TEXT;
  END IF;
END $$;

-- View: timeline de preços de cada IMÓVEL FÍSICO across all portals
-- Uso: SELECT * FROM property_price_timeline WHERE property_id = 123
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
  -- Price history embedded as array (latest first)
  (
    SELECT json_agg(json_build_object(
      'old_price', ph.old_price,
      'new_price', ph.new_price,
      'change_pct', ph.change_pct,
      'changed_at', ph.created_at,
      'source', ph.source
    ) ORDER BY ph.created_at DESC)
    FROM price_history ph WHERE ph.listing_id = l.id
  ) AS price_changes
FROM listings l
WHERE l.sale_price IS NOT NULL AND l.sale_price > 0
ORDER BY COALESCE(l.canonical_listing_id, l.id), l.source;

-- View: resumo por imóvel físico (1 row per property, all sources aggregated)
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

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_listings_canonical_active
  ON listings (canonical_listing_id) WHERE canonical_listing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_price_history_listing
  ON price_history (listing_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_listings_property_group
  ON listings (COALESCE(canonical_listing_id, id));

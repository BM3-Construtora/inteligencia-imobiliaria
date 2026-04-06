-- 012: Cross-platform price history & improved dedup tracking
-- Adds source tracking to price_history for cross-platform comparison

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

-- Create cross-platform price view: for each property (canonical group),
-- show all prices across all portals over time
CREATE OR REPLACE VIEW listing_price_timeline AS
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
  l.first_seen_at,
  l.last_seen_at,
  l.is_active,
  l.title,
  l.url
FROM listings l
WHERE l.sale_price IS NOT NULL AND l.sale_price > 0
ORDER BY COALESCE(l.canonical_listing_id, l.id), l.source;

-- Index for fast cross-platform lookups
CREATE INDEX IF NOT EXISTS idx_listings_canonical_active
  ON listings (canonical_listing_id) WHERE canonical_listing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_price_history_listing
  ON price_history (listing_id, created_at DESC);

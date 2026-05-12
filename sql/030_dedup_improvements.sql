-- 030: Dedup improvements for land listings
--
-- Adds flags/columns to support:
--   - area_inferred: total_area was extracted from title (not source-provided)
--   - listing_fingerprint: deterministic match shortcut
--     (neighborhood_norm + street_name_norm + number + area_bucket)

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS area_inferred BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS listing_fingerprint TEXT;

CREATE INDEX IF NOT EXISTS idx_listings_fingerprint
  ON listings (listing_fingerprint)
  WHERE listing_fingerprint IS NOT NULL;

COMMENT ON COLUMN listings.area_inferred IS
  'TRUE when total_area was extracted from title/description by area_parser, not provided by source';

COMMENT ON COLUMN listings.listing_fingerprint IS
  'Deterministic key for same-property detection: neigh|street|number|area_bucket';

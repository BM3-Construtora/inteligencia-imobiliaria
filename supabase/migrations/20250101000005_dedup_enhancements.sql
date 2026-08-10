-- 005_dedup_enhancements.sql — Enhanced dedup + ZAP Imóveis

-- New source portal
ALTER TYPE source_portal ADD VALUE IF NOT EXISTS 'zapimoveis';

-- Dedup columns on listings
ALTER TABLE listings ADD COLUMN IF NOT EXISTS image_phash TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS canonical_listing_id BIGINT REFERENCES listings(id);
ALTER TABLE listings ADD COLUMN IF NOT EXISTS normalized_address TEXT;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_listings_phash ON listings (image_phash) WHERE image_phash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listings_canonical ON listings (canonical_listing_id) WHERE canonical_listing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listings_zip ON listings (zip_code) WHERE zip_code IS NOT NULL;

-- CEP cache table
CREATE TABLE IF NOT EXISTS cep_cache (
    cep         TEXT PRIMARY KEY,
    street      TEXT,
    neighborhood TEXT,
    city        TEXT,
    state       TEXT,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

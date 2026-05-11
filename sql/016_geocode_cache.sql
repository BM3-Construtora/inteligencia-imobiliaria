-- Geocode cache — avoid re-geocoding same address.
-- Many listings share neighborhood/address; cache key on normalized query.

CREATE TABLE IF NOT EXISTS geocode_cache (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    query_hash      TEXT NOT NULL UNIQUE,   -- sha256 of normalized query
    query_text      TEXT NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    provider        TEXT NOT NULL,           -- 'nominatim' | 'mapbox' | 'manual'
    hit_count       INT NOT NULL DEFAULT 1,
    last_used_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geocode_cache_provider
    ON geocode_cache (provider);

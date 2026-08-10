-- 004_classification.sql — Classificação por tier e melhorias em neighborhoods

-- Market tier classification column
ALTER TABLE listings ADD COLUMN IF NOT EXISTS market_tier TEXT;
CREATE INDEX IF NOT EXISTS idx_listings_market_tier ON listings (market_tier) WHERE market_tier IS NOT NULL;

-- Neighborhood enhancements for map visualization
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS total_houses INT DEFAULT 0;
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS total_listings_by_tier JSONB DEFAULT '{}';

-- RLS: neighborhoods já tem public read via 003_rls_dashboard.sql
-- Garantir que market_tier é acessível no dashboard (listings já tem RLS)

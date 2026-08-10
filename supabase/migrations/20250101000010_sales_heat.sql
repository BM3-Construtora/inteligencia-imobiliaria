-- 010_sales_heat.sql — Sold estimates + market heat

CREATE TABLE IF NOT EXISTS sold_estimates (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id      BIGINT REFERENCES listings(id),
    last_price      NUMERIC(14,2),
    neighborhood    TEXT,
    property_type   TEXT,
    total_area      NUMERIC(10,2),
    days_on_market  INT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(listing_id)
);

-- RLS for dashboard
ALTER TABLE sold_estimates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read sold_estimates" ON sold_estimates FOR SELECT USING (true);

-- Market heat score
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS market_heat_score INT;

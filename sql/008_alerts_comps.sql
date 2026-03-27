-- 008_alerts_comps.sql — Saved searches / alerts + risk aggregation

-- Saved searches for personalized alerts
CREATE TABLE IF NOT EXISTS saved_searches (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    criteria        JSONB NOT NULL DEFAULT '{}',
    -- criteria example: {"property_type": ["land"], "neighborhoods": ["Centro"],
    --   "price_min": 50000, "price_max": 200000, "area_min": 200, "market_tier": ["terreno_economico"]}
    notify_telegram BOOLEAN DEFAULT TRUE,
    is_active       BOOLEAN DEFAULT TRUE,
    last_notified   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Risk aggregation on neighborhoods
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS avg_risk_score NUMERIC(3,2);
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS risk_breakdown JSONB DEFAULT '{}';

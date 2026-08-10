-- CRM-lite: track decisions on opportunities and improve company_projects.
-- Closes the feedback loop: oportunidades viram decisões reais → vira ground truth.

-- ============================================================
-- 1. opportunity_decisions — what the team did with each opportunity
-- ============================================================
CREATE TABLE IF NOT EXISTS opportunity_decisions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    opportunity_id  BIGINT REFERENCES opportunities(id) ON DELETE CASCADE,
    listing_id      BIGINT NOT NULL REFERENCES listings(id),
    decision        TEXT NOT NULL,    -- 'interested' | 'visited' | 'offered' | 'rejected' | 'acquired' | 'won_by_other'
    reason          TEXT,
    offered_price   NUMERIC(14, 2),
    actual_price    NUMERIC(14, 2),
    decided_at      DATE NOT NULL DEFAULT CURRENT_DATE,
    decided_by      TEXT,
    notes           TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opp_decisions_listing
    ON opportunity_decisions (listing_id);
CREATE INDEX IF NOT EXISTS idx_opp_decisions_decision
    ON opportunity_decisions (decision, decided_at DESC);

ALTER TABLE opportunity_decisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read opportunity_decisions"
    ON opportunity_decisions FOR SELECT USING (true);
CREATE POLICY "Service write opportunity_decisions"
    ON opportunity_decisions FOR INSERT WITH CHECK (true);
CREATE POLICY "Service update opportunity_decisions"
    ON opportunity_decisions FOR UPDATE USING (true);

-- ============================================================
-- 2. match_review_queue — feed for human confirm/reject UI
-- ============================================================
CREATE OR REPLACE VIEW match_review_queue AS
SELECT
    lm.id,
    lm.listing_a_id,
    lm.listing_b_id,
    lm.match_score,
    lm.decision_rule,
    lm.addr_score,
    lm.geo_distance_m,
    lm.price_diff_pct,
    lm.area_diff_pct,
    lm.bed_match,
    lm.bath_match,
    la.source        AS a_source,
    la.title         AS a_title,
    la.address       AS a_address,
    la.neighborhood  AS a_neighborhood,
    la.sale_price    AS a_price,
    la.total_area    AS a_area,
    la.url           AS a_url,
    lb.source        AS b_source,
    lb.title         AS b_title,
    lb.address       AS b_address,
    lb.neighborhood  AS b_neighborhood,
    lb.sale_price    AS b_price,
    lb.total_area    AS b_area,
    lb.url           AS b_url,
    lm.created_at
FROM listing_matches lm
JOIN listings la ON la.id = lm.listing_a_id
JOIN listings lb ON lb.id = lm.listing_b_id
WHERE lm.confirmed IS NULL
  AND lm.match_score BETWEEN 0.70 AND 0.90
ORDER BY lm.match_score, lm.created_at DESC;

-- ============================================================
-- 3. Extend company_projects (additive)
-- ============================================================
ALTER TABLE company_projects
    ADD COLUMN IF NOT EXISTS sale_price_per_unit NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS construction_months INT,
    ADD COLUMN IF NOT EXISTS roi_actual_pct NUMERIC(8, 2);

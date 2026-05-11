-- Split listing_matches.match_method into structured columns.
-- Old `match_method` had 400+ unique values like "addr_70%+price_5%+bed+bath".
-- New: numeric sub-scores + categorical decision_rule.

ALTER TABLE listing_matches
    ADD COLUMN IF NOT EXISTS addr_score    NUMERIC(4, 3),
    ADD COLUMN IF NOT EXISTS geo_distance_m NUMERIC(8, 1),
    ADD COLUMN IF NOT EXISTS price_diff_pct NUMERIC(5, 3),
    ADD COLUMN IF NOT EXISTS area_diff_pct  NUMERIC(5, 3),
    ADD COLUMN IF NOT EXISTS bed_match     BOOLEAN,
    ADD COLUMN IF NOT EXISTS bath_match    BOOLEAN,
    ADD COLUMN IF NOT EXISTS decision_rule TEXT;
    -- decision_rule values:
    --   'source_id_match'      — same source_id, definitive
    --   'loc+financial'        — addr/geo + price + area
    --   'loc+price+attrs'      — addr/geo + price + bed/bath
    --   'loc+area+attrs'       — addr/geo + area + bed/bath
    --   'financial+attrs'      — price + area + bed/bath, no location
    --   'geo_tight+attrs'      — <50m + bed + bath
    --   'manual_confirm'       — confirmed=TRUE by user

CREATE INDEX IF NOT EXISTS idx_listing_matches_rule
    ON listing_matches (decision_rule);

CREATE INDEX IF NOT EXISTS idx_listing_matches_score
    ON listing_matches (match_score DESC);

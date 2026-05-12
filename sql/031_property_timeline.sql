-- 031: Unified property timeline view
--
-- Materializes the full life of each physical property:
--   entry_date   → first_seen_at across all portal siblings
--   price_changes → ordered array of {date, old, new, pct, source}
--   exit_date    → deactivated_at when all siblings are inactive
--   exit_reason  → 'sold_estimate' | 'withdrawn' | 'active'
--   days_on_market → entry → exit (or today if still active)

CREATE OR REPLACE VIEW property_timeline AS
WITH
-- One row per physical property (canonical or standalone)
property_base AS (
  SELECT
    COALESCE(l.canonical_listing_id, l.id)  AS property_id,
    MIN(l.first_seen_at)                     AS entry_date,
    BOOL_OR(l.is_active)                     AS is_active,
    -- exit = latest deactivated_at when ALL siblings are inactive
    CASE WHEN BOOL_OR(l.is_active) THEN NULL
         ELSE MAX(l.deactivated_at)
    END                                      AS exit_date,
    -- aggregate across all siblings
    MIN(l.sale_price)                        AS min_price,
    MAX(l.sale_price)                        AS max_price,
    MAX(l.total_area)                        AS total_area,
    MIN(l.neighborhood)                      AS neighborhood,
    MIN(l.property_type)                     AS property_type,
    COUNT(DISTINCT l.source)                 AS num_sources,
    json_agg(DISTINCT l.source)              AS sources,
    -- canonical listing carries the best URL/title
    MIN(l.url)                               AS url,
    MIN(l.title)                             AS title
  FROM listings l
  WHERE l.sale_price IS NOT NULL
  GROUP BY COALESCE(l.canonical_listing_id, l.id)
),

-- Price changes ordered per property
price_changes AS (
  SELECT
    COALESCE(l.canonical_listing_id, l.id) AS property_id,
    json_agg(
      json_build_object(
        'date',    ph.detected_at,
        'old',     ph.old_price,
        'new',     ph.new_price,
        'pct',     ph.change_pct,
        'source',  ph.source
      ) ORDER BY ph.detected_at
    ) AS changes
  FROM price_history ph
  JOIN listings l ON l.id = ph.listing_id
  GROUP BY COALESCE(l.canonical_listing_id, l.id)
),

-- Sold estimate confidence
sold AS (
  SELECT
    COALESCE(l.canonical_listing_id, l.id) AS property_id,
    MAX(se.confidence)                      AS sold_confidence
  FROM sold_estimates se
  JOIN listings l ON l.id = se.listing_id
  GROUP BY COALESCE(l.canonical_listing_id, l.id)
)

SELECT
  pb.property_id,
  pb.neighborhood,
  pb.property_type,
  pb.total_area,
  pb.num_sources,
  pb.sources,
  pb.url,
  pb.title,

  -- Timeline
  pb.entry_date,
  pb.exit_date,
  pb.is_active,
  CASE
    WHEN pb.is_active              THEN 'active'
    WHEN s.sold_confidence IS NOT NULL THEN 'sold_estimate'
    ELSE                                    'withdrawn'
  END                              AS exit_reason,
  s.sold_confidence,

  EXTRACT(DAY FROM
    COALESCE(pb.exit_date, NOW()) - pb.entry_date
  )::INT                           AS days_on_market,

  -- Pricing
  pb.min_price,
  pb.max_price,
  ROUND((pb.max_price - pb.min_price)
    / NULLIF(pb.max_price, 0) * 100, 2) AS price_drop_pct,

  -- History
  COALESCE(pc.changes, '[]'::json) AS price_changes,
  json_array_length(COALESCE(pc.changes, '[]'::json)) AS num_price_changes

FROM property_base pb
LEFT JOIN price_changes pc USING (property_id)
LEFT JOIN sold s USING (property_id)
ORDER BY pb.entry_date DESC;

COMMENT ON VIEW property_timeline IS
  'One row per physical property. Aggregates all portal siblings, price history, and exit signal.';

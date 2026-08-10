-- 053_bairro_stats.sql
-- Painel do Bairro: transforma listings + property_timeline + avm_predictions
-- em resumo de decisão por bairro (preço por tipo, aluguel, absorção, oportunidade).
--
-- Duas materialized views:
--   bairro_tipo_stats  -> grão (bairro, property_type): preço, estoque e absorção
--   bairro_resumo      -> grão (bairro): totais, MCMV, acessibilidade, barganhas AVM
--
-- Refresh via refresh_bairro_stats() no fim do pipeline (ou cron diário).

-- ---------------------------------------------------------------------------
-- Normalização do nome do bairro (initcap + trim), reaproveitada nas views.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION norm_bairro(txt TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
  SELECT initcap(trim(COALESCE(NULLIF(txt, ''), '(sem bairro)')));
$$;

-- ---------------------------------------------------------------------------
-- bairro_tipo_stats: uma linha por (bairro, tipo de imóvel)
-- ---------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS bairro_tipo_stats CASCADE;
CREATE MATERIALIZED VIEW bairro_tipo_stats AS
WITH listing_agg AS (
  SELECT
    norm_bairro(neighborhood) AS bairro,
    property_type,
    COUNT(*)                                         AS total,
    COUNT(*) FILTER (WHERE is_active)                AS ativos,
    COUNT(*) FILTER (WHERE is_mcmv)                  AS mcmv,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sale_price)
      FILTER (WHERE is_active AND sale_price IS NOT NULL)   AS preco_mediano,
    ROUND(AVG(sale_price) FILTER (WHERE is_active AND sale_price IS NOT NULL), 2) AS preco_medio,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY price_per_m2)
      FILTER (WHERE is_active AND price_per_m2 IS NOT NULL) AS ppm2_mediano,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY total_area)
      FILTER (WHERE is_active AND total_area IS NOT NULL)   AS area_mediana,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY rent_price)
      FILTER (WHERE rent_price > 0)                         AS aluguel_mediano,
    COUNT(*) FILTER (WHERE rent_price > 0)                  AS aluguel_n
  FROM listings
  GROUP BY 1, 2
),
absorcao_agg AS (
  SELECT
    norm_bairro(neighborhood) AS bairro,
    property_type,
    COUNT(*)                                         AS hist_total,
    COUNT(*) FILTER (WHERE is_active = false)         AS saiu_do_ar,
    ROUND(AVG(days_on_market) FILTER (WHERE is_active = false AND days_on_market IS NOT NULL), 1) AS dias_medio,
    COUNT(*) FILTER (WHERE price_drop_pct > 0)        AS baixaram_preco
  FROM property_timeline
  GROUP BY 1, 2
)
SELECT
  COALESCE(l.bairro, a.bairro)               AS bairro,
  COALESCE(l.property_type, a.property_type) AS property_type,
  l.total, l.ativos, l.mcmv,
  l.preco_mediano, l.preco_medio, l.ppm2_mediano, l.area_mediana,
  l.aluguel_mediano, l.aluguel_n,
  a.hist_total, a.saiu_do_ar,
  CASE WHEN a.hist_total > 0
       THEN ROUND(100.0 * a.saiu_do_ar / a.hist_total, 1) END AS taxa_saida_pct,
  a.dias_medio, a.baixaram_preco
FROM listing_agg l
FULL OUTER JOIN absorcao_agg a
  ON l.bairro = a.bairro AND l.property_type = a.property_type;

CREATE UNIQUE INDEX idx_bairro_tipo_stats ON bairro_tipo_stats (bairro, property_type);

-- ---------------------------------------------------------------------------
-- bairro_resumo: uma linha por bairro (o cabeçalho da ficha)
-- ---------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS bairro_resumo CASCADE;
CREATE MATERIALIZED VIEW bairro_resumo AS
WITH l AS (
  SELECT
    norm_bairro(neighborhood) AS bairro,
    COUNT(*)                             AS listings_total,
    COUNT(*) FILTER (WHERE is_active)    AS listings_ativos,
    COUNT(*) FILTER (WHERE is_mcmv)      AS mcmv,
    ROUND(AVG(mcmv_accessibility_score) FILTER (WHERE mcmv_accessibility_score IS NOT NULL), 1) AS acessibilidade_media,
    COUNT(*) FILTER (WHERE mcmv_accessibility_score IS NOT NULL) AS acc_n
  FROM listings
  GROUP BY 1
),
avm AS (
  SELECT
    norm_bairro(li.neighborhood) AS bairro,
    COUNT(*)                                       AS avm_total,
    COUNT(*) FILTER (WHERE p.is_undervalued)       AS avm_under
  FROM avm_predictions p
  JOIN listings li ON li.id = p.listing_id
  GROUP BY 1
)
SELECT
  l.bairro,
  l.listings_total, l.listings_ativos, l.mcmv,
  CASE WHEN l.listings_total > 0
       THEN ROUND(100.0 * l.mcmv / l.listings_total, 1) END AS mcmv_pct,
  l.acessibilidade_media, l.acc_n,
  COALESCE(avm.avm_total, 0) AS avm_total,
  COALESCE(avm.avm_under, 0) AS avm_under
FROM l
LEFT JOIN avm ON avm.bairro = l.bairro;

CREATE UNIQUE INDEX idx_bairro_resumo ON bairro_resumo (bairro);

-- ---------------------------------------------------------------------------
-- Refresh atômico (CONCURRENTLY exige o índice único acima).
-- Chamar no fim do pipeline: SELECT refresh_bairro_stats();
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_bairro_stats()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY bairro_tipo_stats;
  REFRESH MATERIALIZED VIEW CONCURRENTLY bairro_resumo;
END;
$$;

-- 20250101000059_prefeitura_itbi_alvaras.sql
-- Ingestão dos extratos oficiais da Prefeitura de Marília (recebidos 2026-08-27):
--   itbi_loteamento -> Total de ITBI por loteamento, 01/01/2015 a 17/08/2026
--                      (agregado: qtde de transações + valor arrecadado; sem datas
--                      nem transações individuais — série anual já foi pedida).
--   alvaras         -> Projetos/Obras: alvará e habite-se por inscrição cadastral
--                      (1940 a ago/2024, ~49k linhas; habite-se ~98% vazio na fonte).
--
-- Dado público municipal, sem edge competitivo (mesmo racional de
-- parcelamento_solo_marilia, migration 058): RLS + SELECT anônimo.
-- Escrita só via service_role (loader: scripts/load_prefeitura_files.py).
--
-- bairro_liquidez cruza vendas reais (ITBI) com anúncios ativos (listings) e
-- entrega a métrica nova: meses de estoque por bairro.

CREATE TABLE IF NOT EXISTS itbi_loteamento (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  loteamento       TEXT NOT NULL,            -- nome cru do extrato da prefeitura
  qtde_itbi        INTEGER NOT NULL,
  valor_arrecadado NUMERIC(14,2) NOT NULL,
  periodo_inicio   DATE NOT NULL,
  periodo_fim      DATE NOT NULL,
  -- de-para para o grão dos painéis: mesmo formato de norm_bairro(neighborhood).
  -- Preenchido pelo matching fuzzy do loader; NULL = sem correspondente nos
  -- listings (ponto cego do scraping ou nome ainda não revisado).
  bairro_canonico  TEXT,
  match_confidence NUMERIC(3,2),             -- jaccard do matching (1.00 = exato)
  source_file      TEXT,
  imported_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (loteamento, periodo_inicio, periodo_fim)
);

CREATE INDEX IF NOT EXISTS idx_itbi_loteamento_bairro ON itbi_loteamento (bairro_canonico);

CREATE TABLE IF NOT EXISTS alvaras (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  inscricao       TEXT NOT NULL,             -- inscrição cadastral municipal (chave p/ IPTU)
  alvara_dt       DATE,                      -- NULL quando a data na fonte é impossível
  alvara_dt_raw   TEXT,                      -- valor original quando alvara_dt = NULL
  processo_adm    TEXT,
  cep             TEXT,
  bairro_raw      TEXT,                      -- texto livre da prefeitura (~1.6k variantes)
  logradouro      TEXT,
  numero          TEXT,
  complemento     TEXT,
  tipo_edificacao TEXT,                      -- ResidencialUnifamiliar, MoradiaEconomica, ...
  area_construida NUMERIC(12,2),
  area_terreno    NUMERIC(12,2),
  habitese_dt     DATE,
  habitese_numero TEXT,
  data_suspeita   BOOLEAN NOT NULL DEFAULT false,  -- ano fora de 1900..2026 na fonte
  source_file     TEXT,
  imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alvaras_inscricao ON alvaras (inscricao);
CREATE INDEX IF NOT EXISTS idx_alvaras_dt        ON alvaras (alvara_dt);
CREATE INDEX IF NOT EXISTS idx_alvaras_bairro    ON alvaras (bairro_raw);
CREATE INDEX IF NOT EXISTS idx_alvaras_tipo      ON alvaras (tipo_edificacao);

ALTER TABLE itbi_loteamento ENABLE ROW LEVEL SECURITY;
ALTER TABLE alvaras         ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public read on itbi_loteamento" ON itbi_loteamento;
CREATE POLICY "Allow public read on itbi_loteamento"
    ON itbi_loteamento FOR SELECT TO anon
    USING (true);

DROP POLICY IF EXISTS "Allow public read on alvaras" ON alvaras;
CREATE POLICY "Allow public read on alvaras"
    ON alvaras FOR SELECT TO anon
    USING (true);

-- ---------------------------------------------------------------------------
-- bairro_liquidez: vendas reais (ITBI) x estoque anunciado (listings ativos).
--   vendas_ano      -> transações reais / ano, média do período do extrato
--   itbi_medio      -> ITBI médio por transação
--   ticket_estimado -> itbi_medio / 0.02 (alíquota assumida de 2% — CONFIRMAR
--                      no código tributário antes de exibir como valor absoluto;
--                      leitura relativa entre bairros independe da alíquota)
--   meses_estoque   -> anúncios de venda ativos / (vendas_ano / 12)
-- View simples (não materializada): itbi_loteamento é pequena (~500 linhas)
-- e o agregado de listings usa índice; sem necessidade de refresh.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW bairro_liquidez AS
WITH itbi AS (
  SELECT
    bairro_canonico AS bairro,
    SUM(qtde_itbi)                                    AS vendas_periodo,
    ROUND(SUM(
      qtde_itbi::numeric
      / GREATEST((periodo_fim - periodo_inicio) / 365.25, 1)
    ), 1)                                             AS vendas_ano,
    ROUND(SUM(valor_arrecadado) / SUM(qtde_itbi), 2)  AS itbi_medio,
    ROUND(SUM(valor_arrecadado) / SUM(qtde_itbi) / 0.02, 0) AS ticket_estimado,
    MIN(match_confidence)                             AS match_confidence_min
  FROM itbi_loteamento
  WHERE bairro_canonico IS NOT NULL
  GROUP BY bairro_canonico
),
ativos AS (
  SELECT
    norm_bairro(neighborhood) AS bairro,
    COUNT(*)                  AS anuncios_ativos
  FROM listings
  WHERE is_active AND business_type = 'sale'
  GROUP BY 1
)
SELECT
  i.bairro,
  i.vendas_periodo,
  i.vendas_ano,
  i.itbi_medio,
  i.ticket_estimado,
  COALESCE(a.anuncios_ativos, 0) AS anuncios_ativos,
  CASE WHEN i.vendas_ano > 0
       THEN ROUND(COALESCE(a.anuncios_ativos, 0) / (i.vendas_ano / 12.0), 1)
  END AS meses_estoque,
  i.match_confidence_min
FROM itbi i
LEFT JOIN ativos a USING (bairro);

COMMENT ON TABLE itbi_loteamento IS
  'ITBI agregado por loteamento (extrato oficial da Prefeitura de Marília). Vendas REAIS, não anúncios.';
COMMENT ON TABLE alvaras IS
  'Alvarás de construção e habite-se por inscrição cadastral (extrato oficial da Prefeitura de Marília).';
COMMENT ON VIEW bairro_liquidez IS
  'Liquidez por bairro: vendas reais/ano (ITBI) vs anúncios ativos = meses de estoque.';

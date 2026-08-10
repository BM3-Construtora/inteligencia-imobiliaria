-- ============================================================
-- apply_v2_migrations.sql — bundle ordenado das migrations V2
-- NÃO aplicadas em produção (confirmado 2026-08-10: só 001/028/051
-- estavam no banco). Cole INTEIRO no SQL editor do Supabase.
-- Idempotente (CREATE ... IF NOT EXISTS / OR REPLACE). Ordem importa:
-- 042 cria census_sectors/economic_centroids; 045 e 052 dependem dele.
-- Requer extensões postgis (042) e vector (047).
-- ============================================================


-- ==================== sql/042_postgis.sql ====================
-- Ativa PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Coluna geom em listings (gerada automaticamente de lat/lng existentes)
ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);

UPDATE listings
SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND geom IS NULL;

CREATE INDEX IF NOT EXISTS idx_listings_geom ON listings USING GIST (geom);

-- Tabela de POIs (Points of Interest) via OSMnx
CREATE TABLE IF NOT EXISTS pois (
  id            SERIAL PRIMARY KEY,
  osm_id        TEXT UNIQUE,
  category      TEXT NOT NULL,  -- hospital, university, school, clinic, pharmacy, supermarket, bus_stop, park, industrial
  subcategory   TEXT,           -- amenity, shop, highway, etc
  name          TEXT,
  address       TEXT,
  latitude      DOUBLE PRECISION,
  longitude     DOUBLE PRECISION,
  geom          geometry(Point, 4326),
  source        TEXT DEFAULT 'osmnx',
  collected_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pois_geom ON pois USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_pois_category ON pois (category);

-- Tabela de setores censitários IBGE 2022 (polígonos)
CREATE TABLE IF NOT EXISTS census_sectors (
  id                  SERIAL PRIMARY KEY,
  sector_code         TEXT UNIQUE NOT NULL,
  municipality_code   TEXT DEFAULT '3529005',
  geom                geometry(MultiPolygon, 4326),
  renda_per_capita    NUMERIC,
  total_domicilios    INTEGER,
  populacao           INTEGER,
  densidade_demo      NUMERIC,  -- pessoas/km²
  area_km2            NUMERIC,
  source_year         INTEGER DEFAULT 2022,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_census_sectors_geom ON census_sectors USING GIST (geom);

-- Tabela de centros econômicos (calculados empiricamente)
CREATE TABLE IF NOT EXISTS economic_centroids (
  id          SERIAL PRIMARY KEY,
  name        TEXT UNIQUE NOT NULL,  -- 'commercial', 'health', 'education', 'industrial'
  label_pt    TEXT,                  -- 'Polo Comercial', 'Polo de Saúde', etc
  latitude    DOUBLE PRECISION,
  longitude   DOUBLE PRECISION,
  geom        geometry(Point, 4326),
  radius_m    INTEGER DEFAULT 2000,  -- raio de influência em metros
  description TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Inserir centros econômicos reais de Marília
INSERT INTO economic_centroids (name, label_pt, latitude, longitude, geom, radius_m, description) VALUES
  ('commercial',  'Polo Comercial',     -22.2163, -49.9491, ST_SetSRID(ST_MakePoint(-49.9491, -22.2163), 4326), 1500, 'Corredor Av. Sampaio Vidal + Shopping Marília'),
  ('health',      'Polo de Saúde',      -22.2089, -49.9433, ST_SetSRID(ST_MakePoint(-49.9433, -22.2089), 4326), 1000, 'Hospital Amaral Carvalho + Famema + Hospitais regionais'),
  ('education',   'Polo Educacional',   -22.2237, -49.9601, ST_SetSRID(ST_MakePoint(-49.9601, -22.2237), 4326), 1200, 'Unimar + Unesp + Fatec + Unip'),
  ('industrial',  'Polo Industrial',    -22.1978, -49.9752, ST_SetSRID(ST_MakePoint(-49.9752, -22.1978), 4326), 2000, 'Distrito Industrial Sul + Logística SP-333'),
  ('historic',    'Centro Histórico',   -22.2141, -49.9466, ST_SetSRID(ST_MakePoint(-49.9466, -22.2141), 4326), 800,  'Praça da Bandeira + Marco Zero')
ON CONFLICT (name) DO UPDATE SET
  latitude = EXCLUDED.latitude,
  longitude = EXCLUDED.longitude,
  geom = EXCLUDED.geom,
  description = EXCLUDED.description;

-- Tabela de proximidades pré-calculadas (listing → POI mais próximo por categoria)
CREATE TABLE IF NOT EXISTS listing_poi_proximity (
  id              SERIAL PRIMARY KEY,
  listing_id      INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  category        TEXT NOT NULL,
  poi_id          INTEGER REFERENCES pois(id),
  distance_m      DOUBLE PRECISION,
  poi_name        TEXT,
  calculated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(listing_id, category)
);
CREATE INDEX IF NOT EXISTS idx_proximity_listing ON listing_poi_proximity (listing_id);

-- View útil: listings com features geoespaciais
CREATE OR REPLACE VIEW listings_with_geo AS
SELECT
  l.id,
  l.sale_price,
  l.total_area,
  l.price_per_m2,
  l.neighborhood,
  l.property_type,
  l.is_active,
  l.latitude,
  l.longitude,
  l.geom,
  -- Distâncias aos centros econômicos
  ST_Distance(l.geom::geography, ec_com.geom::geography) AS dist_commercial_m,
  ST_Distance(l.geom::geography, ec_health.geom::geography) AS dist_health_m,
  ST_Distance(l.geom::geography, ec_edu.geom::geography) AS dist_education_m,
  ST_Distance(l.geom::geography, ec_ind.geom::geography) AS dist_industrial_m,
  -- POI mais próximos
  prox_hospital.distance_m AS dist_hospital_m,
  prox_school.distance_m AS dist_school_m,
  prox_bus.distance_m AS dist_bus_stop_m,
  prox_super.distance_m AS dist_supermarket_m
FROM listings l
LEFT JOIN economic_centroids ec_com ON ec_com.name = 'commercial'
LEFT JOIN economic_centroids ec_health ON ec_health.name = 'health'
LEFT JOIN economic_centroids ec_edu ON ec_edu.name = 'education'
LEFT JOIN economic_centroids ec_ind ON ec_ind.name = 'industrial'
LEFT JOIN listing_poi_proximity prox_hospital ON prox_hospital.listing_id = l.id AND prox_hospital.category = 'hospital'
LEFT JOIN listing_poi_proximity prox_school ON prox_school.listing_id = l.id AND prox_school.category = 'school'
LEFT JOIN listing_poi_proximity prox_bus ON prox_bus.listing_id = l.id AND prox_bus.category = 'bus_stop'
LEFT JOIN listing_poi_proximity prox_super ON prox_super.listing_id = l.id AND prox_super.category = 'supermarket'
WHERE l.geom IS NOT NULL;


-- ==================== sql/043_audit_log.sql ====================
-- Data Audit Log — rastreia fluxo de dados por etapa do pipeline
-- Implementa requisito LGPD: Art. 37 (registro de operações de tratamento)
CREATE TABLE IF NOT EXISTS data_audit_log (
  id                BIGSERIAL PRIMARY KEY,
  logged_at         TIMESTAMPTZ DEFAULT NOW(),
  pipeline_step     TEXT NOT NULL,    -- 'collect', 'normalize', 'enrich_llm', 'score', 'notify'
  agent_name        TEXT,             -- 'osm_collector', 'hunter', 'price_model', etc
  data_type         TEXT NOT NULL,    -- 'imovel', 'poi', 'obra_publica', 'habite_se', etc
  source_system     TEXT NOT NULL,    -- 'vivareal', 'zapimóveis', 'prefeitura_marilia', 'gemini_api', 'ibge'
  records_count     INTEGER DEFAULT 0,
  legal_basis       TEXT,             -- 'dado_publico', 'legitimo_interesse', 'contrato', 'consentimento'
  external_transfer BOOLEAN DEFAULT FALSE,  -- TRUE se dado saiu do Brasil
  transfer_safeguard TEXT,            -- 'vertex_ai_dpa', 'standard_contractual_clauses', NULL
  contains_pii      BOOLEAN DEFAULT FALSE,  -- Personally Identifiable Information
  data_hash         TEXT,             -- hash dos dados (não os dados em si)
  retention_until   DATE,             -- data de expiração
  metadata          JSONB DEFAULT '{}'::jsonb,
  run_id            INTEGER           -- FK para agent_runs (opcional)
);

-- Índices para consulta de compliance
CREATE INDEX IF NOT EXISTS idx_audit_log_step ON data_audit_log (pipeline_step);
CREATE INDEX IF NOT EXISTS idx_audit_log_source ON data_audit_log (source_system);
CREATE INDEX IF NOT EXISTS idx_audit_log_logged_at ON data_audit_log (logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_external ON data_audit_log (external_transfer) WHERE external_transfer = TRUE;

-- View para dashboard de compliance
CREATE OR REPLACE VIEW audit_compliance_summary AS
SELECT
  source_system,
  data_type,
  legal_basis,
  external_transfer,
  transfer_safeguard,
  contains_pii,
  COUNT(*) AS log_entries,
  SUM(records_count) AS total_records,
  MAX(logged_at) AS last_seen,
  MIN(logged_at) AS first_seen
FROM data_audit_log
GROUP BY source_system, data_type, legal_basis, external_transfer, transfer_safeguard, contains_pii
ORDER BY total_records DESC;

-- Tabela de políticas de retenção por fonte de dado
CREATE TABLE IF NOT EXISTS data_retention_policies (
  id            SERIAL PRIMARY KEY,
  source_system TEXT UNIQUE NOT NULL,
  data_type     TEXT NOT NULL,
  legal_basis   TEXT NOT NULL,
  retention_days INTEGER NOT NULL,  -- -1 = indefinido (dado público)
  contains_pii  BOOLEAN DEFAULT FALSE,
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Políticas padrão (baseadas em análise LGPD dos agentes especialistas)
INSERT INTO data_retention_policies (source_system, data_type, legal_basis, retention_days, contains_pii, notes) VALUES
  ('vivareal',           'listing',        'legitimo_interesse',  730,  FALSE, 'Dado público de portal. Retenção 24 meses.'),
  ('zapimoveis',         'listing',        'legitimo_interesse',  730,  FALSE, 'Dado público de portal. Retenção 24 meses.'),
  ('chavesnamao',        'listing',        'legitimo_interesse',  730,  FALSE, 'Dado público de portal.'),
  ('uniao_imobiliaria',  'listing',        'contrato',            730,  FALSE, 'API pública com ToS permissivo.'),
  ('toca_imoveis',       'listing',        'contrato',            730,  FALSE, 'Parceiro com acesso explícito.'),
  ('prefeitura_marilia', 'habite_se',      'dado_publico',        -1,   FALSE, 'Ato administrativo publicado no DOM. Retenção indefinida.'),
  ('prefeitura_marilia', 'alvara',         'dado_publico',        -1,   FALSE, 'Ato administrativo publicado no DOM.'),
  ('prefeitura_marilia', 'obra_publica',   'dado_publico',        -1,   FALSE, 'Dado de transparência pública.'),
  ('prefeitura_marilia', 'itbi',           'dado_publico',        1825, FALSE, 'Dado tributário público. Retenção 5 anos (prescrição civil).'),
  ('ibge',               'demografico',    'dado_publico',        -1,   FALSE, 'Censo e estimativas IBGE. Retenção indefinida.'),
  ('ibge',               'setor_censitario','dado_publico',       -1,   FALSE, 'Malha censitária geoespacial.'),
  ('osmnx',              'poi',            'dado_publico',        -1,   FALSE, 'OpenStreetMap, licença ODbL.'),
  ('gemini_api',         'enrichment',     'contrato',            30,   FALSE, 'Processamento LLM. Não armazena resposta da API — só saída processada. Retenção 30 dias para debugging.'),
  ('sinapi',             'indice',         'dado_publico',        -1,   FALSE, 'Índice IBGE público.'),
  ('cepea_esalq',        'commodity',      'dado_publico',        -1,   FALSE, 'Preços agrícolas ESALQ-USP público.')
ON CONFLICT (source_system) DO NOTHING;


-- ==================== sql/044_alvaras_eiv.sql ====================
-- 044_alvaras_eiv.sql — Alvarás de aprovação + EIVs — Marília-SP
-- Alvarás Seção III-A DOM-MAR: sinal 18-36 meses antes do habite-se.
-- EIV (Estudo de Impacto de Vizinhança): obrigatório para glebas >5000m² — sinal de empreendimentos grandes.
-- radar_concorrencia view: union das duas fontes para dashboard de pipeline competitivo.

CREATE TABLE IF NOT EXISTS alvaras_marilia (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT NOT NULL UNIQUE,           -- SHA1(edition_id:processo|alvara|endereco:area)
    publication_date    DATE,
    numero_alvara       TEXT,
    numero_processo     TEXT,
    tipo_alvara         TEXT,                           -- aprovacao_projeto | licenca_construcao | reforma | demolicao
    uso                 TEXT,                           -- residencial | comercial | industrial | misto
    requerente          TEXT,                           -- nome da construtora/pessoa
    cnpj_cpf            TEXT,
    endereco            TEXT,
    neighborhood        TEXT,
    area_construida_m2  NUMERIC,
    unidades            INTEGER,
    pavimentos          INTEGER,
    city                TEXT NOT NULL DEFAULT 'Marília',
    state               TEXT NOT NULL DEFAULT 'SP',
    raw_payload         JSONB,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alvaras_publication_date
    ON alvaras_marilia (publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_alvaras_neighborhood
    ON alvaras_marilia (neighborhood);
CREATE INDEX IF NOT EXISTS idx_alvaras_tipo
    ON alvaras_marilia (tipo_alvara);
CREATE INDEX IF NOT EXISTS idx_alvaras_requerente
    ON alvaras_marilia (requerente);
CREATE INDEX IF NOT EXISTS idx_alvaras_processo
    ON alvaras_marilia (numero_processo)
    WHERE numero_processo IS NOT NULL;

ALTER TABLE alvaras_marilia ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on alvaras_marilia" ON alvaras_marilia;
CREATE POLICY "service_role full access on alvaras_marilia"
    ON alvaras_marilia FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on alvaras_marilia" ON alvaras_marilia;
CREATE POLICY "Allow public read on alvaras_marilia"
    ON alvaras_marilia FOR SELECT TO anon
    USING (true);

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS eiv_marilia (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT NOT NULL UNIQUE,
    publication_date    DATE,
    numero_eiv          TEXT,
    numero_processo     TEXT,
    requerente          TEXT,
    endereco            TEXT,
    neighborhood        TEXT,
    area_gleba_m2       NUMERIC,
    unidades            INTEGER,
    resultado           TEXT,                           -- aprovado | reprovado | em_analise
    city                TEXT NOT NULL DEFAULT 'Marília',
    state               TEXT NOT NULL DEFAULT 'SP',
    raw_payload         JSONB,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eiv_publication_date
    ON eiv_marilia (publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_eiv_neighborhood
    ON eiv_marilia (neighborhood);
CREATE INDEX IF NOT EXISTS idx_eiv_resultado
    ON eiv_marilia (resultado);

ALTER TABLE eiv_marilia ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on eiv_marilia" ON eiv_marilia;
CREATE POLICY "service_role full access on eiv_marilia"
    ON eiv_marilia FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on eiv_marilia" ON eiv_marilia;
CREATE POLICY "Allow public read on eiv_marilia"
    ON eiv_marilia FOR SELECT TO anon
    USING (true);

-- ---------------------------------------------------------------------------
-- Radar de concorrência: alvarás + EIVs últimos 24 meses
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW radar_concorrencia AS
SELECT
    'alvara'            AS tipo_sinal,
    source_id,
    publication_date,
    requerente,
    neighborhood,
    area_construida_m2  AS area_m2,
    unidades,
    tipo_alvara         AS subtipo,
    NULL::TEXT          AS resultado
FROM alvaras_marilia
WHERE publication_date >= CURRENT_DATE - INTERVAL '24 months'
  AND tipo_alvara IN ('aprovacao_projeto', 'licenca_construcao')

UNION ALL

SELECT
    'eiv'               AS tipo_sinal,
    source_id,
    publication_date,
    requerente,
    neighborhood,
    area_gleba_m2       AS area_m2,
    unidades,
    'eiv'               AS subtipo,
    resultado
FROM eiv_marilia
WHERE publication_date >= CURRENT_DATE - INTERVAL '24 months'

ORDER BY publication_date DESC;


-- ==================== sql/045_ibge_sectors.sql ====================
-- Setores Censitários IBGE 2022 com dados demográficos
-- Polígonos baixados via API: https://servicodados.ibge.gov.br/api/v3/malhas/municipios/3529005
-- Dados de renda: IBGE Censo 2022 (via CNEFE e resultados preliminares)

-- A tabela census_sectors já foi criada no 042_postgis.sql
-- Este arquivo adiciona colunas extras e função de join espacial

-- Adicionar colunas de dados socioeconômicos
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS renda_media_domiciliar NUMERIC;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS pessoas_responsavel_alfabetizadas INTEGER;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS domicilios_alugados INTEGER;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS domicilios_proprios INTEGER;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS media_moradores NUMERIC;

-- Função PostgreSQL para enriquecer listing com dados do setor censitário
CREATE OR REPLACE FUNCTION enrich_listing_with_census(p_listing_id INTEGER)
RETURNS VOID AS $$
BEGIN
  UPDATE listings l
  SET
    census_sector_code = cs.sector_code,
    census_renda_pc = cs.renda_per_capita,
    census_densidade = cs.densidade_demo,
    census_domicilios = cs.total_domicilios,
    updated_at = NOW()
  FROM census_sectors cs
  WHERE l.id = p_listing_id
    AND l.geom IS NOT NULL
    AND ST_Within(l.geom, cs.geom);
END;
$$ LANGUAGE plpgsql;

-- Adicionar colunas de censo em listings (se não existirem)
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_sector_code TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_renda_pc NUMERIC;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_densidade NUMERIC;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_domicilios INTEGER;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS mcmv_accessibility_score NUMERIC;

-- Índice para join espacial
CREATE INDEX IF NOT EXISTS idx_census_sectors_geom_gist ON census_sectors USING GIST (geom);


-- ==================== sql/046_construtora_rating.sql ====================
-- Rating de Construtoras baseado em dados públicos observáveis
-- Fontes: DOM-MAR (habite_se, alvaras), TJSP (processos)
-- Lógica: replicar critérios de habilitação da Caixa com dados públicos

CREATE TABLE IF NOT EXISTS construtoras_rating (
  id                      SERIAL PRIMARY KEY,
  nome                    TEXT NOT NULL,
  cnpj                    TEXT UNIQUE,
  -- Métricas de desempenho (calculadas automaticamente)
  total_alvaras           INTEGER DEFAULT 0,    -- alvarás emitidos histórico
  total_habite_se         INTEGER DEFAULT 0,    -- habite-se emitidos histórico
  total_eivs              INTEGER DEFAULT 0,    -- EIVs publicados
  alvaras_sem_habite_se   INTEGER DEFAULT 0,    -- alvarás sem habite-se correspondente (risco)
  tempo_medio_obra_dias   NUMERIC,              -- delta médio alvará→habite-se em dias
  tempo_min_obra_dias     NUMERIC,
  tempo_max_obra_dias     NUMERIC,
  -- Bairros de atuação
  bairros_atuacao         TEXT[],               -- array de bairros onde já atuou
  bairro_principal        TEXT,                 -- bairro com maior concentração
  -- Scores calculados
  score_entrega           NUMERIC,              -- 0-100: taxa de conclusão (habite-se/alvarás)
  score_prazo             NUMERIC,              -- 0-100: quão dentro do prazo entrega
  score_volume            NUMERIC,              -- 0-100: volume normalizado de obras
  score_geral             NUMERIC,              -- 0-100: composto dos três
  tier                    TEXT,                 -- 'A' (>80), 'B' (60-80), 'C' (40-60), 'D' (<40)
  -- Sinais de risco
  tem_embargo             BOOLEAN DEFAULT FALSE,
  tem_processo_tjsp       BOOLEAN DEFAULT FALSE,
  ultima_atividade_date   DATE,
  -- Metadata
  primeiro_registro_date  DATE,
  calculado_em            TIMESTAMPTZ DEFAULT NOW(),
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rating_score ON construtoras_rating (score_geral DESC);
CREATE INDEX IF NOT EXISTS idx_rating_tier ON construtoras_rating (tier);
CREATE INDEX IF NOT EXISTS idx_rating_bairro ON construtoras_rating USING GIN (bairros_atuacao);

-- View: "Construtoras Ativas em Marília" (últimos 24 meses)
CREATE OR REPLACE VIEW construtoras_ativas AS
SELECT
  cr.*,
  CASE
    WHEN cr.ultima_atividade_date >= CURRENT_DATE - INTERVAL '12 months' THEN 'ativa'
    WHEN cr.ultima_atividade_date >= CURRENT_DATE - INTERVAL '24 months' THEN 'recente'
    ELSE 'inativa'
  END AS status_atividade
FROM construtoras_rating cr
WHERE cr.total_alvaras > 0 OR cr.total_habite_se > 0
ORDER BY cr.score_geral DESC NULLS LAST;

-- View: "Mapa de Atuação" — onde cada construtora está ativa por bairro
CREATE OR REPLACE VIEW construtoras_por_bairro AS
SELECT
  a.neighborhood,
  a.requerente AS construtora,
  a.cnpj_cpf AS cnpj,
  COUNT(*) AS alvaras_no_bairro,
  MAX(a.publication_date) AS ultimo_alvara,
  SUM(a.area_construida_m2) AS area_total_aprovada_m2
FROM alvaras_marilia a
WHERE a.neighborhood IS NOT NULL
  AND a.requerente IS NOT NULL
  AND a.publication_date >= CURRENT_DATE - INTERVAL '36 months'
GROUP BY a.neighborhood, a.requerente, a.cnpj_cpf
ORDER BY a.neighborhood, alvaras_no_bairro DESC;


-- ==================== sql/047_pgvector.sql ====================
-- 047_pgvector.sql — Reativa embeddings via pgvector (021_remove_embeddings.sql os removeu)
-- Usado para: busca semântica de imóveis similares, RAG de documentos municipais (CMDU, Plano Diretor)

CREATE EXTENSION IF NOT EXISTS vector;

-- Embeddings de listings (busca de similares, clustering de bairro)
CREATE TABLE IF NOT EXISTS listing_embeddings (
  id              BIGSERIAL PRIMARY KEY,
  listing_id      BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  embedding       vector(768),       -- Gemini text-embedding-004 = 768 dims
  content_hash    TEXT,              -- SHA1 do texto que gerou o embedding
  model           TEXT DEFAULT 'text-embedding-004',
  embedded_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(listing_id)
);
CREATE INDEX IF NOT EXISTS idx_listing_emb_ivfflat
  ON listing_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Embeddings de documentos municipais (CMDU atas, Plano Diretor, EIV pareceres)
CREATE TABLE IF NOT EXISTS document_embeddings (
  id              BIGSERIAL PRIMARY KEY,
  source_table    TEXT NOT NULL,     -- 'cmdu_atas', 'eiv_marilia', 'alvaras_marilia', 'plano_diretor'
  source_id       TEXT NOT NULL,     -- source_id da tabela de origem
  chunk_index     INTEGER DEFAULT 0, -- se o doc foi dividido em chunks
  chunk_text      TEXT NOT NULL,     -- texto do chunk (para exibição)
  embedding       vector(768),
  content_hash    TEXT,
  model           TEXT DEFAULT 'text-embedding-004',
  embedded_at     TIMESTAMPTZ DEFAULT NOW(),
  metadata        JSONB DEFAULT '{}'::jsonb,
  UNIQUE(source_table, source_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_doc_emb_ivfflat
  ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);
CREATE INDEX IF NOT EXISTS idx_doc_emb_source ON document_embeddings (source_table, source_id);

-- Função: buscar documentos similares a uma query
CREATE OR REPLACE FUNCTION search_documents(
  query_embedding vector(768),
  source_filter   TEXT DEFAULT NULL,   -- filtrar por source_table (ex: 'cmdu_atas')
  match_count     INTEGER DEFAULT 10,
  similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
  source_table  TEXT,
  source_id     TEXT,
  chunk_index   INTEGER,
  chunk_text    TEXT,
  similarity    FLOAT,
  metadata      JSONB
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    de.source_table,
    de.source_id,
    de.chunk_index,
    de.chunk_text,
    1 - (de.embedding <=> query_embedding) AS similarity,
    de.metadata
  FROM document_embeddings de
  WHERE (source_filter IS NULL OR de.source_table = source_filter)
    AND 1 - (de.embedding <=> query_embedding) >= similarity_threshold
  ORDER BY de.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Função: buscar listings similares a um listing de referência
CREATE OR REPLACE FUNCTION find_similar_listings(
  p_listing_id    BIGINT,
  match_count     INTEGER DEFAULT 5,
  similarity_threshold FLOAT DEFAULT 0.8
)
RETURNS TABLE (
  listing_id    BIGINT,
  similarity    FLOAT
)
LANGUAGE plpgsql AS $$
DECLARE
  ref_embedding vector(768);
BEGIN
  SELECT embedding INTO ref_embedding
  FROM listing_embeddings WHERE listing_id = p_listing_id;

  IF ref_embedding IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    le.listing_id,
    1 - (le.embedding <=> ref_embedding) AS similarity
  FROM listing_embeddings le
  WHERE le.listing_id != p_listing_id
    AND 1 - (le.embedding <=> ref_embedding) >= similarity_threshold
  ORDER BY le.embedding <=> ref_embedding
  LIMIT match_count;
END;
$$;


-- ==================== sql/048_cmdu_plano_diretor.sql ====================
-- 048_cmdu_plano_diretor.sql — CMDU atas + sinais de Plano Diretor / Zoneamento

-- Atas do Conselho Municipal de Desenvolvimento Urbano (CMDU)
-- Publicadas no DOM-MAR. Sinal de 6-12 meses antes de qualquer mudança de zoneamento.
CREATE TABLE IF NOT EXISTS cmdu_atas (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT NOT NULL UNIQUE,
    publication_date    DATE,
    numero_ata          TEXT,
    texto_pauta         TEXT,              -- pauta/ordem do dia extraída
    tem_aprovacao       BOOLEAN DEFAULT FALSE,
    tem_zoneamento      BOOLEAN DEFAULT FALSE,  -- menciona zoneamento/plano diretor
    neighborhood        TEXT,
    city                TEXT NOT NULL DEFAULT 'Marília',
    state               TEXT NOT NULL DEFAULT 'SP',
    raw_snippet         TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cmdu_publication_date ON cmdu_atas (publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_cmdu_zoneamento ON cmdu_atas (tem_zoneamento) WHERE tem_zoneamento = TRUE;
CREATE INDEX IF NOT EXISTS idx_cmdu_neighborhood ON cmdu_atas (neighborhood);

ALTER TABLE cmdu_atas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on cmdu_atas" ON cmdu_atas;
CREATE POLICY "service_role full access on cmdu_atas"
    ON cmdu_atas FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on cmdu_atas" ON cmdu_atas;
CREATE POLICY "Allow public read on cmdu_atas"
    ON cmdu_atas FOR SELECT TO anon USING (true);

-- ---------------------------------------------------------------------------

-- Sinais de Plano Diretor / Upzoning
-- Captura publicações DOM-MAR com keywords de zoneamento: lei de uso do solo,
-- rezonamento, ZEIS, coeficiente de aproveitamento, audiência pública, PPA.
CREATE TABLE IF NOT EXISTS plano_diretor_signals (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT NOT NULL UNIQUE,
    publication_date    DATE,
    tipo_sinal          TEXT,              -- plano_diretor | rezonamento | zeis | ppa | audiencia_publica | uso_ocupacao_solo | outorga_onerosa
    keyword             TEXT,              -- keyword que triggou o match
    lei_number          TEXT,              -- número da lei se mencionado
    neighborhood        TEXT,
    upzoning_bairro     TEXT,              -- bairro em upzoning se detectado (Jd Bela Vista, Jd América)
    city                TEXT NOT NULL DEFAULT 'Marília',
    state               TEXT NOT NULL DEFAULT 'SP',
    raw_snippet         TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pd_signals_publication_date ON plano_diretor_signals (publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_pd_signals_tipo ON plano_diretor_signals (tipo_sinal);
CREATE INDEX IF NOT EXISTS idx_pd_signals_upzoning ON plano_diretor_signals (upzoning_bairro)
    WHERE upzoning_bairro IS NOT NULL;

ALTER TABLE plano_diretor_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on plano_diretor_signals" ON plano_diretor_signals;
CREATE POLICY "service_role full access on plano_diretor_signals"
    ON plano_diretor_signals FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on plano_diretor_signals" ON plano_diretor_signals;
CREATE POLICY "Allow public read on plano_diretor_signals"
    ON plano_diretor_signals FOR SELECT TO anon USING (true);

-- ---------------------------------------------------------------------------
-- View: Radar de Upzoning — sinais de valorização antecipada por bairro
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW radar_upzoning AS
SELECT
    p.upzoning_bairro AS bairro,
    COUNT(*) AS total_sinais,
    MAX(p.publication_date) AS ultimo_sinal,
    MIN(p.publication_date) AS primeiro_sinal,
    ARRAY_AGG(DISTINCT p.tipo_sinal) AS tipos_sinal,
    ARRAY_AGG(DISTINCT p.lei_number) FILTER (WHERE p.lei_number IS NOT NULL) AS leis_relacionadas,
    BOOL_OR(p.tipo_sinal = 'plano_diretor') AS tem_plano_diretor,
    BOOL_OR(p.tipo_sinal = 'audiencia_publica') AS tem_audiencia_publica
FROM plano_diretor_signals p
WHERE p.upzoning_bairro IS NOT NULL
  AND p.publication_date >= CURRENT_DATE - INTERVAL '24 months'
GROUP BY p.upzoning_bairro
ORDER BY total_sinais DESC, ultimo_sinal DESC;


-- ==================== sql/049_cnpj_agronegocio.sql ====================
-- 049_cnpj_agronegocio.sql

-- ---------------------------------------------------------------------------
-- Enriquecimento CNPJ das construtoras (Receita Federal / open.cnpja.com)
-- ---------------------------------------------------------------------------
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS razao_social TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS situacao_cadastral TEXT;  -- ATIVA | BAIXADA | SUSPENSA
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS data_abertura DATE;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS capital_social NUMERIC;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS porte TEXT;               -- ME | EPP | MEDIA | GRANDE
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS socios JSONB;             -- [{nome, cpf_hash, cargo, entrada}]
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS cnae_principal TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS telefone TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS endereco_cnpj TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS cnpj_enriched_at TIMESTAMPTZ;

-- Flag de risco derivado do CNPJ
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS cnpj_risco TEXT;
-- 'baixo' | 'medio' | 'alto' | 'critico'
-- critico: situação != ATIVA ou capital < R$10k com obra > R$1M

-- ---------------------------------------------------------------------------
-- Índice Agronegócio Marília — correlação safra × mercado imobiliário
-- Fonte: CEPEA ESALQ-USP (público) + calendário de safra SP
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agronegocio_index (
    id              BIGSERIAL PRIMARY KEY,
    reference_date  DATE NOT NULL UNIQUE,
    cultura         TEXT NOT NULL DEFAULT 'soja',  -- soja | milho | cafe | laranja
    preco_saca      NUMERIC,       -- R$/sc 60kg (soja) ou R$/sc 50kg (milho)
    variacao_pct    NUMERIC,       -- variação % vs semana anterior
    fase_safra      TEXT,          -- plantio | crescimento | colheita | comercializacao | entressafra
    indice_compra   NUMERIC,       -- 0-100: probabilidade de compra imobiliária neste mês (calculado)
    source          TEXT DEFAULT 'cepea_esalq',
    collected_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agro_date ON agronegocio_index (reference_date DESC);
CREATE INDEX IF NOT EXISTS idx_agro_cultura ON agronegocio_index (cultura);

-- Calendário de safra Marília-SP (médias históricas CONAB)
-- Usado como fallback quando API CEPEA não está disponível
CREATE TABLE IF NOT EXISTS safra_calendar (
    mes             INTEGER PRIMARY KEY CHECK (mes BETWEEN 1 AND 12),
    fase_soja       TEXT,
    fase_milho      TEXT,
    indice_compra_historico NUMERIC,  -- 0-100 baseado em histórico de transações ITBI
    notas           TEXT
);

INSERT INTO safra_calendar (mes, fase_soja, fase_milho, indice_compra_historico, notas) VALUES
    (1,  'colheita_inicio',    'plantio_2a',        45, 'Início colheita soja; aguardando preço'),
    (2,  'colheita',           'crescimento_2a',     55, 'Colheita plena; primeiros pagamentos'),
    (3,  'comercializacao',    'colheita_2a_inicio', 80, 'Pico de pagamento safra; maior demanda imobiliária'),
    (4,  'comercializacao',    'colheita_2a',        85, 'Maior volume de compras imobiliárias do ano'),
    (5,  'comercializacao',    'comercializacao_2a', 75, 'Pagamentos finais; ainda aquecido'),
    (6,  'entressafra',        'entressafra',        50, 'Transição; mercado normaliza'),
    (7,  'plantio_inicio',     'entressafra',        40, 'Início ciclo; comprador mais cauteloso'),
    (8,  'plantio',            'entressafra',        35, 'Baixo volume; bom para negociar terreno'),
    (9,  'plantio',            'plantio_inicio',     38, 'Preparação plantio 2a safra'),
    (10, 'crescimento',        'crescimento',        42, 'Monitoramento lavoura; atenção dividida'),
    (11, 'crescimento',        'crescimento',        48, 'Estimativas colheita influenciam otimismo'),
    (12, 'colheita_antecipada','colheita_antecipada',60, 'Colheitas precoces; início de movimentação')
ON CONFLICT (mes) DO NOTHING;


-- ==================== sql/050_heritage_vision.sql ====================
-- 050_heritage_vision.sql — Heritage detector + Vision conservation score

-- ---------------------------------------------------------------------------
-- Heritage Detector — cruzamento obituário × inventário × listing
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS heritage_signals (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT NOT NULL UNIQUE,
    signal_date         DATE,
    signal_type         TEXT NOT NULL,   -- 'obituario' | 'inventario_tjsp' | 'listing_post_obit'
    nome_falecido       TEXT,
    cpf_hash            TEXT,            -- SHA256(cpf) — nunca armazenar CPF em claro
    endereco            TEXT,
    neighborhood        TEXT,
    processo_tjsp       TEXT,            -- número do processo de inventário
    listing_id          BIGINT REFERENCES listings(id),
    desconto_estimado   NUMERIC,         -- % desconto estimado vs valor de mercado
    confidence          NUMERIC,         -- 0-1: certeza do cruzamento
    source              TEXT,
    raw_payload         JSONB,
    first_seen_at       TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_heritage_signal_date ON heritage_signals (signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_heritage_neighborhood ON heritage_signals (neighborhood);
CREATE INDEX IF NOT EXISTS idx_heritage_listing ON heritage_signals (listing_id)
    WHERE listing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_heritage_type ON heritage_signals (signal_type);

ALTER TABLE heritage_signals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role full access on heritage_signals" ON heritage_signals;
CREATE POLICY "service_role full access on heritage_signals"
    ON heritage_signals FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- Vision conservation score — análise das fotos dos anúncios via Gemini Vision
-- ---------------------------------------------------------------------------
ALTER TABLE listings ADD COLUMN IF NOT EXISTS vision_conservation_score NUMERIC;   -- 0-10
ALTER TABLE listings ADD COLUMN IF NOT EXISTS vision_acabamento TEXT;               -- basico | medio | alto | luxo
ALTER TABLE listings ADD COLUMN IF NOT EXISTS vision_reformado BOOLEAN;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS vision_problemas TEXT[];              -- ['umidade','rachadura','pintura_velha']
ALTER TABLE listings ADD COLUMN IF NOT EXISTS vision_fotos_analisadas INTEGER DEFAULT 0;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS vision_listing_analyzed_at TIMESTAMPTZ;

-- Detalhes por foto (para auditoria e retreino)
CREATE TABLE IF NOT EXISTS listing_vision_details (
    id              BIGSERIAL PRIMARY KEY,
    listing_id      BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    foto_url        TEXT NOT NULL,
    foto_index      INTEGER DEFAULT 0,
    conservation    NUMERIC,        -- 0-10
    acabamento      TEXT,
    comodos         TEXT[],         -- ['sala','quarto','banheiro','cozinha']
    problemas       TEXT[],
    pontos_positivos TEXT[],
    raw_response    JSONB,
    analyzed_at     TIMESTAMPTZ DEFAULT NOW(),
    model           TEXT DEFAULT 'gemini-2.0-flash',
    UNIQUE(listing_id, foto_url)
);

CREATE INDEX IF NOT EXISTS idx_vision_listing ON listing_vision_details (listing_id);


-- ==================== sql/052_map_geojson.sql ====================
-- 052_map_geojson.sql — RPCs GeoJSON para o mapa do dashboard (Onda 2)
-- O dashboard acessa o Supabase direto e o PostgREST não devolve geometria
-- PostGIS de forma utilizável (vem como WKB hex). Estas funções expõem os
-- polígonos de setores censitários e os polos econômicos como GeoJSON/coords
-- prontos para o Leaflet.
--
-- SECURITY DEFINER: rodam como o dono (bypass RLS), leitura apenas, e são
-- concedidas ao papel anon. Assim o front lê o mapa sem precisar abrir as
-- tabelas base ao público.

-- Setores censitários como GeoJSON, com renda/densidade para choropleth.
CREATE OR REPLACE FUNCTION census_sectors_geojson()
RETURNS TABLE (
  sector_code       TEXT,
  renda_per_capita  NUMERIC,
  densidade_demo    NUMERIC,
  total_domicilios  INTEGER,
  populacao         INTEGER,
  geojson           TEXT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    cs.sector_code,
    cs.renda_per_capita,
    cs.densidade_demo,
    cs.total_domicilios,
    cs.populacao,
    ST_AsGeoJSON(cs.geom) AS geojson
  FROM census_sectors cs
  WHERE cs.geom IS NOT NULL;
$$;

-- Polos econômicos (pontos + raio de influência).
CREATE OR REPLACE FUNCTION economic_centroids_geojson()
RETURNS TABLE (
  name        TEXT,
  label_pt    TEXT,
  latitude    DOUBLE PRECISION,
  longitude   DOUBLE PRECISION,
  radius_m    INTEGER,
  description TEXT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT name, label_pt, latitude, longitude, radius_m, description
  FROM economic_centroids
  WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
$$;

GRANT EXECUTE ON FUNCTION census_sectors_geojson() TO anon;
GRANT EXECUTE ON FUNCTION economic_centroids_geojson() TO anon;


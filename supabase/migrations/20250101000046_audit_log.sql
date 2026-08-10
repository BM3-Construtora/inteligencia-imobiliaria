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

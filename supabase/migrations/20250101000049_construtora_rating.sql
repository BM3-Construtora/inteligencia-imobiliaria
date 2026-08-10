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

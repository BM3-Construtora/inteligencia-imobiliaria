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

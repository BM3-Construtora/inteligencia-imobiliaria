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

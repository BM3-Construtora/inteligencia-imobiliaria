-- 033_iptu_planta_generica.sql — Planta Genérica de Valores (PGV) IPTU Marília-SP
--
-- Dado de REFERÊNCIA (não é signal). Valor venal m² oficial por face de quadra
-- /setor fiscal, conforme Anexo I (Tabela 5) da Lei Complementar Municipal.
--
-- Histórico legal Marília:
--   - LC 158/1997 — Código Tributário do Município (CTM)
--   - LC 672/2013 — Edita a Planta Genérica de Valores (vigência 2013)
--   - PLC 16/2025 — Revisão da PGV aprovada em 22/09/2025
--
-- Uso no sistema:
--   - Floor price de terra por região (calibração do AVM)
--   - Detector de "imóvel abaixo do valor venal" (oportunidade fiscal)

CREATE TABLE IF NOT EXISTS iptu_planta_valores (
    id BIGSERIAL PRIMARY KEY,
    ref_year INT NOT NULL,                 -- Ano de vigência (ex: 2024, 2026)
    sector_code TEXT NOT NULL,             -- Setor fiscal (ex: "01", "12-A")
    face_code TEXT,                        -- Face de quadra (nullable; alguns
                                           -- registros são por setor inteiro)
    neighborhood TEXT,                     -- Bairro normalizado
    street_name TEXT,                      -- Logradouro (quando aplicável)
    street_from TEXT,                      -- Trecho — de (nº ou logradouro)
    street_to TEXT,                        -- Trecho — até (nº ou logradouro)
    land_value_per_m2 NUMERIC NOT NULL,    -- R$/m² de terreno (territorial)
    build_value_per_m2_by_type JSONB,      -- {"residencial": 1200, "comercial":
                                           --  1500, "industrial": 800, ...}
    source_law TEXT,                       -- Ex: "Lei Complementar 672/2013"
    raw_payload JSONB,                     -- Linha original do PDF (debug)
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Idempotência: 1 linha por (ano, setor, face). face_code NULL vira ''
    -- via COALESCE pra permitir unique sem conflitos NULL.
    CONSTRAINT iptu_planta_valores_uniq
        UNIQUE (ref_year, sector_code, face_code)
);

CREATE INDEX IF NOT EXISTS idx_iptu_planta_ref_year_neighborhood
    ON iptu_planta_valores (ref_year DESC, neighborhood);

CREATE INDEX IF NOT EXISTS idx_iptu_planta_sector_code
    ON iptu_planta_valores (sector_code);

-- RLS
ALTER TABLE iptu_planta_valores ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on iptu_planta_valores"
    ON iptu_planta_valores;
CREATE POLICY "service_role full access on iptu_planta_valores"
    ON iptu_planta_valores
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on iptu_planta_valores"
    ON iptu_planta_valores;
CREATE POLICY "Allow public read on iptu_planta_valores"
    ON iptu_planta_valores
    FOR SELECT
    TO anon
    USING (true);

COMMENT ON TABLE iptu_planta_valores IS
    'Planta Genérica de Valores IPTU Marília — valor venal oficial m² por face '
    'de quadra/setor. Atualizada anualmente via anexo de Lei Complementar.';

COMMENT ON COLUMN iptu_planta_valores.land_value_per_m2 IS
    'Valor venal territorial R$/m² (Tabela 5 do Anexo I — antes dos fatores '
    'de homogeneização: profundidade, esquina, topografia, pedologia)';

COMMENT ON COLUMN iptu_planta_valores.build_value_per_m2_by_type IS
    'Valor venal predial R$/m² por tipo/padrão construtivo (residencial, '
    'comercial, industrial, etc) — Tabelas 1-4 do Anexo I';

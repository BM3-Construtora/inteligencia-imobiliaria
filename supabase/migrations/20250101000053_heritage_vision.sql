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

-- Track F — Computer vision sobre imagem satélite de cada terreno.
-- Google Static Maps + Gemini Vision extraem features visuais que viram
-- feature adicional do Hunter score (até 10pts).

CREATE TABLE IF NOT EXISTS vision_features (
    id                      BIGSERIAL PRIMARY KEY,
    listing_id              BIGINT NOT NULL UNIQUE
                              REFERENCES listings(id) ON DELETE CASCADE,

    -- Imagem fonte (sem key, regerada na ida)
    latitude                NUMERIC(10, 6),
    longitude               NUMERIC(10, 6),
    image_url               TEXT,
    image_zoom              INT DEFAULT 19,
    image_hash              TEXT,                  -- sha256 da imagem baixada

    -- Topografia / terreno
    topography              TEXT CHECK (topography IN (
                                'plano','aclive_suave','aclive_acentuado',
                                'declive_suave','declive_acentuado','irregular','unknown'
                            )),
    vegetation_pct          NUMERIC(5, 2),         -- 0-100 estimado
    paved_access            BOOLEAN,
    sidewalk_present        BOOLEAN,
    drainage_visible        BOOLEAN,
    neighbors_built_pct     NUMERIC(5, 2),         -- % de lotes construídos no entorno
    lot_shape               TEXT CHECK (lot_shape IN (
                                'regular','irregular','esquina','encravado','unknown'
                            )),
    visible_obstacles       TEXT[],                -- postes, transformadores, etc
    socioeconomic_signal    TEXT CHECK (socioeconomic_signal IN (
                                'baixo','medio_baixo','medio','medio_alto','alto','unknown'
                            )),

    -- Bookkeeping
    raw_vision_response     JSONB,
    vision_model            TEXT DEFAULT 'gemini-2.5-flash',
    extracted_at            TIMESTAMPTZ DEFAULT NOW(),
    vision_score            NUMERIC(4, 2)          -- 0-10 composto p/ Hunter
);

-- Índices
CREATE UNIQUE INDEX IF NOT EXISTS idx_vision_features_listing
    ON vision_features (listing_id);

CREATE INDEX IF NOT EXISTS idx_vision_features_score
    ON vision_features (vision_score DESC);

-- RLS — padrão Marília (service_role full, anon SELECT)
ALTER TABLE vision_features ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on vision_features"
    ON vision_features;
CREATE POLICY "service_role full access on vision_features"
    ON vision_features
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read on vision_features"
    ON vision_features;
CREATE POLICY "Allow public read on vision_features"
    ON vision_features
    FOR SELECT
    TO anon
    USING (true);

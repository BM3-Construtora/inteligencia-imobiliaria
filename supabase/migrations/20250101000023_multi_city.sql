-- Multi-city support — parametrizar pra BM3 expandir além de Marília.
-- Listings já tem `city`; tabela aglutinadora + neighborhoods pivota.

CREATE TABLE IF NOT EXISTS cities (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    state           TEXT NOT NULL DEFAULT 'SP',
    ibge_code       TEXT,
    centroid_lat    DOUBLE PRECISION,
    centroid_lng    DOUBLE PRECISION,
    bbox_min_lat    DOUBLE PRECISION,
    bbox_max_lat    DOUBLE PRECISION,
    bbox_min_lng    DOUBLE PRECISION,
    bbox_max_lng    DOUBLE PRECISION,
    is_active       BOOLEAN DEFAULT TRUE,
    aliases         TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO cities (name, state, ibge_code, centroid_lat, centroid_lng,
                    bbox_min_lat, bbox_max_lat, bbox_min_lng, bbox_max_lng,
                    aliases)
VALUES ('Marília', 'SP', '3528502', -22.2154, -49.9456,
        -22.40, -22.05, -50.10, -49.80,
        ARRAY['Marilia', 'MARÍLIA', 'MARILIA', 'Mar?Lia'])
ON CONFLICT (name) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_cities_active ON cities (is_active);

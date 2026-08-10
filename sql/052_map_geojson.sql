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

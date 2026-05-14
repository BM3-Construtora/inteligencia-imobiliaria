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
  l.score,
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

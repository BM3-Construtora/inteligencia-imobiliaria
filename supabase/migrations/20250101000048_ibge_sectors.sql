-- Setores Censitários IBGE 2022 com dados demográficos
-- Polígonos baixados via API: https://servicodados.ibge.gov.br/api/v3/malhas/municipios/3529005
-- Dados de renda: IBGE Censo 2022 (via CNEFE e resultados preliminares)

-- A tabela census_sectors já foi criada no 042_postgis.sql
-- Este arquivo adiciona colunas extras e função de join espacial

-- Adicionar colunas de dados socioeconômicos
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS renda_media_domiciliar NUMERIC;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS pessoas_responsavel_alfabetizadas INTEGER;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS domicilios_alugados INTEGER;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS domicilios_proprios INTEGER;
ALTER TABLE census_sectors ADD COLUMN IF NOT EXISTS media_moradores NUMERIC;

-- Função PostgreSQL para enriquecer listing com dados do setor censitário
CREATE OR REPLACE FUNCTION enrich_listing_with_census(p_listing_id INTEGER)
RETURNS VOID AS $$
BEGIN
  UPDATE listings l
  SET
    census_sector_code = cs.sector_code,
    census_renda_pc = cs.renda_per_capita,
    census_densidade = cs.densidade_demo,
    census_domicilios = cs.total_domicilios,
    updated_at = NOW()
  FROM census_sectors cs
  WHERE l.id = p_listing_id
    AND l.geom IS NOT NULL
    AND ST_Within(l.geom, cs.geom);
END;
$$ LANGUAGE plpgsql;

-- Adicionar colunas de censo em listings (se não existirem)
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_sector_code TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_renda_pc NUMERIC;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_densidade NUMERIC;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS census_domicilios INTEGER;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS mcmv_accessibility_score NUMERIC;

-- Índice para join espacial
CREATE INDEX IF NOT EXISTS idx_census_sectors_geom_gist ON census_sectors USING GIST (geom);

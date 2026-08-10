-- 032_materials_sprint2.sql — Profundidade do dado de materiais
-- 1. Normalização de preço por unidade (kg/m2/un) em price_history
-- 2. Flag de outlier pra triagem
-- 3. Seeds de fornecedores locais Marília (sem site, cotação manual)

-- =====================================================================
-- material_price_history — colunas novas
-- =====================================================================
ALTER TABLE material_price_history
    ADD COLUMN IF NOT EXISTS price_per_kg NUMERIC,
    ADD COLUMN IF NOT EXISTS price_per_m2 NUMERIC,
    ADD COLUMN IF NOT EXISTS price_per_unit NUMERIC,
    ADD COLUMN IF NOT EXISTS is_outlier BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS outlier_reason TEXT,
    ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'scrape'
        CHECK (source IN ('scrape', 'manual', 'pdf', 'api_b2b'));

CREATE INDEX IF NOT EXISTS idx_material_price_history_price_per_kg
    ON material_price_history (price_per_kg)
    WHERE price_per_kg IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_material_price_history_outlier
    ON material_price_history (is_outlier)
    WHERE is_outlier;

-- =====================================================================
-- Seeds — fornecedores locais Marília-SP (sem e-commerce)
-- =====================================================================
-- Cotação entra via CLI manual ou form futuro do dashboard.
INSERT INTO material_supplier (slug, name, kind, platform, base_url, delivers_to_marilia, delivery_notes)
VALUES
    ('cassol_centerlar', 'Cassol Centerlar', 'regional_retail', 'magento',
     'https://www.cassol.com.br', TRUE,
     'Loja Bauru. E-commerce Magento. Scraping HTML — sem API JSON pública.'),

    -- Locais sem site, cotação manual via CLI
    ('marilia_concreto', 'Marília Concreto', 'aggregate', 'manual', NULL, TRUE,
     'Concreto usinado. Cotação por telefone/WhatsApp.'),
    ('polimix_marilia', 'Polimix Marília', 'aggregate', 'manual', NULL, TRUE,
     'Concreto usinado. Rede nacional, unidade Marília.'),
    ('engemix_marilia', 'Engemix Marília', 'aggregate', 'manual', NULL, TRUE,
     'Concreto usinado. Verificar unidade local.'),
    ('supermix_marilia', 'Supermix', 'aggregate', 'manual', NULL, TRUE,
     'Concreto usinado.'),
    ('areal_local_marilia', 'Areais Locais Marília', 'aggregate', 'manual', NULL, TRUE,
     'Areia/brita/pedrisco. Multi-fornecedor (genérico — refinar conforme cotações).'),
    ('olarias_regiao', 'Olarias Região (Pompéia/Garça)', 'manufacturer', 'manual', NULL, TRUE,
     'Bloco cerâmico, telha. Multi-fornecedor regional.'),
    ('madeireira_marilia', 'Madeireira Marília', 'local_retail', 'manual', NULL, TRUE,
     'Madeira bruta, forma, pontalete.'),
    ('ferragem_local', 'Ferragens Locais', 'local_retail', 'manual', NULL, TRUE,
     'Aço cortado e dobrado. Multi-fornecedor.'),
    ('maxbel_marilia', 'Maxbel', 'local_retail', 'manual', NULL, TRUE,
     'Loja física Marília.')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    kind = EXCLUDED.kind,
    platform = EXCLUDED.platform,
    base_url = EXCLUDED.base_url,
    delivers_to_marilia = EXCLUDED.delivers_to_marilia,
    delivery_notes = EXCLUDED.delivery_notes;

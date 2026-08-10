-- 031_materials.sql — Módulo de materiais de construção
-- Pipeline paralelo ao de imóveis. Rastreia preço de SKUs (cimento, aço, bloco,
-- tinta, etc) em fornecedores que entregam em Marília-SP. Objetivo: orçamento
-- preciso de obra + alertas de queda de preço.

-- =====================================================================
-- material_supplier — Fornecedores (lojas/redes/fabricantes)
-- =====================================================================
CREATE TABLE IF NOT EXISTS material_supplier (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'national_retail',     -- Leroy, Telhanorte, C&C
        'regional_retail',     -- Cassol, Center Castilho
        'local_retail',        -- Loja física Marília sem e-commerce
        'marketplace',         -- Mercado Livre, Amazon
        'manufacturer',        -- Votorantim, Gerdau, Tigre
        'wholesaler',          -- Atacadista B2B
        'aggregate'            -- Areia/brita/concreto (depósitos)
    )),
    platform TEXT,             -- 'vtex' | 'leroy' | 'mercadolivre' | 'manual' | ...
    base_url TEXT,
    delivers_to_marilia BOOLEAN DEFAULT FALSE,
    delivery_notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_material_supplier_kind
    ON material_supplier (kind);
CREATE INDEX IF NOT EXISTS idx_material_supplier_active_delivers
    ON material_supplier (is_active, delivers_to_marilia);

-- =====================================================================
-- material_sku — Catálogo canônico (entidade unificada cross-loja)
-- =====================================================================
-- Um SKU canônico (ex: "Cimento CP II F 32 50kg Votoran") pode ter listings
-- em N fornecedores. Matching cross-loja por EAN ou por nome+marca+volume.
CREATE TABLE IF NOT EXISTS material_sku (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'cimento','agregado','aco','bloco','argamassa',
        'hidraulica','eletrica','cobertura','revestimento',
        'tinta','madeira','ferramenta','epi','outro'
    )),
    brand TEXT,
    model TEXT,
    unit TEXT NOT NULL,        -- 'saco_50kg' | 'barra_12m' | 'm2' | 'un' | 'rolo_100m' | ...
    weight_kg NUMERIC,
    ean TEXT UNIQUE,           -- nullable — nem todo SKU tem EAN exposto
    seed BOOLEAN DEFAULT FALSE,-- TRUE pros 10 SKUs do MVP
    bom_stage TEXT,            -- 'fundacao' | 'estrutura' | 'alvenaria' | ...
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_material_sku_category
    ON material_sku (category);
CREATE INDEX IF NOT EXISTS idx_material_sku_brand_model
    ON material_sku (brand, model);
CREATE INDEX IF NOT EXISTS idx_material_sku_seed
    ON material_sku (seed) WHERE seed;

-- =====================================================================
-- material_listing — Anúncio específico de um SKU em um fornecedor
-- =====================================================================
-- (sku_id, supplier_id) → URL, ID externo, status. O preço varia no tempo
-- e fica em material_price_history.
CREATE TABLE IF NOT EXISTS material_listing (
    id BIGSERIAL PRIMARY KEY,
    sku_id BIGINT REFERENCES material_sku (id) ON DELETE CASCADE,
    supplier_id BIGINT NOT NULL REFERENCES material_supplier (id) ON DELETE CASCADE,
    supplier_sku TEXT NOT NULL,             -- ID interno do fornecedor (ex: VTEX itemId)
    supplier_name TEXT,                     -- Nome do produto na loja
    supplier_ean TEXT,
    url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    raw_payload JSONB,
    UNIQUE (supplier_id, supplier_sku)
);

CREATE INDEX IF NOT EXISTS idx_material_listing_sku
    ON material_listing (sku_id);
CREATE INDEX IF NOT EXISTS idx_material_listing_supplier
    ON material_listing (supplier_id);
CREATE INDEX IF NOT EXISTS idx_material_listing_ean
    ON material_listing (supplier_ean) WHERE supplier_ean IS NOT NULL;

-- =====================================================================
-- material_price_history — Série temporal de preço por listing
-- =====================================================================
CREATE TABLE IF NOT EXISTS material_price_history (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES material_listing (id) ON DELETE CASCADE,
    price NUMERIC NOT NULL,
    list_price NUMERIC,
    region_price NUMERIC,                   -- Preço Marília quando disponível
    is_available BOOLEAN NOT NULL,
    can_deliver_marilia BOOLEAN,
    shipping_cost NUMERIC,                  -- Frete CEP 17500 (nullable até implementar)
    collected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_material_price_history_listing_time
    ON material_price_history (listing_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_material_price_history_collected_at
    ON material_price_history (collected_at DESC);

-- =====================================================================
-- material_bom — Bill of Materials (quantidade por m² ou por casa-tipo)
-- =====================================================================
CREATE TABLE IF NOT EXISTS material_bom (
    id BIGSERIAL PRIMARY KEY,
    template TEXT NOT NULL,                 -- 'mcmv_60m2' | 'medio_padrao_120m2' | ...
    sku_id BIGINT NOT NULL REFERENCES material_sku (id) ON DELETE CASCADE,
    quantity NUMERIC NOT NULL,
    notes TEXT,
    UNIQUE (template, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_material_bom_template
    ON material_bom (template);

-- =====================================================================
-- RLS
-- =====================================================================
ALTER TABLE material_supplier ENABLE ROW LEVEL SECURITY;
ALTER TABLE material_sku ENABLE ROW LEVEL SECURITY;
ALTER TABLE material_listing ENABLE ROW LEVEL SECURITY;
ALTER TABLE material_price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE material_bom ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'material_supplier','material_sku','material_listing',
        'material_price_history','material_bom'
    ]
    LOOP
        EXECUTE format(
            'DROP POLICY IF EXISTS "service_role full access on %I" ON %I',
            t, t
        );
        EXECUTE format(
            'CREATE POLICY "service_role full access on %I" ON %I '
            'FOR ALL TO service_role USING (true) WITH CHECK (true)',
            t, t
        );
        EXECUTE format(
            'DROP POLICY IF EXISTS "Allow public read on %I" ON %I',
            t, t
        );
        EXECUTE format(
            'CREATE POLICY "Allow public read on %I" ON %I '
            'FOR SELECT TO anon USING (true)',
            t, t
        );
    END LOOP;
END $$;

-- =====================================================================
-- Seed mínimo de fornecedores
-- =====================================================================
INSERT INTO material_supplier (slug, name, kind, platform, base_url, delivers_to_marilia, delivery_notes)
VALUES
    ('leroy_merlin', 'Leroy Merlin', 'national_retail', 'leroy',
     'https://www.leroymerlin.com.br',
     TRUE,
     'Auto-geo detecta CEP Marília. region_price embute frete (~+6% vs base nacional).'),
    ('telhanorte', 'Telhanorte', 'national_retail', 'vtex',
     'https://www.telhanorte.com.br',
     TRUE,
     'VTEX. Cobertura SP interior. Frete a confirmar por carrinho.'),
    ('obramax', 'Obramax', 'national_retail', 'vtex',
     'https://www.obramax.com.br',
     FALSE,
     'API entrega 5 lojas para CEP 17500 (Mooca, Piracicaba, etc) mas simulação real retorna cannotBeDelivered para cimento e tinta. Fora do MVP.'),
    ('mercadolivre', 'Mercado Livre', 'marketplace', 'mercadolivre',
     'https://www.mercadolivre.com.br',
     TRUE,
     'Scraping HTML (API pública pede OAuth). Filtro por cidade Marília.')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    kind = EXCLUDED.kind,
    platform = EXCLUDED.platform,
    base_url = EXCLUDED.base_url,
    delivers_to_marilia = EXCLUDED.delivers_to_marilia,
    delivery_notes = EXCLUDED.delivery_notes;

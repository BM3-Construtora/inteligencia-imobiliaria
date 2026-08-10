-- 035_registry_lookups.sql — Consultas a cartórios de registro de imóveis (ARISP/ONR)
--
-- ARISP (Associação dos Registradores Imobiliários de SP) e ONR (Operador
-- Nacional de Registro) oferecem consulta a matrículas/certidões de imóveis
-- via portal registradores.onr.org.br. PAGO por consulta (~R$10-95 dependendo
-- do tipo + custas estaduais). NÃO é bulk-scrapeable.
--
-- Workflow: consulta sob demanda quando hunter detecta lead high-score.
-- Cache de 90 dias para evitar gastar R$ na mesma matrícula repetidamente.

CREATE TABLE IF NOT EXISTS registry_lookups (
    id BIGSERIAL PRIMARY KEY,

    -- Referência opcional para o lead que motivou a consulta
    listing_id BIGINT REFERENCES listings(id) ON DELETE SET NULL,

    -- Inputs da consulta
    address TEXT,
    registry_office TEXT,         -- ex: "1º Oficial de Marília-SP"
    matricula_number TEXT,        -- número da matrícula consultada
    requested_at TIMESTAMPTZ DEFAULT NOW(),

    -- Status do pedido
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'fetched', 'failed', 'pay_required')),

    -- Dados extraídos da matrícula (quando fetched)
    property_type TEXT,           -- casa | apartamento | terreno | comercial | rural
    area_m2 NUMERIC,
    owner_name TEXT,
    owner_doc TEXT,               -- CPF/CNPJ (parcial/hash conforme LGPD)
    last_transaction_date DATE,
    last_transaction_value NUMERIC,
    encumbrances JSONB,           -- ônus, penhoras, hipotecas, usufrutos, etc.
    raw_response JSONB,           -- payload bruto do portal (PDF link, JSON, etc.)

    -- Custo realizado (R$) — alimenta dashboard de gasto operacional
    cost_brl NUMERIC,

    fetched_at TIMESTAMPTZ,
    error_message TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_registry_lookups_listing
    ON registry_lookups (listing_id);
CREATE INDEX IF NOT EXISTS idx_registry_lookups_status
    ON registry_lookups (status);
CREATE INDEX IF NOT EXISTS idx_registry_lookups_matricula
    ON registry_lookups (matricula_number);
CREATE INDEX IF NOT EXISTS idx_registry_lookups_address
    ON registry_lookups (address);
CREATE INDEX IF NOT EXISTS idx_registry_lookups_requested_at
    ON registry_lookups (requested_at DESC);

-- RLS
ALTER TABLE registry_lookups ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role full access on registry_lookups"
    ON registry_lookups;
CREATE POLICY "service_role full access on registry_lookups"
    ON registry_lookups
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 049_cnpj_agronegocio.sql

-- ---------------------------------------------------------------------------
-- Enriquecimento CNPJ das construtoras (Receita Federal / open.cnpja.com)
-- ---------------------------------------------------------------------------
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS razao_social TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS situacao_cadastral TEXT;  -- ATIVA | BAIXADA | SUSPENSA
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS data_abertura DATE;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS capital_social NUMERIC;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS porte TEXT;               -- ME | EPP | MEDIA | GRANDE
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS socios JSONB;             -- [{nome, cpf_hash, cargo, entrada}]
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS cnae_principal TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS telefone TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS endereco_cnpj TEXT;
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS cnpj_enriched_at TIMESTAMPTZ;

-- Flag de risco derivado do CNPJ
ALTER TABLE construtoras_rating ADD COLUMN IF NOT EXISTS cnpj_risco TEXT;
-- 'baixo' | 'medio' | 'alto' | 'critico'
-- critico: situação != ATIVA ou capital < R$10k com obra > R$1M

-- ---------------------------------------------------------------------------
-- Índice Agronegócio Marília — correlação safra × mercado imobiliário
-- Fonte: CEPEA ESALQ-USP (público) + calendário de safra SP
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agronegocio_index (
    id              BIGSERIAL PRIMARY KEY,
    reference_date  DATE NOT NULL UNIQUE,
    cultura         TEXT NOT NULL DEFAULT 'soja',  -- soja | milho | cafe | laranja
    preco_saca      NUMERIC,       -- R$/sc 60kg (soja) ou R$/sc 50kg (milho)
    variacao_pct    NUMERIC,       -- variação % vs semana anterior
    fase_safra      TEXT,          -- plantio | crescimento | colheita | comercializacao | entressafra
    indice_compra   NUMERIC,       -- 0-100: probabilidade de compra imobiliária neste mês (calculado)
    source          TEXT DEFAULT 'cepea_esalq',
    collected_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agro_date ON agronegocio_index (reference_date DESC);
CREATE INDEX IF NOT EXISTS idx_agro_cultura ON agronegocio_index (cultura);

-- Calendário de safra Marília-SP (médias históricas CONAB)
-- Usado como fallback quando API CEPEA não está disponível
CREATE TABLE IF NOT EXISTS safra_calendar (
    mes             INTEGER PRIMARY KEY CHECK (mes BETWEEN 1 AND 12),
    fase_soja       TEXT,
    fase_milho      TEXT,
    indice_compra_historico NUMERIC,  -- 0-100 baseado em histórico de transações ITBI
    notas           TEXT
);

INSERT INTO safra_calendar (mes, fase_soja, fase_milho, indice_compra_historico, notas) VALUES
    (1,  'colheita_inicio',    'plantio_2a',        45, 'Início colheita soja; aguardando preço'),
    (2,  'colheita',           'crescimento_2a',     55, 'Colheita plena; primeiros pagamentos'),
    (3,  'comercializacao',    'colheita_2a_inicio', 80, 'Pico de pagamento safra; maior demanda imobiliária'),
    (4,  'comercializacao',    'colheita_2a',        85, 'Maior volume de compras imobiliárias do ano'),
    (5,  'comercializacao',    'comercializacao_2a', 75, 'Pagamentos finais; ainda aquecido'),
    (6,  'entressafra',        'entressafra',        50, 'Transição; mercado normaliza'),
    (7,  'plantio_inicio',     'entressafra',        40, 'Início ciclo; comprador mais cauteloso'),
    (8,  'plantio',            'entressafra',        35, 'Baixo volume; bom para negociar terreno'),
    (9,  'plantio',            'plantio_inicio',     38, 'Preparação plantio 2a safra'),
    (10, 'crescimento',        'crescimento',        42, 'Monitoramento lavoura; atenção dividida'),
    (11, 'crescimento',        'crescimento',        48, 'Estimativas colheita influenciam otimismo'),
    (12, 'colheita_antecipada','colheita_antecipada',60, 'Colheitas precoces; início de movimentação')
ON CONFLICT (mes) DO NOTHING;

-- 052_rls_hardening.sql
-- Fecha exposição de leitura anônima em tabelas sensíveis.
--
-- Contexto: várias tabelas foram criadas sem habilitar RLS. No Supabase, uma
-- tabela do schema public sem RLS habilitado fica legível via anon key (que é
-- pública no bundle do dashboard). Estas tabelas NÃO são lidas pelo dashboard
-- (conferido contra os .from(...) do front), então habilitar RLS deny-by-default
-- (RLS ligado, sem policy de SELECT) fecha o acesso anônimo sem quebrar nada.
-- O backend usa a service_role key, que ignora RLS por padrão.
--
-- NÃO incluídas aqui (o dashboard depende delas via anon key): listings,
-- opportunities, market_snapshots, neighborhoods, agent_runs, company_projects,
-- data_quality_log, listing_matches, market_indices, opportunity_decisions,
-- viability_studies. Essas são o edge competitivo da BM3 e continuam com leitura
-- pública. Fechá-las exige mover o front para auth (anon autenticado) ou uma API
-- server-side — decisão de arquitetura pendente (ver TODO no fim).

-- Preços justos (AVM) e rating de construtora: sinais de negociação sensíveis.
ALTER TABLE IF EXISTS avm_predictions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS construtoras_rating  ENABLE ROW LEVEL SECURITY;

-- Dados brutos e histórico interno de scoring.
ALTER TABLE IF EXISTS raw_listings         ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS hunter_score_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS price_history        ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS mcmv_rules           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS cities               ENABLE ROW LEVEL SECURITY;

-- Auditoria e retenção: nunca devem ser públicas.
ALTER TABLE IF EXISTS data_audit_log        ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS data_retention_policies ENABLE ROW LEVEL SECURITY;

-- Embeddings (RAG interno, não vão ao front).
ALTER TABLE IF EXISTS listing_embeddings    ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS document_embeddings   ENABLE ROW LEVEL SECURITY;

-- NÃO fechamos a camada geo pública (pois, census_sectors, economic_centroids,
-- listing_poi_proximity): são dados IBGE/OSM, não o edge competitivo, e alimentam
-- o mapa do dashboard via as funções *_geojson (migration map_geojson). Fechar
-- RLS aqui esvaziaria as camadas do mapa para o anon se as funções forem
-- SECURITY INVOKER.

-- Índices macro auxiliares.
ALTER TABLE IF EXISTS agronegocio_index     ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS safra_calendar        ENABLE ROW LEVEL SECURITY;

-- Caches (baixa sensibilidade, mas não precisam ser públicos).
ALTER TABLE IF EXISTS cep_cache             ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS geocode_cache         ENABLE ROW LEVEL SECURITY;

-- TODO(security): as tabelas do dashboard (listings, opportunities, etc.) ainda
-- têm leitura pública via `USING (true)` em 003_rls_dashboard.sql. Elas contêm o
-- ranking de oportunidades, que é o ativo competitivo. Fechar exige decidir o
-- modelo de acesso do front: (a) Supabase Auth com policy por usuário, ou
-- (b) API server-side com a service_role, deixando o browser sem acesso direto.
-- Registrar como ADR antes de implementar.

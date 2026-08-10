-- Baseline do tracking do Supabase CLI (equivale a 'supabase migration repair
-- --status applied ...'). Cole no SQL Editor do dashboard e rode UMA vez.
-- Marca as migrations históricas JÁ em prod como aplicadas; deixa as novas
-- desta leva pendentes para o db push/CD: map_geojson (055), rls_hardening
-- (056), parcelamento_public_read (058) — todas idempotentes.
-- Determinado cruzando o schema real do banco em 2026-08-10.

create schema if not exists supabase_migrations;
create table if not exists supabase_migrations.schema_migrations (
  version text primary key,
  statements text[],
  name text
);

insert into supabase_migrations.schema_migrations (version, name) values
  ('20250101000001','schema'),
  ('20250101000002','opportunities_unique'),
  ('20250101000003','rls_dashboard'),
  ('20250101000004','classification'),
  ('20250101000005','dedup_enhancements'),
  ('20250101000006','market_indices'),
  ('20250101000007','deal_velocity'),
  ('20250101000008','alerts_comps'),
  ('20250101000009','absorption'),
  ('20250101000010','sales_heat'),
  ('20250101000011','company_projects'),
  ('20250101000012','price_history_cross_platform'),
  ('20250101000013','data_quality_fixes'),
  ('20250101000014','listing_matches_split'),
  ('20250101000015','viability_columns'),
  ('20250101000016','geocode_cache'),
  ('20250101000017','llm_cost_optimization'),
  ('20250101000018','widen_change_pct'),
  ('20250101000019','sold_estimates_confidence'),
  ('20250101000020','decision_tracking'),
  ('20250101000021','hunter_score_history'),
  ('20250101000022','remove_embeddings'),
  ('20250101000023','multi_city'),
  ('20250101000024','backfill_uniao_urls'),
  ('20250101000025','off_market_signals'),
  ('20250101000026','bm3_deals'),
  ('20250101000027','regulatory_signals'),
  ('20250101000028','avm_predictions'),
  ('20250101000029','vision_features'),
  ('20250101000030','dedup_improvements'),
  ('20250101000031','off_market_source_relax'),
  ('20250101000032','materials'),
  ('20250101000033','property_timeline'),
  ('20250101000034','habite_se'),
  ('20250101000035','materials_sprint2'),
  ('20250101000036','iptu_planta_generica'),
  ('20250101000037','labor_indices'),
  ('20250101000038','registry_lookups'),
  ('20250101000039','construction_timeline'),
  ('20250101000040','itbi_transactions'),
  ('20250101000041','obras_publicas'),
  ('20250101000042','receitas_marilia'),
  ('20250101000043','parcelamento_solo'),
  ('20250101000044','licitacoes_obras'),
  ('20250101000045','postgis'),
  ('20250101000046','audit_log'),
  ('20250101000047','alvaras_eiv'),
  ('20250101000048','ibge_sectors'),
  ('20250101000049','construtora_rating'),
  ('20250101000050','pgvector'),
  ('20250101000051','cmdu_plano_diretor'),
  ('20250101000052','cnpj_agronegocio'),
  ('20250101000053','heritage_vision'),
  ('20250101000054','llm_usage'),
  ('20250101000057','bairro_stats')
on conflict (version) do nothing;

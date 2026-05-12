-- Migration 040: parcelamento_solo_marilia
-- Aprovações de parcelamento de solo (loteamentos e desmembramentos) extraídas do
-- Diário Oficial Municipal de Marília via API dados-abertos DOM-MAR.
-- Fonte: https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}

create table if not exists parcelamento_solo_marilia (
    id                  bigserial primary key,
    source_id           text not null,          -- processo normalizado ou hash do snippet
    issue_date          date,
    process_number      text,
    tipo                text,                   -- loteamento | desmembramento | subdivisao
    titulo              text,
    neighborhood        text,
    address             text,
    area_total_m2       numeric(14,2),
    lotes_count         integer,
    snippet             text,
    raw_payload         jsonb,
    last_seen_at        timestamptz not null default now(),
    constraint parcelamento_solo_marilia_source_id_key unique (source_id)
);

create index if not exists parcelamento_solo_marilia_issue_date_idx
    on parcelamento_solo_marilia (issue_date);
create index if not exists parcelamento_solo_marilia_neighborhood_idx
    on parcelamento_solo_marilia (neighborhood);
create index if not exists parcelamento_solo_marilia_tipo_idx
    on parcelamento_solo_marilia (tipo);

alter table parcelamento_solo_marilia enable row level security;

create policy "service role full access"
    on parcelamento_solo_marilia
    for all
    to service_role
    using (true)
    with check (true);

create policy "authenticated read"
    on parcelamento_solo_marilia
    for select
    to authenticated
    using (true);

-- Migration 038: obras_publicas_marilia
-- Obras públicas municipais via API dados-abertos da Prefeitura de Marília
-- Fonte: https://www.marilia.sp.gov.br/portal/dados-abertos/obras/{year}

create table if not exists obras_publicas_marilia (
    id                  bigserial primary key,
    source_id           text not null,          -- {year}_{slug(titulo)}
    year                smallint not null,
    titulo              text not null,
    categoria           text,                   -- Pavimentação, Escolas, Praças, etc.
    situacao            text,                   -- Em Andamento, Concluído, Cancelada, etc.
    neighborhood        text,                   -- bairro (quando disponível na descrição)
    valor               numeric(14,2),
    data_inicio         date,
    data_fim            date,
    data_atualizacao    timestamptz,
    descricao           text,
    raw_payload         jsonb,
    collected_at        timestamptz not null default now(),
    constraint obras_publicas_marilia_source_id_key unique (source_id)
);

-- índices para queries por bairro, categoria e período
create index if not exists obras_publicas_marilia_year_idx
    on obras_publicas_marilia (year);
create index if not exists obras_publicas_marilia_categoria_idx
    on obras_publicas_marilia (categoria);
create index if not exists obras_publicas_marilia_situacao_idx
    on obras_publicas_marilia (situacao);
create index if not exists obras_publicas_marilia_neighborhood_idx
    on obras_publicas_marilia (neighborhood);

-- RLS
alter table obras_publicas_marilia enable row level security;

create policy "service role full access"
    on obras_publicas_marilia
    for all
    to service_role
    using (true)
    with check (true);

create policy "authenticated read"
    on obras_publicas_marilia
    for select
    to authenticated
    using (true);

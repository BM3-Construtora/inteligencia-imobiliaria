-- Migration 041: licitacoes_obras_marilia
-- Licitações e editais de obras da Prefeitura de Marília
-- Fonte: https://www.marilia.sp.gov.br/portal/dados-abertos/licitacoes/{year}
-- Filtrado por palavras-chave de obras/construção para foco imobiliário

create table if not exists licitacoes_obras_marilia (
    id                  bigserial primary key,
    source_id           text not null,          -- {year}_{numero_edital}_{numero_processo}
    year                smallint not null,
    numero_edital       integer,
    numero_processo     integer,
    modalidade          text,
    situacao            text,                   -- Aberto, Homologado, Cancelado, etc.
    titulo              text not null,
    data_postagem       timestamptz,
    data_realizacao     timestamptz,
    data_atualizacao    timestamptz,
    descricao_html      text,
    is_obra             boolean not null default true, -- filtrado na coleta
    raw_payload         jsonb,
    collected_at        timestamptz not null default now(),
    constraint licitacoes_obras_marilia_source_id_key unique (source_id)
);

create index if not exists licitacoes_obras_marilia_year_idx
    on licitacoes_obras_marilia (year);
create index if not exists licitacoes_obras_marilia_situacao_idx
    on licitacoes_obras_marilia (situacao);
create index if not exists licitacoes_obras_marilia_data_realizacao_idx
    on licitacoes_obras_marilia (data_realizacao);

alter table licitacoes_obras_marilia enable row level security;

create policy "service role full access"
    on licitacoes_obras_marilia
    for all
    to service_role
    using (true)
    with check (true);

create policy "authenticated read"
    on licitacoes_obras_marilia
    for select
    to authenticated
    using (true);

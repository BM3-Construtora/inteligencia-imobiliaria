-- Migration 039: receitas_marilia
-- Receitas Analíticas mensais da Prefeitura de Marília via paiportalserver
-- Tipos coletados: ITBI + Taxa de Licença para Execução de Obras (proxy de alvarás)
-- Fonte: POST https://transparencia.marilia.sp.gov.br/paiportalserver/modulovisao/filter

create table if not exists receitas_marilia (
    id                  bigserial primary key,
    source_id           text not null,          -- UUID da API (campo "Id")
    api_id              bigint,                 -- ID numérico da API (campo "ID")
    exercicio           smallint not null,
    mes                 smallint not null,      -- 1-12
    descricao_receita   text not null,
    natureza_receita    text,
    unidade_gestora     text,
    vinculo             text,
    descricao_vinculo   text,
    nome_banco          text,
    operacao            text,
    data_movto          date,
    valor               numeric(14,2),
    raw_payload         jsonb,
    collected_at        timestamptz not null default now(),
    constraint receitas_marilia_source_id_key unique (source_id)
);

create index if not exists receitas_marilia_exercicio_mes_idx
    on receitas_marilia (exercicio, mes);
create index if not exists receitas_marilia_descricao_idx
    on receitas_marilia (descricao_receita);
create index if not exists receitas_marilia_data_movto_idx
    on receitas_marilia (data_movto);

alter table receitas_marilia enable row level security;

create policy "service role full access"
    on receitas_marilia
    for all
    to service_role
    using (true)
    with check (true);

create policy "authenticated read"
    on receitas_marilia
    for select
    to authenticated
    using (true);

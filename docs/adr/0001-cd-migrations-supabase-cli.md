# ADR 0001 — CD de migrations via Supabase CLI

Status: Accepted (2026-08-10)

## Contexto

As migrations vivem soltas em `sql/` numeradas (`001_…` a `053_…`), aplicadas
manualmente (via `scripts/apply_v2_migrations.sql` e pelo dashboard do Supabase).
Não há tracking de o que já rodou. A auditoria e o `PRODUCT_ROADMAP` acharam o
sintoma: migrations 042-050 ficaram órfãs (nunca aplicadas em produção), então
tabelas e colunas do "cérebro V2" existem no código e não no banco.

Queremos que toda migration entre no banco automaticamente quando chega na `main`.

## Decisão

- **Tracking + aplicação: Supabase CLI** (`supabase db push`). O CLI mantém a
  tabela `supabase_migrations.schema_migrations` no banco e aplica só as
  pendentes. Migrations passam a viver em `supabase/migrations/`.
- **Gatilho: automático no merge para `main`** (sem gate de aprovação), conforme
  escolha do time.

## Consequências

Positivas:
- Schema sempre sincronizado com o código; fim das migrations órfãs.
- Cada migration roda uma única vez (tracking), então a não-idempotência de
  algumas deixa de ser um problema de re-execução.

Negativas / riscos aceitos:
- **Sem gate**: uma migration ruim entra em produção sem revisão humana. Mitigação
  parcial: o `db push` para no primeiro erro e o job de CD falha (visível), mas
  não há rollback automático de DDL. Reveja migrations destrutivas no PR.
- Exige reorganizar ~57 arquivos para o layout do CLI e resolver 5 colisões de
  prefixo (`017, 030, 031, 032, 052`).
- Exige um **baseline** das migrations já aplicadas em produção, senão o primeiro
  `db push` tentaria reaplicar tudo.

## Plano de migração (ordem obrigatória)

1. **Reorganizar** `sql/` → `supabase/migrations/` com versões únicas de 14
   dígitos, preservando a ordem. Use `scripts/migrate_to_supabase_layout.sh`
   (faz os `git mv` determinísticos e resolve as colisões). Rode quando a branch
   parar de receber migrations de outras sessões, num commit dedicado. Atualize
   também as referências textuais a `sql/NNN_*.sql` em comentários/docstrings.
2. **Configurar secrets** no repositório (Settings → Secrets → Actions):
   - `SUPABASE_ACCESS_TOKEN` (token pessoal do CLI)
   - `SUPABASE_DB_PASSWORD` (senha do banco do projeto)
   - `SUPABASE_PROJECT_REF` (ref do projeto, ex: `abcxyz…`)
3. **Baseline** (uma vez, local, com as credenciais): marcar como aplicadas as
   migrations que já existem em produção, sem re-rodar:
   ```
   supabase link --project-ref <REF>
   supabase migration list          # veja local vs remoto
   supabase migration repair --status applied <version> …   # para cada já-aplicada
   ```
   Só as genuinamente novas (ex: RLS hardening, map geojson, bairro_stats) devem
   ficar como pendentes.
4. **Ativar o CD**: o workflow `deploy-migrations.yml` roda `supabase db push` no
   push para `main`. Antes do baseline ele sai limpo (guard), então é seguro
   mergear o workflow antes de concluir os passos 1-3.

## Alternativas consideradas

- **Runner próprio + tabela `schema_migrations`**: menos reestruturação, mas
  reinventa o que o CLI já faz. Preterido a favor do padrão da plataforma.
- **Gate de aprovação (GitHub Environment)**: mais seguro para DDL, mas o time
  preferiu velocidade (auto). Reavaliar se houver incidente de migration em prod.

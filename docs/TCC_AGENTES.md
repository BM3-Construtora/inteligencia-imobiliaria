# Sistema de Agentes para o TCC (MBA USP)

Conjunto de 6 agentes especializados + 1 workflow orquestrador para analisar e melhorar o TCC "Inteligência Imobiliária com IA para Análise de Viabilidade de Empreendimentos de Habitação Popular (MCMV)".

O diferencial: os agentes **conversam entre si** — o técnico ancora o texto no código real, o metodólogo cobra rigor, a banca usa as fraquezas apontadas como munição, e o orientador consolida tudo.

## Os 6 agentes

| Agente | Papel | Lente |
|---|---|---|
| `tcc-orientador` | Orientador acadêmico sênior | Estrutura, fio condutor, prontidão para defesa. Consolida os demais. |
| `tcc-redator` | Redator/revisor PT-BR | Clareza, redundância, registro acadêmico, ortografia. Propõe reescritas. |
| `tcc-tecnico` | Validador técnico | Confronta cada afirmação com o código real (src/, sql/). Caça exagero e subnotificação. |
| `tcc-metodologo` | Metodólogo + cientista de dados | Método de pesquisa (DSR), validação do AVM (MAE/MAPE/cobertura), leakage, viés. |
| `tcc-mercado` | Estrategista de negócios | Proposta de valor, benchmarking proptech, Canvas/SWOT, modelo de receita. |
| `tcc-banca` | Advogado do diabo / banca | Perguntas mais difíceis da defesa; encontra onde o trabalho quebra. |

Texto canônico do TCC: `docs/TCC_draft.md` (mantenha sincronizado com a versão atual).

## Como usar

### 1. Agente individual (pontual)
Peça diretamente no chat. Exemplos:
- "Use o `tcc-redator` para revisar a seção 2 do TCC."
- "Roda o `tcc-tecnico` pra checar se a parte de AVM bate com o código."
- "Chama o `tcc-banca` pra me fazer as 10 perguntas mais difíceis."

### 2. Revisão completa orquestrada (todos conversando)
Roda o workflow `.claude/workflows/tcc-revisao.js`:
- 3 fases: **Análise** (4 lentes em paralelo) → **Debate** (banca + redator reagem aos pareceres) → **Síntese** (orientador consolida num plano P0/P1/P2).
- Invocação: peça "roda a revisão completa do TCC" ou execute o workflow `tcc-revisao`.
- Acompanhe ao vivo com `/workflows`.

### 3. Combinações úteis
- **Antes de escrever uma seção nova**: `tcc-orientador` (onde encaixa) + `tcc-metodologo` (o que precisa conter).
- **Depois de escrever**: `tcc-redator` (polir) + `tcc-tecnico` (não exagerar).
- **Semana da defesa**: `tcc-banca` + `tcc-orientador` (plano final).

## Fluxo de conversa (workflow)

```
       ┌─────────── Fase 1: ANÁLISE (paralelo) ───────────┐
       │ orientador   técnico   metodólogo   mercado       │
       └───────────────────────┬───────────────────────────┘
                               ▼ pareceres viram munição
       ┌─────────── Fase 2: DEBATE (paralelo) ────────────┐
       │ banca (ataca fraquezas)   redator (reescreve)     │
       └───────────────────────┬───────────────────────────┘
                               ▼ tudo consolidado
       ┌─────────── Fase 3: SÍNTESE ──────────────────────┐
       │ orientador → plano de ação P0/P1/P2 + cronograma  │
       └───────────────────────────────────────────────────┘
```

## Manutenção
- Atualize `docs/TCC_draft.md` sempre que evoluir o texto — é a fonte que todos os agentes leem.
- Os agentes são project-local (`.claude/agents/`), versionados junto com o repositório.
- Para ajustar foco/tom de um agente, edite seu arquivo `.md` em `.claude/agents/`.

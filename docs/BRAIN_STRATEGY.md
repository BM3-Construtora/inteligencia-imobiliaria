# Brain MaríliaBot — Estratégia, Concorrentes, Roadmap e Arquitetura de Grafo

> Documento de estratégia consolidado a partir da conversa de discovery competitivo e arquitetural.
> Data de referência: 2026-05-11
> Não é doc de implementação fina — é a memória do raciocínio. Para implementar, derivar PRs/migrations a partir das fases descritas aqui.

---

## Sumário

1. [Pergunta inicial: "existe coisa parecida?"](#1-existe-coisa-parecida)
2. [Análise competitiva detalhada (6 players)](#2-análise-competitiva-detalhada)
3. [Diagnóstico do estágio atual do MaríliaBot](#3-diagnóstico-do-estágio-atual)
4. [Plano de Construção — 6 meses, 18 milestones](#4-plano-de-construção)
5. [Decisão estratégica: dado vs inteligência](#5-decisão-estratégica)
6. [Arquitetura do Knowledge Graph](#6-arquitetura-do-knowledge-graph)
7. [Fontes de dado por tier de impacto](#7-fontes-de-dado-por-tier)
8. [Sequência de execução recomendada](#8-sequência-de-execução-recomendada)

---

## 1. Existe coisa parecida?

**Veredito:** categoria existe (PropTech viabilidade BR), mas o nicho-alvo do MaríliaBot está vazio:
- Cidade média (Marília-SP) — nenhum competidor cobre bem
- Construtora familiar pequena — todos miram incorporadora média/grande
- Custo R$15-30/mês — todos cobram SaaS de R$2k-10k/mês
- Pipeline próprio com LLM + off-market — ninguém faz combo

**Concorrentes mapeados:** Urbit · Oferta Terreno · Hiperdados (+ ComproTerreno) · Locates · DataZap · ImobiBrasil (descartado, é CRM).

---

## 2. Análise competitiva detalhada

### 🏛️ Urbit (urbit.com.br) — *o veterano geoespacial*

**Produtos:**
- **Território em Dados** — fichas de terreno (urbanística + infra + sociodemografia + zoneamento), relatórios pagos por crédito
- **Explorer** — GIS profissional para mercado imobiliário, layers de zoneamento/lotes/infra pública, SaaS licenciado (trimestral/semestral/anual)
- **AVM Urbit** — modelo matemático de avaliação automatizada, treinado em portais + IBGE + infra + qualidade regional
- **Market Panel** — painel agregado para estudo de viabilidade mercadológica

**Cobertura:** 133 municípios parciais, **só SP e BH completos** (com legislação urbana + infra estruturada). Marília = parcial (só portais + IBGE).

**Preço:** créditos a partir de R$20 / Plano Corporate até 50 relatórios mês / Explorer licença SaaS.

**Público:** incorporadora média/grande, urbanista, arquiteto, engenheiro, fintech.

**Diferencial deles:** profundidade geoespacial em SP/BH.
**Lacuna:** Marília é vazio. Sem off-market. Sem LLM. Sem custo de obra.

---

### 🤖 Oferta Terreno (ofertaterreno.com.br) — *o mais próximo do seu DNA*

**Produtos:**
- IA + ML processando 6 tipos de input (geo + urbanístico + mercado + financeiro + sazonal + regulatório)
- Cálculo automático de **TIR, VPL, exposição máxima de caixa**
- Suporte explícito a **MCMV + crédito associativo + permuta financeira**
- Gestão de landbank: cadastro de terrenos com proprietário, docs, status, tarefas
- "Entende particularidades BR" — programas habitacionais, cartórios, prefeituras

**Diferencial declarado:** análise de dias → segundos.
**Base instalada:** 10k+ usuários.
**Lacuna:** sem coleta própria de portais (cadastro manual do usuário). Sem off-market. Sem vision. Sem fonte cartorial.

**Por que é o mais perigoso:** se um dia descer de ticket, ataca o mesmo perfil. Mantém-se enterprise por enquanto.

---

### 🏢 Hiperdados (hiperdados.com.br) — *ERP completo 360°*

**Módulos (suíte integrada):**
- **ComproTerreno** — landbank + inteligência mercado + georeferenciamento
- **Viabilidade** — TIR, VPL, dashboards consolidados
- **Vendas** — registro + comissão + funil
- **Carteira de Recebíveis** — índices de correção, boletos, inadimplência
- **Compras / Finanças / Contábil** — ERP full

**Cobertura:** 120+ cidades.
**Diferencial:** integração full-cycle do empreendimento.
**Lacuna:** é ERP enterprise, sem scraping, sem discovery, sem LLM.

---

### 🛰️ Locates (locates.com.br) — *GIS + IA, foco SC*

**Capacidades:**
- Viabilidade urbanística automática (cruza com Plano Diretor municipal)
- **Potencial construtivo + incentivos urbanos** aplicados automaticamente
- VGV, mapeamento de uso possível do lote
- Big Data + IA + geografia

**Backing:** investimento da Brognoli, lançou FII próprio recentemente.
**Origem:** Florianópolis, foco SC/Sul.
**Lacuna:** não cobre SP interior. Sem off-market.

---

### 📊 DataZap (datazap.com.br) — *fonte de dado, não software*

- Inteligência do Grupo OLX (ZAP + VivaReal + OLX consolidados)
- **Maior base de dados do setor** no Brasil
- Reports periódicos (Radar Imobiliário, termômetro mercado)
- API via Portal de Integração GrupoZap (developers.grupozap.com)
- Equipe de economistas + cientistas de dados

**Tipo:** vendem dado e insight, não plataforma de viabilidade.
**Risco:** se OLX bloquear scraping externo, fonte de portais sofre.

---

### 🏠 Compro Terreno (comproterreno.com.br) — *spin do Hiperdados*

Módulo ComproTerreno do Hiperdados vendido standalone. IA + Big Data + viabilidade + landbank + vendas/recebíveis. Mesmo público enterprise.

---

## 3. Diagnóstico do estágio atual

### Comparativo de capacidades

| Capacidade | Urbit | Oferta T. | Hiperdados | Locates | DataZap | **MaríliaBot** |
|---|---|---|---|---|---|---|
| Scraping portais próprio | ❌ | ❌ | ❌ | ❌ | ✅ (dono) | ✅ Viva/ZAP/Chaves/Imovelweb |
| Off-market (leilão, inventário, IPTU dev., alvará) | parcial | ❌ | ❌ | ❌ | ❌ | ✅ **4 coletores** |
| Dedup cross-portal | ❌ | ❌ | ❌ | ❌ | parcial | ✅ fingerprint + land-aware |
| LLM scoring qualitativo | ❌ | parcial | ❌ | ❌ | ❌ | ✅ Claude (analyst, scorer_llm) |
| AVM próprio | ✅ SP/BH | ✅ | ❌ | ✅ | ✅ | ✅ `price_model.py` 21k |
| Viabilidade (TIR/VPL/VGV) | parcial | ✅ | ✅ | ✅ | ❌ | ✅ `viability.py` 24k |
| Zoneamento/regulatório | ✅ SP/BH | ✅ | parcial | ✅ SC | ❌ | ✅ `regulatory.py` + zoning_marilia |
| SINAPI / custo obra | ❌ | parcial | ❌ | ❌ | ❌ | ✅ `sinapi.py` |
| Tracking "anúncio sumiu = vendeu" | ❌ | ❌ | ❌ | ❌ | parcial | ✅ `sales_tracker.py` |
| Vision (fotos anúncio) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `vision.py` 15k |
| Litígio vendedor/inventário | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `seller_litigation.py` |
| Telegram alerts | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `telegram_bot.py` |
| Feedback loop (calibração) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `feedback_loop.py` 18k |
| Cobertura Marília-SP | parcial | parcial | parcial | ❌ | parcial | ✅ **nativo** |
| Materiais/insumos (Leroy/Telhanorte) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `materials/` |
| Carteira recebível / ERP / vendas | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| GIS visual (mapa interativo) | ✅ | ✅ | ✅ | ✅ | ❌ | parcial dashboard |
| Plano Diretor parser estruturado | ✅ | ✅ | parcial | ✅ | ❌ | parcial |
| Permuta financeira / cenários | ❌ | ✅ | ✅ | ✅ | ❌ | parcial |

### Resumo do estágio

**Posição rara:** coleta superior a todos, análise comparável, escopo hiperlocal único em Marília. Nenhum competidor cruza on-market + off-market + leilão + IPTU devedor + inventário TJSP + alvará prefeitura.

**Gaps identificados:**
1. Sem GIS interativo (mapa heatmap + zoneamento sobreposto)
2. Sem parser estruturado do Plano Diretor de Marília (regulatory_geo existe mas falta normalização)
3. Sem cenários financeiros comparativos (TIR sensitivity, what-if permuta)
4. Sem ingestão cartorial (matrícula, ônus, ITBI)
5. Sem IBGE granular (setor censitário ≠ só município)
6. Sem modelo de demanda MCMV (perfil de comprador, renda, bairro alvo)
7. Sem grafo de relacionamento (proprietário ↔ matrículas ↔ CNPJ ↔ sócios)
8. Sem custo de obra granular por tipologia/bairro
9. Vision subutilizado (não extrai padrão construtivo / idade / conservação estruturado)
10. Sem benchmark histórico de absorção bairro × m² (existe migration 009 mas falta camada analítica)

**Stack atual:** Python 3.12+ · Supabase PostgreSQL · Claude API + Gemini Vision · LightGBM · cloudscraper + Playwright · GitHub Actions · ~3.5k linhas core · 31 migrations · 14 collectors · 3 workflows.

---

## 4. Plano de Construção

### Princípios de execução

- **Migrations sempre aditivas** — nunca quebrar schema existente
- **Toggle por env var** — feature nova roda com `ENABLE_X=1`, fallback silencioso
- **Backfill batched** — script `scripts/backfill_<feature>.py` para histórico
- **Cada feature = 1 PR + 1 migration + 1 teste smoke**
- **Telegram alert por feature** — sente quando funciona
- **Custo target: ≤R$30/mês original** — após brain completo, esperado ~R$110/mês

### Roadmap de 6 meses — 18 milestones

```
M1  (sem 1-2)   ITBI ingestion         → ground truth de preço
M2  (sem 3-4)   PDM Marília parser     → regulatory estruturado
M3  (sem 5-6)   IBGE setor censitário  → enrichment granular
M4  (sem 7-8)   Cartório/Matrícula     → ônus + proprietário
M5  (sem 9-10)  Grafo proprietários    → cross-refs
M6  (sem 11-12) AVM v2 calibrado       → precisão real
M7  (sem 13-14) Vision v2 estruturado  → features visuais
M8  (sem 15-16) Custo obra granular    → orçamento auto
M9  (sem 17-18) Demanda MCMV           → demand model
M10 (sem 19-20) Agente cenários        → comparador
M11 (sem 21)    Reasoning explainer    → prosa decisional
M12 (sem 22)    Detector temporal      → eventos disparam reavaliação
M13 (sem 23)    Risk scorer v2         → score composto
M14 (sem 24)    GIS interno            → mapa
M15 (sem 25)    Chat RAG               → consulta o brain
M16 (sem 26)    Backtesting            → replay histórico
M17 (cont)      Feedback loop expand   → auto-tuning
M18 (cont)      Drift monitoring       → auto-alert
```

### FASE 1 — Dado bruto faltante (sem 1-8)

#### M1 — ITBI Marília
- **Por quê primeiro:** AVM hoje treina em preço **anunciado**, não fechado. ITBI = preço real. Recalibra TUDO downstream.
- **Entregas:**
  - `src/collectors/itbi_marilia.py`
  - `sql/032_itbi_transactions.sql` — `itbi_transactions(id, matricula, lat, lng, bairro, valor_venda, valor_avaliado, area, data, tipo)`
  - `scripts/backfill_itbi.py` — 24 meses retroativo
  - Refactor `src/comps.py` para usar ITBI quando disponível
  - GH Actions: cron mensal (dia 1)
- **Risco:** prefeitura pode não publicar estruturado → fallback LAI manual + parser PDF
- **Success:** ≥500 transações reais ingeridas, AVM RMSE cai ≥15%

#### M2 — Plano Diretor Marília parser
- `src/regulatory/pdm_parser.py` — extrai LC vigente (PDF → estruturado)
- `sql/033_zoning_rules.sql` — `zoning_rules(zona, ca_basico, ca_maximo, to_max, recuo_frontal, recuo_lateral, gabarito_max, uso_permitido[])`
- Seed: 100% das zonas Marília (ZR1, ZR2, ZR3, ZC1, ZE, ZI, ZPA, ZEIS...)
- Refactor `src/regulatory.py` para consultar `zoning_rules`
- **Success:** Hunter passa a usar CA real, não estimado

#### M3 — IBGE setor censitário
- `src/collectors/ibge_setor.py` — baixa shapefile Marília + parse
- `sql/034_ibge_setores.sql` — com PostGIS habilitado
- `enrich_with_ibge(lat, lng)` via ST_Contains
- Backfill todos imóveis: setor + renda
- **Success:** 100% imóveis com setor + renda regional

#### M4 — Cartório / Matrícula
- `src/collectors/cartorio_sp.py` — ONR + 1º/2º CRI Marília
- `sql/035_matriculas.sql` — `matriculas(id, numero, lat, lng, proprietario_cpf_cnpj, area, onus[], penhoras[], hipotecas[], last_update)`
- Trigger: novo lote → enfileira consulta matrícula async
- Budget mensal limitado em consultas pagas
- **Risco alto:** viabilidade técnica/jurídica ONR
- **Success:** Top-50 lotes do mês com matrícula resolvida

### FASE 2 — Inteligência (sem 9-16)

#### M5 — Grafo de proprietários
- **Decisão:** Supabase + tabelas grafo (não Neo4j puro). Mantém stack, recursive CTE até prof 5 funciona até 10M edges.
- `sql/036_ownership_graph.sql`:
  - `entities(id, type, identifier, name)`
  - `relationships(src, dst, type, evidence_url, valid_from, valid_to)`
- `src/graph/owner_resolver.py` — `lots_by_owner(cpf)`, `cluster_by_company(cnpj)`, `litigation_chain(entity)`
- Integra `seller_litigation.py` + `inventario_tjsp.py` + matrículas (M4)

#### M6 — AVM v2 calibrado ITBI
- Refactor `price_model.py` — fontes: `asking` e `closed` (ITBI)
- Pesos: 0.3 asking + 0.7 closed quando ambos
- Confidence interval por bairro × tipologia
- Output: `predicted_closed_price`, `predicted_asking_price`, `gap_estimate`
- **Success:** RMSE documentado por bairro/tipologia

#### M7 — Vision v2 features estruturadas
- Expandir prompt Gemini Vision: `acabamento` (popular/médio/alto), `idade_aparente`, `conservacao`, `garagem_coberta`, `jardim`, `muro_tipo`, `padrao_construtivo`
- `sql/037_vision_features_v2.sql`
- Regressor: features visuais → ajuste % sobre AVM base
- Backfill últimos 6 meses

#### M8 — Custo obra granular Marília
- Combinar SINAPI + Leroy/Telhanorte
- `sql/038_unit_cost_models.sql` — `unit_cost_models(tipologia, area_min, area_max, custo_m2_base, custo_m2_alto, regiao_marilia, last_update)`
- Tipologias: MCMV térrea 45m², MCMV sobrado 60m², médio 150m², médio-alto 250m²
- `src/cost_estimator.py` novo
- Integrar em `viability.py`

### FASE 3 — Síntese / Raciocínio (sem 17-23)

#### M9 — Demand model MCMV
- Coletor Caixa MCMV (limites/filas/contratos por região)
- Modelo: renda IBGE + estoque atual + absorção histórica → demanda residual
- `sql/039_demand_model.sql` — `demand_estimates(bairro, faixa_mcmv, demanda_unidades, absorcao_meses)`
- **Success:** cada cenário no Hunter mostra "absorção esperada N meses"

#### M10 — Agente de cenários
- `src/scenarios/generator.py` — dado lote, gera N cenários:
  - MCMV F1/F2/F3 (X unidades)
  - Médio padrão Y unidades
  - Venda raw + markup
  - Permuta financeira
- Cada cenário: VGV + custo (M8) + TIR + payback + risco (M13) + demanda (M9)
- `sql/040_scenario_runs.sql` — histórico
- Claude Sonnet sintetiza ranking + justificativa
- PDF via `reporter.py`

#### M11 — Reasoning explainer
- Expandir `avm_explain.py` → `decision_explainer.py`
- Prosa estruturada citando inputs reais
- Persiste em `decision_tracking` (mig 019)
- Telegram alert mostra reasoning resumido

#### M12 — Detector temporal de eventos
- `src/collectors/diario_oficial_marilia.py`
- Detect: alvará novo, loteamento aprovado, mudança zoneamento, desapropriação
- `sql/041_temporal_events.sql`
- Job: evento novo → reavalia lotes no raio → re-score
- **Success:** ≥1 evento/semana detectado

#### M13 — Risk scorer v2
- Refactor `risk_scorer.py` (5k → ~10k)
- 4 dimensões: regulatório, vendedor, construtivo, mercado
- Score composto 0-100 + sub-scores
- Hunter multiplica pontuação por (1 - risk/100)

### FASE 4 — Interface (sem 24-26)

#### M14 — GIS interno
- Dashboard React + **Maplibre GL**
- Tiles: OSM + zoneamento (M2) + setores IBGE (M3) + lotes
- Layers: on-market / off-market / leilão / inventário / heatmaps
- Tile server: PostGIS + pg_tileserv

#### M15 — Chat RAG sobre o brain
- pgvector — `brain_embeddings(entity_id, entity_type, content, embedding)`
- Embed: cada análise gerada, cada lote, cada cenário, cada decisão
- `src/brain_chat.py` — Claude Sonnet + tool use (`query_sql`, `search_embeddings`, `get_lot`, `get_scenarios`)
- Interface: Telegram `/ask <pergunta>`
- Haiku triagem, Sonnet resposta complexa

### FASE 5 — Auto-evolução (contínuo)

#### M16 — Backtesting
- Replay `hunter_score_history` (mig 020) últimos 12m
- `scripts/backtest.py` — output relatório
- ROI hipotético se seguido scoring

#### M17 — Feedback loop expandido
- `feedback_loop.py` (18k) — labels de decisão real (comprei/passei/vizinho vendeu por mais)
- Retreino mensal pesos Hunter
- A/B silencioso de 2 versões scorer

#### M18 — Drift monitoring
- `reporter_drift.py` (3k) — expandido
- Detecta: AVM erro > threshold, coletor anômalo, ITBI atrasado
- Telegram alert saúde semanal

### Orçamento de custo mensal

| Item | Hoje | Após M18 |
|---|---|---|
| Supabase | $0 | $25 (se >500MB) |
| Claude API (Haiku massa + Sonnet síntese) | ~R$15 | ~R$40 |
| Gemini Vision | ~R$5 | ~R$15 |
| Consultas cartório/ITBI | R$0 | R$30 |
| GH Actions (free tier) | $0 | $0 |
| **Total** | **~R$20** | **~R$110/mês** |

Acima do target original (R$30) — mas razoável para o moat. Se manter R$30, M4 (cartório pay-per-call) corta primeiro.

### Dependências novas (pyproject.toml)

```toml
"pgvector>=0.2"            # M15
"pdfplumber>=0.11"         # M2
"geopandas>=1.0"           # M3
"shapely>=2.0"             # M3
"networkx>=3.3"            # M5
"pdfminer.six>=20240706"   # M1
```

Frontend dashboard:
```json
"maplibre-gl": "^4.x"
```

### Estrutura final do repo (após 6 meses)

```
src/
  collectors/
    on_market/          # viva, zap, chaves, imovelweb, toca, uniao
    off_market/         # leilao_caixa, leilao_generico, alvara, inventario, iptu
    institutional/      # itbi, cartorio_sp, ibge_setor, caixa_mcmv, dom_marilia [NOVOS]
  regulatory/
    pdm_parser.py       [NOVO]
    zoning_rules.py     [refactor]
  graph/
    owner_resolver.py   [NOVO]
  scenarios/
    generator.py        [NOVO]
  cost/
    estimator.py        [NOVO]
  demand/
    mcmv_model.py       [NOVO]
  brain/
    chat.py             [NOVO]
    decision_explainer.py [refactor de avm_explain]
  vision/               [refactor do vision.py]
  ...resto atual mantido
sql/                    # ~50 migrations totais
scripts/
  backfill_itbi.py
  backfill_ibge.py
  backtest.py
dashboard/              # + GIS Maplibre
.github/workflows/
  pipeline.yml
  daily-materials.yml
  weekly-report.yml
  monthly-itbi.yml      [NOVO]
  monthly-ibge.yml      [NOVO]
  drift-check.yml       [NOVO]
```

### Critérios de "brain monstro" (definição de pronto)

Ao fim de M18, o sistema deve:

1. Ingerir on-market + off-market + leilão + inventário + IPTU + ITBI + cartório + alvará + DOM automaticamente
2. Conhecer zoneamento real de cada lote
3. Conhecer renda regional de cada lote
4. Conhecer proprietário e histórico
5. Estimar preço fechado real (não anunciado)
6. Extrair padrão visual estruturado
7. Estimar custo construção por tipologia
8. Estimar demanda MCMV por bairro/faixa
9. Gerar N cenários comparados por lote com TIR/VPL/risco/absorção
10. Explicar cada decisão em prosa auditável
11. Detectar eventos temporais e reavaliar
12. Visualizar em mapa com layers
13. Responder pergunta natural sobre o brain
14. Backtest histórico
15. Aprender com decisões reais

---

## 5. Decisão estratégica

> **"Devo focar em mais dado, ou em mais inteligência (grafo/RAG/Neo4j)?"**

**Resposta:** dado primeiro — **mas com schema do grafo já correto desde o byte 1**.

Grafo vazio não pensa. Neo4j com 50 nodes é dashboard chique. Grafo poderoso = **muitos fatos + arestas ricas + procedência**. Hoje há dado para ~10% do que o grafo precisa para ser interessante. Ingerir mais é prioridade — mas modelando como **knowledge graph desde já**, não como tabela relacional plana que se "graficiza" depois.

### Regra do grafo imobiliário

> **Toda fonte que revela RELAÇÃO vale 10× toda fonte que revela LISTAGEM.**

Listagem (Viva/Zap/Chaves) = anúncio = ponto isolado. Relação = aresta = "Fulano vendeu para Beltrano em 2024 por R$X via ITBI #1234". Aresta = inteligência.

### O que torna o grafo INTELIGENTE (além de só ter dado)

#### 5.1 Entity Resolution ("quem é quem")
"José Silva" no Viva = "J. Silva" no ITBI = "José A. Silva" matrícula = mesma pessoa?
- CPF/CNPJ quando disponível = chave de ouro
- Sem CPF: fuzzy match nome + telefone + endereço + lote já conhecido
- Confidence score por match (`merged_with_confidence: 0.87`)
- Tabela `entity_aliases` mantém pontes

#### 5.2 Procedência por aresta (provenance)
Toda aresta tem 4 metadados obrigatórios:
- `source` (URL ou ID do documento)
- `extracted_at` (quando coletei)
- `confidence` (0-1, alto se ITBI/matrícula, baixo se LLM inferiu)
- `valid_from` / `valid_to` (temporal — proprietário muda)

Sem isso: não consegue auditar, não consegue desfazer, não consegue raciocinar histórico.

#### 5.3 Grafo temporal
Pergunta vital: "quem era dono deste lote em 2022?"
- Edges com `valid_from`/`valid_to`
- Query: "as of 2022-06-01, who owned lot X?"
- Permite **backtest real**: testar Hunter score com info que existia naquela data, não info presente

#### 5.4 Hipóteses vs Fatos
LLM vai inferir: "Construtora X parece controlada pelo João pq ele é sócio de 3 empresas que fizeram obras juntas". Isso **NÃO É FATO**, é hipótese.
- Aresta `type: hypothesis`, `confidence: 0.6`
- Pipeline tenta confirmar com fonte primária
- Se confirmado → vira `fact`. Se contradito → vira `disputed`

#### 5.5 Event sourcing
Cada mudança = evento imutável.
- `events(id, timestamp, type, payload, source)`
- Grafo é **projeção** dos eventos, não estado mutável
- Permite replay total / undo / auditoria

#### 5.6 Análise de rede (network analytics)
Com grafo populado:
- **Centralidade** — quem é hub do mercado local? (corretor X aparece em 40% das vendas → conhecer ele = inteligência)
- **Comunidades** — clusters de construtoras + corretores + advogados que sempre operam juntos
- **Caminhos** — "este lote pertence a quem? esse cara é sócio de quem? essas empresas têm obra em qual região?"
- **Anomalias** — lote vendido 3× em 6 meses = flip suspeito / lavagem

#### 5.7 Causal mining
- Detecta: "alvará novo zona X → preços +12% em 90 dias na zona X" (correlação)
- Detecta: "construtora Y entrou no bairro → outras 2 entraram em 6m" (efeito manada)
- Padrões viram **alertas preditivos**

#### 5.8 Memória episódica (RAG)
- Toda análise gerada (cenários, decisões, relatórios) → embedding → pgvector
- "Por que decidimos passar do lote Z em março?" → recupera o relatório original
- Brain lembra do **próprio raciocínio**

---

## 6. Arquitetura do Knowledge Graph

### Stack híbrida (melhor que Neo4j puro)

```
┌─────────────────────────────────────────────┐
│  Postgres + Supabase (transacional + grafo) │
│  - tables: entities, relationships, events  │
│  - PostGIS: geo                              │
│  - pgvector: embeddings (RAG)                │
│  - recursive CTEs: walk grafo até prof 5     │
└─────────────────────────────────────────────┘
                    +
┌─────────────────────────────────────────────┐
│  Neo4j AuraDB free (analytics pesado)       │
│  - réplica derivada do Postgres             │
│  - centralidade, comunidade, pathfinding    │
│  - Cypher quando precisar                    │
└─────────────────────────────────────────────┘
                    +
┌─────────────────────────────────────────────┐
│  Claude / Gemini (raciocínio)               │
│  - tool use: query SQL, query Cypher, RAG   │
│  - gera hipóteses, sumariza, explica        │
└─────────────────────────────────────────────┘
```

**Por que não só Neo4j:** perde PostGIS + Supabase realtime + RLS + custo + stack já consolidada. Postgres faz grafo até ~10M edges sem suor. Neo4j entra só para analytics que SQL recursivo sofre.

### Schema central do grafo

```sql
-- entidades
entities(
  id uuid pk,
  type text,             -- pessoa|cnpj|lote|imovel|empreendimento|orgao|processo
  canonical_name text,
  identifiers jsonb,     -- {cpf, cnpj, matricula, inscricao_imob}
  attributes jsonb,
  created_at, updated_at
)

-- aliases (entity resolution)
entity_aliases(
  entity_id uuid,
  alias text,
  source text,
  confidence float
)

-- relacionamentos (arestas)
relationships(
  id uuid pk,
  src_entity uuid,
  dst_entity uuid,
  type text,             -- owns|sold_to|partner_of|heir_of|granted_poa|engineer_of|...
  attributes jsonb,      -- {price, area, ...}
  source text,           -- URL/doc
  source_doc_id text,
  confidence float,
  is_hypothesis bool,
  valid_from date,
  valid_to date,         -- null = ativo
  created_at
)

-- eventos imutáveis
events(
  id uuid pk,
  ts timestamptz,
  type text,             -- itbi_recorded|matricula_updated|alvara_issued|listing_appeared|...
  entity_refs uuid[],
  payload jsonb,
  source text
)

-- embeddings (RAG)
brain_embeddings(
  entity_id uuid,
  content_type text,
  content text,
  embedding vector(1536)
)

-- hipóteses pendentes
hypotheses(
  id uuid pk,
  description text,
  evidence jsonb[],
  confidence float,
  status text,           -- pending|confirmed|refuted
  created_by text        -- llm-claude|rule-engine
)
```

---

## 7. Fontes de dado por tier

### TIER S — sem isso, não tem cérebro

| Fonte | O que revela | Aresta gerada |
|---|---|---|
| **ITBI Marília** | quem vendeu para quem, por quanto, quando | `pessoa --sold_lot--> pessoa [price, date]` |
| **Cartório Matrícula (ONR/CRI SP)** | proprietário atual, ônus, hipoteca, histórico | `pessoa --owns--> lote`, `lote --has_lien--> banco` |
| **JUCESP / Receita QSA** | sócios de construtoras/imobiliárias locais | `pessoa --partner_of--> cnpj`, `cnpj --controls--> cnpj` |

### TIER A — multiplicam o grafo

| Fonte | Revela | Aresta |
|---|---|---|
| **TJSP processos** (já tem `inventario_tjsp` + `seller_litigation`) | inventário, divórcio, execução | `pessoa --heir_of--> falecido`, `lote --litigated--> processo` |
| **Cartório de Notas SP** | procurações, escrituras públicas | `pessoa --grants_poa_to--> pessoa` |
| **Cartório de Protesto** | inadimplência | `pessoa --has_protest--> credor [valor, data]` |
| **Diário Oficial Marília** | alvará, desapropriação, leilão público, mudança zoneamento | `lote --got_permit--> data`, `lote --rezoned--> nova_zona` |
| **CREA-SP** | engenheiro responsável por obra | `pessoa --engineer_of--> obra --on--> lote` |
| **CRECI-SP** | corretores ativos | `pessoa --broker_of--> imovel` |
| **Caixa MCMV — contratos publicados** | unidades vendidas, construtora, faixa | `cnpj --delivered--> empreendimento [unidades, faixa]` |

### TIER B — sinais indiretos (proxies de movimento)

| Fonte | Revela |
|---|---|
| **CEMIG / EDP / CPFL** (ligações novas) | obra finalizada, ocupação |
| **Sabesp** (ligações novas) | idem |
| **Correios** (novos CEPs/endereços) | loteamento entregue |
| **TCESP contratos** | obra pública na região (valoriza entorno) |
| **CNDT / Dívida Ativa estadual** | proprietário enrolado = pressão venda |
| **Imagens satélite** (Sentinel-2, livre) | construção começou/parou — delta antes/depois |
| **OSM edits** (OpenStreetMap) | comunidade marcou novo prédio |

### TIER C — luxo, depois

- Instagram/Facebook imobiliárias Marília (anúncios off-portal)
- LinkedIn (vínculos corporativos construtoras locais)
- WhatsApp grupos (semi-impossível ético, ignorar)

---

## 8. Sequência de execução recomendada

```
1. Schema do grafo PRIMEIRO (1 semana)
   ↳ Migration 032: entities/relationships/events/embeddings/hypotheses
   ↳ Sem isso, cada coletor novo vira tabela plana e gera dívida

2. Refactor coletores existentes para emitir eventos + arestas (2 semanas)
   ↳ Viva/Zap/leilão/inventário/IPTU/alvará → escrevem em events + relationships
   ↳ Mantém tabelas antigas como views

3. Entity resolution layer (1 semana)
   ↳ Job que deduplica pessoa/CNPJ across fontes
   ↳ Tabela merges + alias

4. Ingerir fontes TIER S em ordem (6-8 semanas)
   M1. ITBI         → arestas sold_to
   M2. Matrícula    → arestas owns + has_lien
   M3. JUCESP/QSA   → arestas partner_of

5. TIER A (4-6 semanas)
   M4. Notas / Protesto / DOM / CREA / CRECI / MCMV

6. Camada de raciocínio (3-4 semanas)
   - Hypothesis engine (LLM gera hipóteses marcadas)
   - Causal miner (regras de correlação alvará→preço)
   - Network analytics (sync para Neo4j Aura)
   - RAG sobre eventos + análises

7. TIER B sinais (paralelo, contínuo)
   - Satélite, concessionárias, OSM
```

### Próximo passo concreto

**Migration do schema do grafo** (`sql/032_knowledge_graph.sql`) — é a fundação que destrava tudo. Sem ela, cada coletor novo vira dívida arquitetural.

---

## Apêndice — contexto de negócio

**BM3 Construtora (família Rezende):**
- Pai = gestor, irmão = engenheiro civil, Matheus (eu) = tech
- Já construíram e venderam casas, 2 paradas esperando venda
- Tiveram problemas com desdobramento de terreno em condomínio
- Investimento por obra: até R$500k capital próprio
- Curto prazo: MCMV | Longo prazo: médio/alto padrão + carteira de aluguel
- 6 problemas diagnosticados: sem planejamento, orçamento impreciso, mão de obra, desalinhamento produto-mercado, burocracia jurídica, gestão descentralizada
- Começaram pelo módulo de Inteligência Comercial (resolve o problema que mais dói)

**Filosofia atual:**
- **NÃO virar SaaS por enquanto.** Construir "brain monstro" privado para a família primeiro.
- Profundidade > polish. Sem UI bonita, sem onboarding, sem pricing.
- Se um dia virar SaaS, o moat já estará pronto: dado + entidades + grafo + raciocínio que ninguém terá em 2-3 anos.

---

*Fim do documento. Atualizar à medida que decisões mudem.*

# MariliaBot — Inteligencia Imobiliaria

Sistema de inteligencia imobiliaria para Marilia-SP. Coleta automatica de 6 fontes, analise com IA, scoring de oportunidades, simulador financeiro MCMV e dashboard interativo com mapa.

Desenvolvido para a **BM3 Construtora**, focado em responder: **ONDE, O QUE e QUANDO construir**.

## Arquitetura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  6 Fontes   │────▶│ 15 Agentes   │────▶│  Supabase   │────▶│  Dashboard   │
│  de Dados   │     │  Python/IA   │     │  PostgreSQL │     │  React/Vite  │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
       │                   │                                        │
       ▼                   ▼                                        ▼
 ┌───────────┐      ┌──────────┐                             ┌──────────────┐
 │  SINAPI   │      │ Telegram │                             │   Leaflet    │
 │  IBGE     │      │ Alertas  │                             │   Recharts   │
 │  CRECI    │      │ Reports  │                             │   Filtros    │
 └───────────┘      └──────────┘                             └──────────────┘
```

## Pipeline Diario (GitHub Actions — 06:00 BRT)

```
Collect (6 fontes, paralelo)    ~3 min
  ↓
Normalize + Classify            ~1 min
  ↓
Enrich (LLM)                    ~3 min
  ↓
Deduplicate                     ~10s
  ↓
Analyze + Trends                ~4 min
  ↓
Sales Tracker + Market Heat     ~20s
  ↓
Hunt + Score + Risk             ~2 min
  ↓
Viability + Comps               ~1 min
  ↓
Notify + Alerts                 ~5s
                          Total: ~12 min
```

## Fontes de Dados

| Fonte | Tipo | Listings | Status |
|-------|------|----------|--------|
| Uniao (DreamKeys) | REST API | ~1.000 | Ativo |
| Toca Imoveis | Supabase REST | ~2.000 | Ativo |
| VivaReal | HTML Scraping | ~600 | Ativo |
| Chaves na Mao | HTML Scraping | ~300 | Ativo |
| Imovelweb | HTML Scraping | ~120 | Ativo (CF limita) |
| ZAP Imoveis | HTML Scraping | ~600 | Ativo |
| **SINAPI/IBGE** | API publica | Indices | Ativo |
| **CRECI-SP** | LLM extraction | Benchmarks | Ativo |

## Agentes (15 modulos)

### Coleta e Processamento
| Agente | Arquivo | Funcao |
|--------|---------|--------|
| Collectors (6x) | `src/collectors/*.py` | Coleta dados brutos das 6 fontes |
| Normalizer | `src/normalizer.py` | Raw → listings estruturados, validacao semantica, deactivation tracking |
| Classifier | `src/classifier.py` | Classifica em 11 tiers (MCMV/baixo/medio/alto por tipo) |
| Deduplicator | `src/deduplicator.py` | Scoring continuo cross-portal, selecao canonica |

### Enriquecimento
| Agente | Arquivo | Funcao |
|--------|---------|--------|
| Enricher | `src/enricher.py` | Geocoding via Nominatim |
| Enricher LLM | `src/enricher_llm.py` | Extracao de atributos e normalizacao de bairros via Gemini |
| Address | `src/address.py` | Normalizacao de enderecos brasileiros |

### Analise e Inteligencia
| Agente | Arquivo | Funcao |
|--------|---------|--------|
| Analyst | `src/analyst.py` | Snapshots de mercado, metricas por bairro, absorcao, centroid |
| Trends | `src/trends.py` | Deteccao de aquecimento/esfriamento por bairro |
| Sales Tracker | `src/sales_tracker.py` | Detecta vendas (listings removidos = proxy) |
| Market Heat | `src/market_heat.py` | Score composto 0-100 por bairro |
| Price Model | `src/price_model.py` | Random Forest para estimar valor justo |

### Oportunidades e Decisao
| Agente | Arquivo | Funcao |
|--------|---------|--------|
| Hunter | `src/hunter.py` | Scoring 10 criterios para terrenos |
| Viability | `src/viability.py` | Simulador VGV/TIR/Payback com SINAPI real |
| Risk Scorer | `src/risk_scorer.py` | Avaliacao de risco (zoneamento, ambiental, legal) |
| Comps | `src/comps.py` | Analise de comparaveis (k-NN) |
| Alerts | `src/alerts.py` | Saved searches com notificacao automatica |

## Dashboard — 6 Paginas

| Pagina | Descricao |
|--------|-----------|
| **Overview** | KPIs, classificacao por tier, mapa + tendencias, benchmarks |
| **Mapa** | Bubbles por bairro com 3 modos: Preco / Risco / Calor do mercado |
| **Decisao** | Painel "Devo construir aqui?" — semaforo GO/NO-GO por bairro |
| **Viabilidade** | Calculadora interativa: preco + area → 4 cenarios MCMV lado a lado |
| **Mercado** | Tendencia temporal de preco/m², benchmarks CRECI/SINAPI/IBGE |
| **Oportunidades** | Tabela ranqueada com score breakdown expandivel |

### Filtros Globais
Tipo de imovel, fonte, classificacao, faixa de preco, faixa de area, periodo, MCMV, bairro — aplicados em todas as paginas.

## Simulador de Viabilidade MCMV

O sistema calcula automaticamente para cada terreno:

```
Inputs:  Preco terreno + Area + SINAPI/m² (real da API IBGE)
         ↓
Custos:  Terreno + (SINAPI × area × BDI 30%) + Infra 12% + Projetos 5%
         + Marketing 3% + Admin 4% + Impostos 4%
         ↓
Receita: Unidades × Preco venda (teto MCMV por faixa)
         ↓
Output:  VGV, Margem bruta/liquida, ROI, TIR anual, Payback
         + Cenarios otimista/pessimista (±10% custo)
         ↓
Decisao: GO (margem ≥15%, payback ≤4 anos) / NO-GO
```

4 cenarios automaticos: MCMV Faixa 1, Faixa 2, Faixa 3, Casa Padrao.

## Tech Stack

**Backend:** Python 3.12+, Supabase, Gemini 2.0 Flash Lite, scikit-learn, BeautifulSoup4, httpx, rapidfuzz

**Frontend:** React 19, TypeScript, Vite, Tailwind CSS 4, Leaflet, Recharts, lucide-react

**Infra:** GitHub Actions (cron diario), Telegram Bot API

## Setup

```bash
# Backend
cp .env.example .env  # preencher credenciais
pip install -e .

# Frontend
cd dashboard
npm install
```

### Variaveis de Ambiente

```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJ...              # service_role key
TOCA_SUPABASE_URL=https://xxxxx.supabase.co
TOCA_ANON_KEY=eyJ...
GEMINI_API_KEY=AIza...           # Gemini 2.0 Flash Lite
TELEGRAM_BOT_TOKEN=123456:ABC... # opcional
TELEGRAM_CHAT_ID=-100123456789   # opcional
MAX_PAGES_PER_SPIDER=20
```

## Comandos CLI

```bash
# Pipeline completo
python -m src.main pipeline

# Coleta
python -m src.main collect [uniao|toca|vivareal|chavesnamao|imovelweb|zapimoveis]

# Processamento
python -m src.main normalize     # Normaliza + desativa stale listings
python -m src.main classify      # Classifica por tier (~11s para 7K listings)
python -m src.main dedup         # Deduplicacao cross-portal

# Enriquecimento
python -m src.main enrich        # Geocoding
python -m src.main enrich-llm    # Atributos via Gemini

# Analise
python -m src.main analyze       # Snapshots + metricas por bairro
python -m src.main trends        # Tendencias de preco
python -m src.main sales         # Vendas estimadas (listings removidos)
python -m src.main heat          # Indice de calor por bairro

# Inteligencia
python -m src.main hunt          # Scoring de terrenos
python -m src.main score-llm     # Segunda opiniao LLM
python -m src.main risk          # Avaliacao de risco
python -m src.main viability     # Simulacao VGV/TIR/Payback
python -m src.main comps         # Comparaveis (k-NN)
python -m src.main price-model   # Predicao de preco (Random Forest)

# Dados publicos
python -m src.main sinapi        # Custo construcao IBGE/SINAPI
python -m src.main ibge          # Demograficos + demanda MCMV
python -m src.main creci         # Benchmarks CRECI-SP

# Notificacoes
python -m src.main notify        # Alertas Telegram
python -m src.main alerts        # Saved searches + notificacao
python -m src.main report        # Relatorio semanal executivo
```

## Banco de Dados (Supabase)

11 migrations em `sql/`:

| Tabela | Registros | Descricao |
|--------|-----------|-----------|
| `listings` | ~7.000+ | Imoveis normalizados de 6 fontes |
| `raw_listings` | ~20.000+ | Dados brutos antes da normalizacao |
| `neighborhoods` | ~400 | Metricas agregadas (preco, absorcao, heat, risco) |
| `market_snapshots` | ~160/dia | Series temporais por tipo e bairro |
| `opportunities` | ~375 | Terrenos pontuados (score 30-95) |
| `viability_studies` | ~200 | Simulacoes VGV/TIR por cenario |
| `listing_matches` | ~90 | Matches de deduplicacao |
| `market_indices` | ~30 | SINAPI, IBGE, CRECI |
| `sold_estimates` | acumula | Vendas estimadas (listings removidos) |
| `saved_searches` | config | Criterios de busca para alertas |
| `company_projects` | manual | Projetos proprios da construtora |
| `agent_runs` | ~120/dia | Log de execucao dos agentes |

## Estrutura do Projeto

```
├── src/
│   ├── main.py               # Orquestrador CLI (20+ comandos)
│   ├── collectors/
│   │   ├── base.py            # BaseCollector com batch upsert + dedup
│   │   ├── uniao.py           # DreamKeys API
│   │   ├── toca.py            # Supabase REST
│   │   ├── vivareal.py        # HTML + JSON-LD
│   │   ├── chavesnamao.py     # HTML scraping
│   │   ├── imovelweb.py       # HTML + JSON-LD
│   │   ├── zapimoveis.py      # HTML + JSON-LD (OLX Group)
│   │   ├── sinapi.py          # IBGE SINAPI API
│   │   ├── creci.py           # CRECI-SP via Gemini
│   │   └── http.py            # CloudScraper + retry
│   ├── normalizer.py          # Raw → listings + validacao + stale detection
│   ├── classifier.py          # 11 tiers (batch por tier, ~11s)
│   ├── deduplicator.py        # Scoring continuo + canonical selection
│   ├── address.py             # Normalizacao enderecos BR
│   ├── analyst.py             # Snapshots + absorcao + centroid + risco
│   ├── trends.py              # Aquecendo/esfriando/estavel
│   ├── hunter.py              # Scoring 10 criterios
│   ├── viability.py           # VGV/TIR/Payback com SINAPI
│   ├── risk_scorer.py         # Risco via Gemini
│   ├── comps.py               # k-NN comparaveis
│   ├── price_model.py         # Random Forest predicao
│   ├── sales_tracker.py       # Proxy de vendas
│   ├── market_heat.py         # Score composto 0-100
│   ├── alerts.py              # Saved searches + Telegram
│   ├── notifier.py            # Oportunidades via Telegram
│   ├── reporter.py            # Relatorio semanal executivo
│   ├── ibge.py                # Demografia + demanda MCMV
│   ├── llm.py                 # Gemini 2.0 Flash Lite
│   ├── config.py              # Variaveis de ambiente
│   └── db.py                  # Supabase client
├── dashboard/
│   └── src/
│       ├── App.tsx            # 6 paginas com sidebar
│       ├── components/
│       │   ├── Sidebar.tsx
│       │   ├── StatCard.tsx
│       │   ├── PropertyMap.tsx      # Leaflet (preco/risco/calor)
│       │   ├── DecisionPanel.tsx    # GO/NO-GO por bairro
│       │   ├── ViabilityCalculator.tsx
│       │   ├── ClassificationSummary.tsx
│       │   ├── PriceTrend.tsx       # Time series por bairro
│       │   ├── MarketBenchmarks.tsx
│       │   ├── MarketCharts.tsx
│       │   ├── OpportunitiesTable.tsx
│       │   ├── FilterBar.tsx
│       │   └── MapLegend.tsx
│       ├── hooks/
│       │   ├── useSupabase.ts
│       │   └── useFilteredData.ts
│       └── contexts/
│           └── FilterContext.tsx
├── sql/                       # 11 migrations
├── .github/workflows/
│   ├── pipeline.yml           # Pipeline diario 06:00 BRT
│   └── weekly-report.yml      # Relatorio semanal
└── pyproject.toml
```

## Licenca

Uso privado — BM3 Construtora.

# MaríliaBot — Síntese Completa do Projeto
## Documento de contexto para continuação no Claude Code

---

## SOBRE O PROJETO

### Quem somos
Construtora/incorporadora familiar em **Marília-SP**:
- **Pai** — gestor (experiência em administração)
- **Irmão** — engenheiro civil
- **Eu** — tecnologia, IA, desenvolvimento full-stack (Python, TypeScript, Next.js, Supabase)

### Histórico
- Já construímos e vendemos casas
- 2 casas paradas esperando venda (corretor cuidando)
- Tivemos problemas com desdobramento de terreno em formato condomínio

### Objetivos
- **Curto prazo:** Minha Casa Minha Vida (MCMV)
- **Longo prazo:** Casas médio/alto padrão para venda + carteira de aluguel
- **Investimento por obra:** Até R$500 mil (capital próprio)

---

## DIAGNÓSTICO DOS PROBLEMAS

Fizemos uma investigação profunda e mapeamos 6 problemas principais:

### 2.1 Ausência de Planejamento e Cronograma (CRÍTICA)
- Sem cronograma formal, sem EAP, sem Gantt
- Material chega na hora errada
- Mudanças no projeto durante execução
- Impacto: atrasos em cascata, custo fixo de obra parada

### 2.2 Orçamento Impreciso e Descontrole de Custos (CRÍTICA)
- Orçamento feito "no olho"
- Retrabalho consome recursos
- Sem reserva de contingência
- Sem composições SINAPI/TCPO
- Impacto: margem consumida, obriga baixar preço de venda

### 2.3 Dificuldade com Mão de Obra (ALTA)
- Escassez em Marília
- Contratos informais, sem métricas
- Sem checklist de qualidade por etapa
- Impacto: retrabalho, atrasos, risco trabalhista

### 2.4 Desalinhamento Produto-Mercado e Fraqueza Comercial (CRÍTICA)
- Decisão do que construir sem pesquisa de mercado
- Faltou marketing/divulgação
- Teve que baixar preço para vender
- Sem funil de vendas ou captação ativa
- Impacto: imóvel parado = capital morto

### 2.5 Burocracia e Riscos Jurídicos (ALTA)
- Dificuldade com documentação (matrícula, registro)
- Questões ambientais e de loteamento
- Problemas no desdobro em condomínio
- Sem assessoria jurídica prévia
- Impacto: obra pronta sem poder vender

### 2.6 Gestão Descentralizada (ALTA)
- Controle em planilhas Excel sem integração
- Informações dispersas (WhatsApp, caderno, cabeça)
- Sem processos padronizados

---

## DECISÃO: COMEÇAR PELO MÓDULO 3.4 — INTELIGÊNCIA COMERCIAL

O módulo escolhido para começar é a **Inteligência de Mercado + Caçador de Terrenos** porque:
1. Resolve o problema que mais dói (casas paradas, preço rebaixado)
2. Os dados gerados alimentam todas as outras decisões
3. Dá vantagem competitiva sobre outras construtoras em Marília

---

## ARQUITETURA DO SISTEMA: MaríliaBot v2

### Stack
- **Linguagem:** Python 3.12+
- **LLM:** Claude (Sonnet 4 para análise / Haiku 4 para normalização)
- **Banco de dados:** Supabase (PostgreSQL + pgvector)
- **Dashboard:** Next.js + React (consumindo Supabase direto)
- **Scheduler:** GitHub Actions (cron 2x/dia, free tier 2.000 min/mês)
- **Alertas:** Telegram Bot API
- **Orquestração:** Python puro (sem framework de agentes — asyncio + pub/sub)

### 7 Agentes Especializados

**Fase 1 — Coleta (paralelo):**
1. **🕷️ Scraper** — APENAS coleta bruta. Um adapter por fonte. Não normaliza.

**Fase 2 — Normalização (sequencial):**
2. **🧹 Normalizador** — Claude Haiku transforma raw → estruturado. Padroniza bairros, extrai atributos.

**Fase 3 — Validação + Enriquecimento (paralelo):**
3. **🛡️ Validador** — Deduplicação cross-portal, outliers, anúncio fantasma, confidence score, estimativa de preço real
4. **🗺️ Enriquecedor** — Google Maps, IBGE, SINAPI, regras MCMV da Caixa

**Fase 4 — Análise (sequencial):**
5. **📊 Analista** — Métricas por bairro, tendências, relatórios semanais

**Fase 5 — Oportunidades (sequencial):**
6. **🎯 Caçador** — Scoring de terrenos (10 critérios), alertas Telegram

**Fase 6 — Sob demanda:**
7. **🧮 Viabilidade** — Simulação de cenários (SINAPI + dados do Analista)

### Pipeline Diário
```
06:00 → Scraper (todos os spiders em paralelo) .............. ~10 min
06:10 → Normalizador (Claude Haiku, fila de raw_listings) ... ~5 min
06:15 → Validador + Enriquecedor (paralelo) ................. ~8 min
06:23 → Analista (métricas + snapshots) ..................... ~5 min
06:28 → Caçador (scoring + alertas Telegram) ................ ~5 min
       → Viabilidade (sob demanda no dashboard/Telegram)
```

### Custo Mensal Estimado
- GitHub Actions: ~R$0 (free tier)
- Supabase: ~R$0 (free tier)
- Claude API (Haiku + Sonnet): ~R$15-30/mês
- Google Maps API: ~R$0 (free tier 5.000 req/mês)
- **Total: ~R$15-30/mês**

---

## FONTES DE DADOS — RESULTADO DO RECONHECIMENTO

Fizemos reconhecimento automatizado (script Python) + inspeção manual via Claude in Chrome em 7 sites. Resultados:

### ✅ TIER 1 — APIs Abertas (Sprint 1)

#### 🏘️ União Imobiliária → API DreamKeys
- **URL:** `https://api.dreamkeys.com.br/public/properties`
- **Auth:** NENHUMA (API pública)
- **Total:** 2.643 imóveis | **440 terrenos** (type=land)
- **Dados:** preço, área, lat/lng, bairro, endereço, **flag MCMV**, fotos, IPTU, quartos, banheiros, vagas
- **Tipos válidos:** `apartment` (636), `house` (1.313), `land` (440), `commercial` (193), `rural`
- **Paginação:** `?city=Marília&page=1&limit=50&business=SALE&type=land`
- **Resposta:** JSON com `properties[]`, `total`, `page`, `totalPages`

#### 🏠 Toca Imóveis → API Supabase
- **URL:** `https://jveljofutivtmufzmiej.supabase.co/rest/v1/`
- **Anon Key:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2ZWxqb2Z1dGl2dG11ZnptaWVqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY3NDA0NzYsImV4cCI6MjA3MjMxNjQ3Nn0.Jl4X9G3Uy-4FrBRiQdVZ7Zvv0tHsg4VEq1mou1yofK0`
- **Total:** 4.500+ imóveis | **88 terrenos** (tipo_imovel="Área")
- **Dados:** titulo, tipo_imovel, bairro_nome, endereco, valor, dormitorios, banheiros, a_construida, a_terreno, garagem, descricao, lati/longi, zona_nome, caracteristicas, pontos_referencia
- **Tipos válidos:** `Apartamento` (1.174), `Casa` (2.162), `Área` (88), `Casa Em Condomínio` (562), `Chácara`
- **Filtros RPC:** `POST /rest/v1/rpc/get_filter_options` → bairros, tipos, edificios, quartos, regioes, caracteristicas
- **View principal:** `properties_public` com select de todos os campos
- **Headers:** `apikey` + `Authorization: Bearer {key}`

### ✅ TIER 2 — HTML Server-Rendered (Sprint 1-2)

#### 🏢 VivaReal → HTML SSR + BeautifulSoup
- **URL:** `https://www.vivareal.com.br/venda/sp/marilia/`
- **Total:** **13.613 imóveis** (maior fonte!)
- **30 listings por página**
- **Paginação:** `?pagina=2` (confirmado funcionando)
- **Dados:** preço, m², quartos, banheiros, vagas, bairro, rua, IPTU
- **JSON-LD:** `ItemList` (30 items) + `RealEstateListing` embutidos no HTML
- **Seletor de links:** `a[href*="/imovel/"]` → 29 por página
- **URL de terrenos específica NÃO funciona** (404) — filtrar no parsing
- **Cloudflare:** presente mas em modo observação (não bloqueou)
- **Nota:** VivaReal é SSR puro — a glue-api é chamada pelo backend, não pelo browser. Coletar via HTML.

#### 🔑 Chaves na Mão → HTML SSR + BeautifulSoup
- **URL:** `https://www.chavesnamao.com.br/imoveis-a-venda/sp-marilia/`
- **Total:** 12.561 imóveis
- **Paginação:** `?pg=2`
- **URLs por tipo:**
  - `/terrenos-a-venda/sp-marilia/`
  - `/casas-a-venda/sp-marilia/`
  - `/apartamentos-a-venda/sp-marilia/`
  - `/terrenos-em-condominio-a-venda/sp-marilia/`
- **Cloudflare:** presente mas não bloqueou (status 200)

#### 🌐 Imovelweb → HTML SSR + BeautifulSoup
- **URL:** `https://www.imovelweb.com.br/terrenos-venda-marilia-sp.html`
- **Terrenos:** **532**
- **Também:** `casas-venda-marilia-sp.html`
- **Paginação:** provavelmente `-pagina-2.html`
- **Dados:** preço, área total, bairro, descrição, condomínio

### 🟡 TIER 3 — Mais complexo (Sprint 2-3)

#### 📦 OLX → Next.js __NEXT_DATA__
- Dados em JSON embutido no HTML via `document.getElementById('__NEXT_DATA__')`
- 57 ads por página
- Campos: subject, price, priceValue, location, properties (area, rooms, IPTU, condominio)
- URL de Marília redireciona para SP geral — precisa investigar URL correta
- Seletor: `a.olx-adcard__link`

---

## O QUE APRENDEMOS NO RECONHECIMENTO

### Surpresas positivas:
1. **União usa plataforma DreamKeys com API 100% aberta** — zero auth, JSON rico
2. **Toca usa Supabase** (mesma tech que a gente!) — API REST aberta com anon key
3. **VivaReal renderiza tudo no servidor** — dados completos no HTML, sem precisar da glue-api

### Surpresas negativas:
1. **Toca tem Vercel Security** — bloqueia requests httpx (429), mas funciona no browser real
2. **União era "uniaoimoveismarilia.com.br" no nosso chute, mas o real é "imobiliariauniao.com.br"**
3. **A glue-api do VivaReal** exige headers complexos e tem parâmetros instáveis — não vale o esforço

### Decisão técnica:
- **APIs (União + Toca):** httpx direto, sem complicação
- **HTML (VivaReal, Chaves, Imovelweb):** httpx + BeautifulSoup (SSR, dados no HTML)
- **Se Cloudflare bloquear:** Playwright como fallback
- **GitHub Actions suporta Playwright** — instalar no workflow se necessário

---

## SCHEMA DO BANCO (Supabase)

### Tabelas planejadas:
- **raw_listings** — dados brutos (source, source_id, raw_data jsonb, scraped_at, processed bool)
- **listings** — dados normalizados (tipo, preço, área, bairro, lat/lng, embedding vector, confidence_score, is_valid, etc.)
- **neighborhoods** — bairros com dados agregados (avg_price_m2, trend, infrastructure_score)
- **market_snapshots** — série temporal (snapshot_date, median_price_m2, count_listings)
- **opportunities** — terrenos pontuados (score, alert_level, llm_analysis, user_status)
- **viability_studies** — estudos de viabilidade (scenarios jsonb, recommended_scenario)
- **agent_runs** — log de execução (agent, status, started_at, items_processed, errors)
- **mcmv_rules** — regras MCMV (max_price, max_income, min_area, interest_rate)
- **price_history** — tracking de preço (listing_id, price, recorded_at)
- **listing_matches** — deduplicação cross-portal (listing_a, listing_b, match_score, match_method)

### Extensões:
```sql
CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fuzzy matching
```

---

## VARIÁVEIS DE AMBIENTE

```env
# Supabase (projeto MaríliaBot)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJ...  # service_role key

# Toca Imóveis (Supabase deles)
TOCA_SUPABASE_URL=https://jveljofutivtmufzmiej.supabase.co
TOCA_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2ZWxqb2Z1dGl2dG11ZnptaWVqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY3NDA0NzYsImV4cCI6MjA3MjMxNjQ3Nn0.Jl4X9G3Uy-4FrBRiQdVZ7Zvv0tHsg4VEq1mou1yofK0

# União (DreamKeys — sem auth)
UNIAO_API_URL=https://api.dreamkeys.com.br/public/properties

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Telegram Bot
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789
```

---

## PLANO DE SPRINTS

### Sprint 1 — Semana 1-2: Fundação + APIs
- [ ] Setup repositório, Docker, .env
- [ ] Schema SQL completo no Supabase (todas as tabelas + extensões)
- [ ] Coletor União (API DreamKeys) — httpx GET, paginação, todos os tipos
- [ ] Coletor Toca (API Supabase) — httpx GET com anon key, todos os tipos
- [ ] Pipeline de normalização com Claude Haiku
- [ ] Deduplicação básica (hash de endereço + preço + área)
- [ ] GitHub Actions workflow: collect → normalize
- [ ] Telegram Bot: setup básico pra alertas

### Sprint 2 — Semana 3-4: HTML Scrapers + Análise
- [ ] Spider VivaReal (HTML SSR, 30/página, `?pagina=N`)
- [ ] Spider Chaves na Mão (HTML SSR, `?pg=N`)
- [ ] Spider Imovelweb (HTML SSR)
- [ ] Validador: deduplicação cross-portal (fuzzy + embedding)
- [ ] Validador: tracking de anúncios que somem (proxy de venda)
- [ ] Analista: métricas por bairro + snapshots
- [ ] Dashboard Next.js: mapa + ranking + métricas
- [ ] Relatório semanal automático

### Sprint 3 — Semana 5-6: Caçador + Enriquecimento
- [ ] Caçador: scoring v2 (10 critérios)
- [ ] Enriquecedor: Google Maps (geocoding + POIs)
- [ ] Enriquecedor: IBGE (renda, demografia)
- [ ] Enriquecedor: Regras MCMV da Caixa
- [ ] Alertas Telegram com ficha do terreno
- [ ] price_history: tracking de mudanças

### Sprint 4 — Semana 7-8: Viabilidade + Refinamento
- [ ] Viabilidade: SINAPI + simulador de cenários
- [ ] Viabilidade: relatório PDF
- [ ] OLX spider (__NEXT_DATA__)
- [ ] Monitoramento: alertas quando pipeline falha
- [ ] Documentação

---

## ESTRUTURA DE PASTAS (planejada)

```
marilia-bot/
├── .github/workflows/
│   ├── collect.yml
│   ├── analyze.yml
│   └── scout.yml
├── src/
│   ├── agents/
│   │   ├── base.py
│   │   ├── collector/
│   │   │   ├── agent.py
│   │   │   ├── spiders/
│   │   │   │   ├── base.py
│   │   │   │   ├── uniao_dreamkeys.py
│   │   │   │   ├── toca_supabase.py
│   │   │   │   ├── vivareal.py
│   │   │   │   ├── chavesnamao.py
│   │   │   │   └── imovelweb.py
│   │   │   └── normalizer.py
│   │   ├── analyst/
│   │   ├── scout/
│   │   └── viability/
│   ├── db/
│   │   ├── client.py
│   │   ├── models.py
│   │   └── migrations/001_initial.sql
│   ├── llm/
│   │   ├── client.py
│   │   └── prompts/
│   ├── config.py
│   └── utils.py
├── dashboard/          # Next.js
├── scripts/
│   ├── run_collector.py
│   ├── run_analyst.py
│   └── run_scout.py
├── data/sinapi/
├── requirements.txt
├── .env.example
└── README.md
```

---

## NOTAS TÉCNICAS IMPORTANTES

1. **União API** — completamente aberta, zero rate limit detectado. Testar com `?type=land&business=SALE`.
2. **Toca API** — precisa dos headers `apikey` + `Authorization: Bearer`. Sem eles retorna 401.
3. **Toca usa Supabase** — mesma tech do projeto. A view `properties_public` já tem todos os campos necessários.
4. **VivaReal** — renderiza tudo no servidor. Sem API client-side. Dados no HTML via links `a[href*="/imovel/"]` e JSON-LD. A glue-api existe mas é instável e não vale o esforço.
5. **VivaReal e ZAP** são o mesmo grupo (OLX Group) — scraping de um cobre o outro.
6. **Chaves na Mão** — Cloudflare presente mas em modo observação. Se bloquear, usar delays maiores ou Playwright.
7. **Toca tem Vercel Security** — bloqueia httpx (429), mas a API Supabase funciona direto (não passa pelo Vercel).
8. **Imóveis MCMV:** União tem flag `isAvailableForMCMV`; Toca não tem mas infere por preço/tipo.
9. **Filosofia de dev:** Simples mas preparado pra escalar. Python puro sem framework de agentes. Cada agente é uma classe independente.
10. **100% automatizado** — sem dependência de input manual de corretores.

---

## ARQUIVOS GERADOS NESTE CHAT

1. **diagnostico-construtora.docx** — Diagnóstico estratégico com 6 problemas e soluções
2. **arquitetura-sistema.jsx** — Arquitetura v1 interativa (4 agentes, stack, sprints)
3. **blueprint-mariliabot.jsx** — Blueprint técnico (estrutura, schema, código dos agentes, GitHub Actions)
4. **arquitetura-v2.jsx** — Arquitetura v2 redesenhada (7 agentes, validação, enriquecimento)
5. **analise-sites-scraping.jsx** — Análise dos 7 sites com estratégias
6. **recon_sites.py** — Script de reconhecimento automático v1
7. **deep_recon.py** — Script de reconhecimento profundo v2 (com Playwright)
8. **recon-analysis.jsx** — Análise dos resultados do recon
9. **MARILIABOT_REFERENCE.md** — Referência técnica das APIs e dados

---

## COMO COMEÇAR NO CLAUDE CODE

Coloque este arquivo na raiz do projeto e peça:

> "Leia o MARILIABOT_CHAT_SYNTHESIS.md. Estou construindo o MaríliaBot. Comece pelo Sprint 1:
> 1. Schema SQL completo pro Supabase (todas as tabelas, índices, extensões)
> 2. Coletor da API DreamKeys (União Imobiliária) — httpx, paginação, salvar no Supabase
> 3. Coletor da API Supabase (Toca Imóveis) — httpx com anon key, salvar no Supabase
> 4. Normalização básica (padronizar campos entre as duas fontes)
> Python puro, sem framework de agentes, seguir a estrutura de pastas do documento."

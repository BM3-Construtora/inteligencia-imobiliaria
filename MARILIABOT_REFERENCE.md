# MaríliaBot — Referência Técnica Completa
## Documento para usar no Claude Code

---

## 1. VISÃO GERAL

Sistema de inteligência imobiliária para Marília-SP. Coleta dados de 6 portais, normaliza, valida, analisa e identifica oportunidades de terrenos para construtora familiar.

**Stack:** Python 3.12+ | Supabase (PostgreSQL + pgvector) | Next.js (dashboard) | Claude API (Haiku + Sonnet) | GitHub Actions (automação)

**Objetivo Sprint 1:** Coletar dados das 2 APIs abertas (União + Toca) + 3 sites HTML (Chaves na Mão, Imovelweb, VivaReal), armazenar no Supabase, e ter um dashboard básico.

---

## 2. FONTES DE DADOS — APIs ABERTAS

### 2.1 União Imobiliária (DreamKeys API)

- **URL base:** `https://api.dreamkeys.com.br/public/properties`
- **Auth:** Nenhuma (API pública)
- **Total:** 2.643 imóveis à venda em Marília
- **Terrenos:** 440 (type=land)

**Endpoints testados e confirmados:**

```
# Todos os imóveis à venda em Marília (paginado)
GET https://api.dreamkeys.com.br/public/properties?city=Marília&page=1&limit=50&business=SALE

# Filtrar por tipo
GET https://api.dreamkeys.com.br/public/properties?city=Marília&page=1&limit=50&business=SALE&type=land
GET https://api.dreamkeys.com.br/public/properties?city=Marília&page=1&limit=50&business=SALE&type=house
GET https://api.dreamkeys.com.br/public/properties?city=Marília&page=1&limit=50&business=SALE&type=apartment
GET https://api.dreamkeys.com.br/public/properties?city=Marília&page=1&limit=50&business=SALE&type=commercial
```

**Tipos válidos (enum):** `apartment` (636), `house` (1.313), `land` (440), `commercial` (193), `rural`

**Resposta JSON (campos por imóvel):**
```json
{
  "id": "uuid",
  "code": "29262",
  "title": "Apartamento em Ticiana Residencial Fragata - Marília",
  "description": "texto completo...",
  "type": "apartment | house | land | commercial | rural",
  "status": "available",
  "address": "Rua Hidekichi Nomura, 95",
  "street": "Rua Hidekichi Nomura",
  "number": "S/N",
  "complement": "",
  "city": "Marília",
  "state": "SP",
  "zipCode": "17519-221",
  "neighborhood": "Fragata",
  "latitude": "-22.22718701",
  "longitude": "-49.93398995",
  "totalArea": "62.00",
  "builtArea": "62.00",
  "bedrooms": 2,
  "bathrooms": 1,
  "parkingSpaces": 1,
  "salePrice": "300000.00",
  "rentPrice": null,
  "condominiumFee": null,
  "iptu": null,
  "features": [],
  "isActive": true,
  "isFeatured": false,
  "isAvailableForSite": true,
  "isAvailableForMCMV": false,  // ← FLAG MCMV!
  "companyId": "uuid",
  "responsibleUserId": "uuid",
  "createdAt": "2026-03-24T21:05:03.008Z",
  "updatedAt": "2026-03-24T21:05:03.008Z",
  "company": { "name": "União Imobiliária", "phone": "(14) 3402-6200", "email": "..." },
  "responsibleUser": { "name": "Brendon", "email": "..." },
  "imageCount": 6,
  "images": [{ "id": "uuid", "url": "https://lh3.googleusercontent.com/...", "category": "general" }],
  "mainImage": { "url": "..." }
}
```

**Paginação:** `page=1&limit=50` → resposta inclui `total`, `page`, `limit`, `totalPages`

---

### 2.2 Toca Imóveis (Supabase REST API)

- **URL base:** `https://jveljofutivtmufzmiej.supabase.co/rest/v1/`
- **Anon Key:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2ZWxqb2Z1dGl2dG11ZnptaWVqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY3NDA0NzYsImV4cCI6MjA3MjMxNjQ3Nn0.Jl4X9G3Uy-4FrBRiQdVZ7Zvv0tHsg4VEq1mou1yofK0`
- **Total:** 4.500+ imóveis à venda
- **Terrenos:** 88 (tipo_imovel = "Área")

**Headers obrigatórios:**
```python
headers = {
    "apikey": TOCA_ANON_KEY,
    "Authorization": f"Bearer {TOCA_ANON_KEY}",
}
```

**Endpoints testados e confirmados:**

```
# Todos os imóveis à venda (com fotos válidas)
GET /rest/v1/properties_public?select=id,titulo,tipo_imovel,cidade,bairro_nome,endereco,nome_edificio,valor,valor_aluguel,dormitorios,banheiros,suites,a_construida,a_terreno,garagem,descricao,foto_thumb,imovel_fotos,lati,longi,flag_mostra_site_ven,flag_mostra_site_loc,destaque,destaque_locacao,destaque_venda,exclusividade_locacao,exclusividade_vendas,aluga_rapido,caracteristicas,zona_nome,pontos_referencia&has_valid_photos=eq.true&flag_mostra_site_ven=eq.1&valor=gt.0&order=updated_at.desc

# Filtrar por tipo (terrenos)
&tipo_imovel=eq.Área

# Filtros disponíveis (bairros, tipos, etc)
POST /rest/v1/rpc/get_filter_options
Body: {}

# Configurações de filtro
GET /rest/v1/filter_configs?select=*&enabled=eq.true&order=name.asc
```

**Tipos válidos (campo tipo_imovel):**
- `Apartamento` (1.174 venda)
- `Casa` (2.162 venda)
- `Área` (88 venda) ← TERRENOS
- `Casa Em Condomínio` (562 venda)
- `Chácara` (+ outros)

**Campos disponíveis na view properties_public:**
- `id`, `titulo`, `tipo_imovel`, `cidade`, `bairro_nome`, `endereco`
- `nome_edificio`, `valor`, `valor_aluguel`, `dormitorios`, `banheiros`, `suites`
- `a_construida`, `a_terreno`, `garagem`, `descricao`
- `foto_thumb`, `imovel_fotos`, `lati`, `longi`
- `flag_mostra_site_ven`, `flag_mostra_site_loc`
- `destaque`, `destaque_locacao`, `destaque_venda`
- `exclusividade_locacao`, `exclusividade_vendas`, `aluga_rapido`
- `caracteristicas`, `zona_nome`, `pontos_referencia`

**Filtros via RPC (get_filter_options):**
- `filter_type: "bairro"` → lista de bairros com count_venda/count_locacao
- `filter_type: "tipo"` → tipos de imóvel com contagem
- `filter_type: "edificio"` → edifícios
- `filter_type: "quarto"` → quartos
- `filter_type: "regiao"` → regiões (zonas)
- `filter_type: "caracteristica"` → características

**Imagens:** `https://jveljofutivtmufzmiej.supabase.co/storage/v1/object/public/imoveis/{id}/capa.webp`

---

## 3. FONTES DE DADOS — HTML (SSR / BeautifulSoup)

### 3.1 VivaReal

- **Total:** 13.613 imóveis à venda em Marília
- **30 listings por página**, dados no HTML renderizado
- **Paginação:** `?pagina=2`, `?pagina=3`...

**URLs:**
```
# Todos os imóveis à venda
https://www.vivareal.com.br/venda/sp/marilia/
https://www.vivareal.com.br/venda/sp/marilia/?pagina=2

# Nota: URL de terrenos (/terrenos-lotes/) retorna 404
# Filtrar terrenos no parsing ou via sidebar do site
```

**Estratégia de coleta:**
- httpx GET com headers de browser → BeautifulSoup parse
- Cloudflare presente mas em modo observação (não bloqueou no recon)
- Se bloquear: Playwright como fallback

**Dados no HTML (por listing):**
- Links: `a[href*="/imovel/"]` → 29 por página
- Preço: regex `R\$\s*([\d.,]+)` no texto do card
- Área: regex `(\d+)\s*m²`
- Quartos/banheiros/vagas: no texto
- Bairro + rua: no texto do card
- IPTU: quando disponível
- JSON-LD: `ItemList` (30 items) + `RealEstateListing`

**URL dos listings contém dados estruturados:**
```
/imovel/casa-2-quartos-jardim-domingos-de-leo-marilia-100m2-venda-RS250000-id-2873227806/
         ^^^^  ^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^  ^^^^  ^^^^^^^^  ^^^^^^^^^^
         tipo  quartos  bairro                    cidade  area  preço    id
```

### 3.2 Chaves na Mão

- **Total:** 12.561 imóveis à venda em Marília
- **Server-rendered**, sem API, HTML puro
- **Paginação:** `?pg=2`, `?pg=3`...

**URLs:**
```
# Por tipo
https://www.chavesnamao.com.br/terrenos-a-venda/sp-marilia/
https://www.chavesnamao.com.br/casas-a-venda/sp-marilia/
https://www.chavesnamao.com.br/apartamentos-a-venda/sp-marilia/
https://www.chavesnamao.com.br/imoveis-a-venda/sp-marilia/

# Com paginação
https://www.chavesnamao.com.br/terrenos-a-venda/sp-marilia/?pg=2

# Terrenos em condomínio
https://www.chavesnamao.com.br/terrenos-em-condominio-a-venda/sp-marilia/
```

**Dados no HTML (por listing):**
- Links de listing com título descritivo
- Exemplo: `Terreno à venda na Rua Santa Helena, 09, Jardim Alvorada, Marília`
- Preço, área, quartos no texto do card
- Cloudflare presente mas não bloqueou (status 200)

### 3.3 Imovelweb

- **Terrenos:** 532 à venda em Marília
- **Server-rendered**, sem API

**URLs:**
```
https://www.imovelweb.com.br/terrenos-venda-marilia-sp.html
https://www.imovelweb.com.br/casas-venda-marilia-sp.html
# Paginação: provavelmente -pagina-2.html
```

**Dados por listing:** preço, área total, bairro, descrição, condomínio, fotos

---

## 4. FONTES DE DADOS — TIER 3 (Sprint 2-3)

### 4.1 OLX
- Next.js SSR com dados em `__NEXT_DATA__`
- 57 ads por página no JSON embutido
- Campos: subject, price, priceValue, location, properties (area, rooms, IPTU, condominio)
- URL de Marília redireciona para SP geral — precisa descobrir URL correta
- Seletor de cards: `a.olx-adcard__link`

### 4.2 VivaReal glue-api (alternativa — não implementar agora)
- `https://glue-api.vivareal.com/v2/listings`
- Precisa header `x-domain: www.vivareal.com.br`
- Retorna JSON mas parâmetros de busca são complexos e mudam
- O HTML SSR é mais confiável

---

## 5. ARQUITETURA

### 5.1 Agentes (7 total)

1. **Scraper** — Coleta bruta (API calls + HTML fetch)
2. **Normalizador** — Padroniza dados com Claude Haiku
3. **Validador** — Deduplicação, outliers, confidence score
4. **Enriquecedor** — Google Maps, IBGE, SINAPI, MCMV rules
5. **Analista** — Métricas de mercado, tendências, relatórios
6. **Caçador** — Scoring de oportunidades, alertas Telegram
7. **Viabilidade** — Simulação de cenários (sob demanda)

### 5.2 Pipeline diário
```
Fase 1: Scraper (todos os spiders em paralelo) → raw_listings
Fase 2: Normalizador (Claude Haiku) → listings
Fase 3: Validador + Enriquecedor (paralelo) → listings validados
Fase 4: Analista → market_snapshots + relatórios
Fase 5: Caçador → opportunities + alertas Telegram
```

### 5.3 Prioridade de implementação
1. **Sprint 1 (sem 1-2):** APIs (União + Toca) + schema Supabase + Normalizador
2. **Sprint 2 (sem 3-4):** HTML scrapers (Chaves + Imovelweb + VivaReal) + Analista + Dashboard
3. **Sprint 3 (sem 5-6):** Caçador + Validador + Enriquecedor
4. **Sprint 4 (sem 7-8):** Viabilidade + OLX + refinamentos

---

## 6. SCHEMA DO BANCO (Supabase)

### Tabelas principais:
- `raw_listings` — dados brutos antes de normalizar
- `listings` — dados normalizados (tabela principal)
- `neighborhoods` — bairros com dados agregados
- `market_snapshots` — série temporal de métricas
- `opportunities` — terrenos pontuados pelo Caçador
- `viability_studies` — estudos de viabilidade
- `agent_runs` — log de execução dos agentes
- `mcmv_rules` — regras MCMV da Caixa
- `price_history` — tracking de mudanças de preço
- `listing_matches` — deduplicação cross-portal

### Extensões necessárias:
```sql
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector para embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- fuzzy matching para deduplicação
```

---

## 7. CONFIGURAÇÃO

### Variáveis de ambiente:
```env
# Supabase (seu projeto)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJ...  # service_role key

# Toca Imóveis (Supabase deles — anon key)
TOCA_SUPABASE_URL=https://jveljofutivtmufzmiej.supabase.co
TOCA_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2ZWxqb2Z1dGl2dG11ZnptaWVqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY3NDA0NzYsImV4cCI6MjA3MjMxNjQ3Nn0.Jl4X9G3Uy-4FrBRiQdVZ7Zvv0tHsg4VEq1mou1yofK0

# União (DreamKeys — sem auth)
UNIAO_API_URL=https://api.dreamkeys.com.br/public/properties

# Anthropic (Claude API)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram Bot (alertas)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789

# Config
MAX_PAGES_PER_SPIDER=20
SCORING_MIN_AREA=200
SCORING_MAX_PRICE=300000
```

### Deploy: GitHub Actions
- 3 workflows encadeados via `workflow_run`
- Free tier: 2.000 min/mês (usa ~1.200)
- Secrets: todas as env vars acima

---

## 8. NOTAS IMPORTANTES

1. **União API** é completamente aberta — zero auth, zero rate limit detectado
2. **Toca API** precisa da anon key no header — sem ela retorna 401
3. **VivaReal** renderiza tudo no servidor — sem API client-side, dados no HTML
4. **Chaves na Mão** tem Cloudflare mas não bloqueia (status 200 no recon)
5. **A Toca usa Supabase** — mesma tech que vocês! Pode inspirar o schema
6. **VivaReal e ZAP** são o mesmo grupo (OLX Group) — mesma base de dados
7. **Imóveis MCMV**: União tem flag `isAvailableForMCMV`; Toca não tem flag mas pode ser inferido por preço/tipo

# Architecture Roadmap — Data Brain Híbrido

> Análise estratégica do sistema de inteligência imobiliária. Gerado em 2026-05-12.

---

## O que o projeto já faz bem

- Coleta múltiplas fontes imobiliárias
- Normaliza, classifica, deduplica, enriquece
- Calcula tendências, risco, viabilidade, comparáveis, preço estimado
- Dashboard React/Vite + Telegram Bot
- Módulos: coletores, normalizador, deduplicador, hunter, risk, viability, price model, feedback loop, materiais, regulatory, vision, ITBI
- Stack: Python 3.12, Supabase, Gemini, BeautifulSoup, httpx, cloudscraper, rapidfuzz, scikit-learn, LightGBM/SHAP/Playwright

---

## Diagnóstico Principal

Sistema hoje: **pipeline diário + rankings**. Para virar "cérebro", precisa de 4 camadas:

| Camada | Objetivo | Tech |
|--------|----------|------|
| **Lake bruto** | guardar tudo como veio, sem perder histórico | Supabase/Postgres ou S3/R2 |
| **Modelo canônico** | imóvel, anúncio, transação, bairro, vendedor, comprador, material, fornecedor | Postgres bem modelado |
| **Grafo de relações** | quem comprou de quem, flips, concentração por bairro | Neo4J ou Postgres + Apache AGE |
| **Reasoning/RAG** | responder perguntas, explicar decisões, consultar leis, PDFs, laudos | pgvector, Qdrant, LanceDB ou Supabase Vector |

> **Regra crítica:** RAG não decide preço, ROI, margem ou score numérico. RAG explica, recupera documentos, contextualiza. Decisão numérica = dados estruturados + modelos + regras auditáveis.

---

## Melhorias Concretas no Código

### `main.py` — God File

Migrar para:

```text
src/
  cli/
    app.py              # Typer ou Click
    commands/
      collect.py
      market.py
      materials.py
      deals.py
      intelligence.py
  pipelines/
    daily_market.py
    weekly_report.py
    materials_prices.py
    itbi_backfill.py
```

Médio prazo: **Prefect** ou **Dagster** — retry por etapa, observabilidade, cache, DAG visual.

### BaseCollector — separar coleta de persistência

```text
fetch_all() -> lista de itens brutos
extract()   -> transforma resposta da fonte em itens
persist()   -> grava raw/eventos
```

Adicionar ao `raw_listings`:

```sql
content_hash
first_collected_at
last_collected_at
run_id
unchanged_count
```

### Normalização — versionamento semântico

```sql
listing_versions
  listing_id
  version_hash
  normalized_payload
  changed_fields
  created_at
```

Responde:
- "Esse terreno baixou quanto desde que entrou?"
- "Quais anúncios mudaram preço depois de 60 dias?"
- "Esse imóvel saiu porque vendeu ou mudou de portal?"

### Hunter — score calibrado

Substituir score único por:

```text
opportunity_score      # quão interessante parece
confidence_score       # quão confiável é a informação
actionability_score    # quão acionável é agora
```

**Bug identificado:** `SOURCE_CONFIDENCE` não tem `zapimoveis` explícito — cai no default `0.70`, penalizando ZAP como baixa confiança se não intencional. Verificar e adicionar.

### Viabilidade — premissas versionadas

Mover hardcoded/env vars para tabela:

```sql
viability_assumptions
  id
  name
  valid_from
  scenario
  bdi_pct
  infra_pct
  admin_pct
  marketing_pct
  commission_pct
  working_capital_pct
  rework_pct
  sale_months
  source
```

**MCMV 2026:** Portaria nº 333/2026 — renda urbana até R$13k, limites por faixa atualizados (Faixas 1/2 até ~R$275k, Faixa 3 até R$400k, Classe Média até R$600k). Parametrizar por vigência e município.

---

## RAG — Como Implementar

### Índice de documentos

```sql
rag_documents
  source_type: plano_diretor | lei | edital | matrícula | contrato | laudo | conversa | anúncio | relatório
  source_id
  title
  text
  metadata
  embedding
  created_at
```

O que indexar:
- Plano Diretor de Marília
- Lei de uso e ocupação do solo
- Código de obras + PDFs de zoneamento
- Editais de leilão
- Certidões/matrículas
- Relatórios CRECI
- Documentos Caixa, MCMV, FGTS
- Histórico de decisões BM3: "compramos / não compramos / por quê"
- Conversas e anotações de visitas
- Fotos e laudos com descrição gerada por vision

### Perguntas que o brain deve responder

```
"Por que esse terreno recebeu score 82?"
"Quais riscos legais checar antes de fazer proposta?"
"Compare com negócios parecidos dos últimos 12 meses."
"Tem evidência de que esse bairro está aquecendo?"
"Esse vendedor já apareceu em outras transações?"
"Qual a proposta máxima para manter margem líquida de 18%?"
"Que materiais mais subiram nos últimos 90 dias e impactam esse tipo de obra?"
```

### Stack recomendada

1. **pgvector/Supabase Vector** — embeddings (já usa Supabase)
2. **LlamaIndex** ou **LangChain** — pipeline RAG
3. **Reranker** após busca vetorial
4. **Structured output** com JSON Schema/Pydantic
5. **Citations obrigatórias** — cada resposta aponta quais docs/dados usou

Evolução: se volume crescer → Qdrant ou Weaviate.

---

## Neo4J — Modelo de Grafo

### Nodes

```text
(:Pessoa {doc_hash})
(:Empresa {cnpj})
(:Imovel {matricula, endereco, geo})
(:Transacao {data, valor_declarado, valor_venal})
(:Anuncio {source, source_id})
(:Terreno)
(:Bairro)
(:ProjetoBM3)
(:Fornecedor)
(:MaterialSKU)
```

### Relações

```text
(:Pessoa)-[:COMPROU]->(:Transacao)
(:Pessoa)-[:VENDEU]->(:Transacao)
(:Transacao)-[:SOBRE]->(:Imovel)
(:Imovel)-[:LOCALIZADO_EM]->(:Bairro)
(:Anuncio)-[:ANUNCIA]->(:Imovel)
(:Empresa)-[:SOCIO_DE]->(:Pessoa)
(:ProjetoBM3)-[:USA_MATERIAL]->(:MaterialSKU)
(:Fornecedor)-[:VENDE]->(:MaterialSKU)
```

### Insights que o grafo desbloqueia

- Compradores recorrentes por bairro
- Vendedores com múltiplos imóveis
- Imóveis revendidos em curto prazo ("flippers" locais)
- Relação entre incorporadores, empresas e áreas
- Bairros com maior spread entre ITBI real e anúncio
- Terrenos com dono PJ com sinais de necessidade de liquidez
- Materiais cujo aumento afeta mais projetos MCMV

> Neo4J não substitui Postgres. É camada analítica relacional, alimentada a partir do Postgres.

---

## Dados para Coletar

### Terrenos

| Fonte | Prioridade | Observação |
|-------|------------|------------|
| **ITBI real** | Máxima | Transação real vs intenção de anúncio. Marília não publica feed estruturado — caminho: LAI ou convênio. Diretoria de Fiscalização de Rendas. |
| **Valor venal / cadastro imobiliário** | Alta | Portal do Cidadão oferece: certidão de cadastro, certidão de valor venal, pesquisa de débitos |
| **IPTU em atraso / dívida ativa** | Alta | Sinal forte de distress. Prioriza prospecção. |
| **Alvarás, habite-se, aprovações recentes** | Média | Mede onde estão construindo de verdade. |
| **Leilões Caixa e judiciais** | Média | Caixa: venda online, compra direta, leilão, licitação aberta. + TJSP + leiloeiros credenciados. |
| **Receita Federal / CNPJ / sócios** | Média | CNPJ Aberto: API REST com CNPJ, QSA, CNAEs, busca textual. |
| **Zoneamento, APP, declividade, hidrografia** | Média | `land_constraints_score` — terreno barato pode ser inviável. |
| **Distância a equipamentos urbanos** | Média | UBS, escolas, creches, transporte, polos de emprego. Crítico para MCMV. |
| **Imagens satélite / visão computacional** | Baixa | Evoluir `vision.py`: terreno limpo/ocupado, vegetação, desnível, rua asfaltada, padrão construtivo. |

### Materiais de Construção

Fontes online prioritárias:
- Leroy Merlin, Telhanorte, Cassol, Obramax, C&C, Joli, Sodimac
- Marketplaces (MercadoLivre, Amazon, Magalu) para SKUs padronizáveis
- Fornecedores locais de Marília: cadastro manual + cotação WhatsApp/PDF

**Métrica correta:**

```text
effective_delivered_price = preço produto + frete + prazo_impact_cost
```

Schema por SKU:

```sql
material_sku:
  categoria
  unidade_base
  fator_conversao
  peso
  volume
  marca_equivalente
  especificacao_tecnica
  uso_no_orcamento
```

SKUs críticos: cimento CPII 50kg, argamassa ACIII 20kg, bloco cerâmico, aço CA-50 10mm, areia m³, pedra m³, tubo PVC 100mm, fio 2.5mm, telha fibrocimento.

---

## Produtos a Desenvolver

### P1 — Motor de Proposta Máxima por Terreno

```
Entrada: terreno, área, bairro, preço pedido, tipo de projeto, margem mínima
Saída:   preço máximo de compra, proposta sugerida, margem esperada,
         sensibilidade por custo de obra, risco, justificativa
```

### P2 — Radar de Terrenos Subprecificados

Combinar: preço anúncio + preço/m² por bairro + ITBI real recente + tempo parado + distress + risco legal + viabilidade MCMV → top oportunidades da semana.

### P3 — Mapa de Liquidez por Bairro

Não só preço médio:
```
dias até sumir do portal
queda média de preço antes de venda
volume de ITBI
número de anúncios novos
absorção
margem MCMV simulada
```

### P4 — Sistema de Alerta Expressivo

```
"Avise quando aparecer terreno >250m² até R$280k em bairro com
 heat_score >70 e risco baixo"
```

### P5 — Benchmark Real de Obra

Cruzar: orçamento previsto × preço de material coletado × compras reais × prazo real × margem real → calibrar `viability.py`.

### P6 — CRM de Proprietários e Compradores

Após ITBI: quem vendeu, quem comprou, qual bairro, faixa de valor, frequência, empresas/sócios → prospecção.

---

## Roadmap

### Próximas 2 semanas

- [ ] Adicionar `zapimoveis` em `SOURCE_CONFIDENCE`
- [ ] Mover premissas do `viability.py` para tabela versionada
- [ ] Criar `listing_versions` e `content_hash`
- [ ] Criar issue/roadmap técnico para separar CLI de pipeline
- [ ] Criar tabela `data_source_health` (sucesso, falhas, tempo, itens, bloqueios)

### Próximos 30 dias

- [ ] RAG com pgvector: plano diretor, leis, MCMV, relatórios, docs internos, justificativas
- [ ] "Opportunity Dossier" por terreno: dados + comps + viabilidade + riscos + evidências + próximos passos
- [ ] `itbi_transactions` completo + fluxo de importação CSV/LAI
- [ ] Expandir materiais para 30–50 SKUs críticos

### Próximos 90 dias

- [ ] Neo4J: pessoas, empresas, imóveis, transações, anúncios
- [ ] Modelo de preço com LightGBM + SHAP usando ITBI como ground truth
- [ ] Feedback loop com projetos reais BM3
- [ ] Agente conversacional: "explique essa oportunidade", "monte uma proposta", "quais terrenos visitar amanhã?", "o que mudou no mercado esta semana?"

---

## Arquitetura Alvo

```
                 ┌─────────────────────────┐
                 │  Portais / ITBI / IPTU  │
                 │  Materiais / Leilões    │
                 │  Zoneamento / Satélite  │
                 └───────────┬─────────────┘
                             │
                      Collectors
                             │
                 ┌───────────▼─────────────┐
                 │ Bronze: raw_events       │
                 │ raw_listings, raw_docs   │
                 └───────────┬─────────────┘
                             │
              Normalize / Match / Dedup / Geocode
                             │
                 ┌───────────▼─────────────┐
                 │ Silver: modelo canônico  │
                 │ imóvel, anúncio, ITBI,   │
                 │ bairro, material, seller │
                 └───────┬─────────┬───────┘
                         │         │
              Analytics/ML       Graph
                         │         │
       ┌─────────────────▼───┐   ┌─▼──────────────┐
       │ Gold: opportunities │   │ Neo4J           │
       │ viability, scores   │   │ relações        │
       └──────────┬──────────┘   └─┬──────────────┘
                  │                │
                  └──────┬─────────┘
                         ▼
              RAG + Agentic Reasoning
                         │
              Dashboard / Telegram / CLI
```

---

## Priorização Final

1. **ITBI + dados reais de transação** — transforma "inteligência de anúncios" em "inteligência de mercado real"
2. **Viabilidade versionada e calibrada com obras reais** — gera decisão de compra
3. **Grafo Neo4J** — compradores/vendedores/imóveis/transações têm valor enorme quando conectados
4. **RAG** — camada de explicação, documentos, leis e copiloto (não motor de cálculo)
5. **Materiais com preço entregue em Marília** — fecha o ciclo: terreno → projeto → custo → margem → decisão

> Objetivo: cada recomendação deve ter dados, evidências, confiança, premissas, risco e ação sugerida — rastreável de ponta a ponta.

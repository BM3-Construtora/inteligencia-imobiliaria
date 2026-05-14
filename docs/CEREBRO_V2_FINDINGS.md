# Cérebro V2 — Findings, Decisões e Backlog

> Sessão de deep dive multi-agente + implementação paralela.
> Data: 2026-05-13
> Status: 4 streams implementados, 10+ itens de backlog mapeados.

---

## O que foi implementado nesta sessão

### Stream 1 — Camada Espacial (PostGIS + OSMnx)

| Arquivo | O que faz |
|---------|-----------|
| `sql/042_postgis.sql` | Ativa PostGIS, cria `pois`, `census_sectors`, `economic_centroids`, `listing_poi_proximity`, view `listings_with_geo` |
| `src/collectors/osm_collector.py` | Coleta 8 categorias de POI via Overpass API (hospital, escola, farmácia, supermercado, ponto de ônibus, parque, indústria, universidade) |
| `src/spatial.py` | Enrichment de proximidade + score MCMV + distâncias para 5 centroides econômicos |
| `src/marilia_neighborhoods.py` | Validação/normalização de nomes de bairros |

**5 centroides econômicos reais de Marília** (substituem o `distância_centro` único e incorreto):
- `commercial`: -22.2163, -49.9491 (centro comercial)
- `health`: -22.2089, -49.9433 (polo saúde - HB/FAMEMA)
- `education`: -22.2237, -49.9601 (polo educação - UNESP/UNIMAR)
- `industrial`: -22.1978, -49.9752 (distrito industrial)
- `historic`: -22.2141, -49.9466 (praça central)

**Score MCMV** (baseado nos critérios reais da Caixa):
- Escola ≤1500m → 30%
- Ponto de ônibus ≤800m → 25%
- Hospital ≤5km → 20%
- Supermercado ≤2km → 15%
- Parque ≤1km → 10%

---

### Stream 2 — LGPD + Vertex AI

| Arquivo | O que faz |
|---------|-----------|
| `src/llm.py` | Dual-mode: Vertex AI (com DPA) via `VERTEX_PROJECT` env, fallback AI Studio com warning |
| `sql/043_audit_log.sql` | `data_audit_log` + `audit_compliance_summary` view + `data_retention_policies` (15 políticas pré-populadas) |
| `src/audit.py` | `log_data_flow()` não-bloqueante via daemon thread; `audit_llm_call()` atalho para calls de LLM |

**Decisão LGPD crítica:** Google AI Studio **não tem DPA** — dados pessoais não podem ser processados lá. Vertex AI tem. Variável `VERTEX_PROJECT` no `.env` ativa o modo compliance.

---

### Stream 3 — Radar de Concorrência (DOM-MAR Seção III-A)

| Arquivo | O que faz |
|---------|-----------|
| `sql/044_alvaras_eiv.sql` | `alvaras_marilia`, `eiv_marilia`, view `radar_concorrencia` |
| `src/collectors/alvara_marilia.py` | Seção III-A do DOM-MAR: alvarás de aprovação 18-36 meses antes do habite-se |
| `src/collectors/eiv_marilia.py` | EIV (Estudo de Impacto de Vizinhança): empreendimentos >5000m², sinal premium |

**Por que é valioso:** alvará de aprovação aparece **18-36 meses** antes do lançamento. EIV aparece antes do alvará. É o sinal mais adiantado disponível publicamente.

---

### Stream 4 — IBGE Setores + Rating Construtoras

| Arquivo | O que faz |
|---------|-----------|
| `sql/045_ibge_sectors.sql` | Colunas socioeconômicas em `census_sectors`, função `enrich_listing_with_census()` |
| `sql/046_construtora_rating.sql` | `construtoras_rating` (scores 0-100), `construtoras_ativas`, `construtoras_por_bairro` |
| `src/collectors/ibge_sectors.py` | Download GeoJSON setores censitários (IBGE API) + opcional SIDRA renda |
| `src/rating_construtoras.py` | Rating A/B/C/D por dados públicos DOM-MAR exclusivamente |

**Fórmula de rating construtora** (só fontes públicas, sem depender de corretor):
- `score_entrega` = habite_se / alvarás ratio → peso 50%
- `score_prazo` = delta alvará→habite-se em dias (ótimo: 180d, ruim: 1095d) → peso 35%
- `score_volume` = log1p(alvarás) * 15 → peso 15%
- Tier: A (≥80), B (≥60), C (≥40), D (<40)

---

## Insights críticos do deep dive multi-agente

### Gaps que o sistema ainda não cobre

#### 🔴 Alta Prioridade

1. **Survivorship Bias no AVM** — LightGBM treinado em listagens que NÃO venderam = ground truth errado. Solução: usar resultados de leilões municipais + ITBI como preço real de transação para calibração.

2. **Plano Diretor 2026 (AGORA)** — Revisão acontecendo AGORA em Marília. Planurb identificou Jardim Bela Vista e Jardim América para upzoning. Monitorar CMDU e DOM-MAR para capturar mudanças de zoneamento antes de qualquer portal.

3. **Pipeline DOM → CMDU não existe** — As atas do Conselho Municipal de Desenvolvimento Urbano (CMDU) são publicadas no DOM mas não são coletadas. Contêm aprovações de EIV, discussões de zoneamento, decisões de loteamento — tudo com 6-12 meses de antecedência.

4. **pgvector não configurado** — `sql/021_remove_embeddings.sql` removeu embeddings mas não foi substituído por pgvector funcional. Sem isso, não há busca semântica por similaridade de imóvel.

5. **Novos coletores não integrados no pipeline** — `osm_collector`, `alvara_marilia`, `eiv_marilia`, `ibge_sectors`, `run_proximity_enrichment`, `run_rating_construtoras` precisam ser adicionados em `src/main.py` e no GitHub Actions `pipeline.yml`.

#### 🟡 Média Prioridade

6. **Termômetro do Agronegócio** — Marília tem ~30% das transações imobiliárias correlacionadas com a safra (CEPEA ESALQ-USP API). Feature de sazonalidade agrícola melhoraria AVM em 8-15% de R².

7. **Detector de Herança** — Cruzar obituários locais × listagens × inventários TJSP. Herança gera venda forçada com desconto de 15-25% em Marília.

8. **PPA 2026-2029** — Plano Plurianual municipal está sendo votado. Contém obras de infraestrutura (pavimentação, saneamento) que valorizam bairros. Fonte pública, ninguém monitora.

9. **Computer Vision para conservação** — Gemini já está disponível. Analisar fotos das listagens para extrair estado de conservação (score 0-10) e acabamentos sem dependência do corretor.

10. **MLS Cooperativo MVP** — Portal simples para corretores de Marília registrarem negócios (área, tipo, preço, bairro, data) em troca de acesso ao score de oportunidade. Resolve o problema de falta de dados de transação real.

#### 🟢 Longo Prazo

11. **Neo4j / GraphRAG** — Adiado. Usar recursive CTEs + pgvector em Supabase até queries precisarem de >4 hops consistentemente >500ms.

12. **Semáforo de Confiança AVM** — UI indicando quando o AVM tem baixa confiança (poucos comparáveis, bairro raro no dataset). Evita decisão errada com falsa precisão.

---

## Tecnologias validadas (deep dive)

| Tecnologia | Status | Aplicação |
|------------|--------|-----------|
| OSMnx + Overpass | ✅ Implementado | POIs, caminhabilidade, acessibilidade |
| PostGIS | ✅ Implementado | Geometrias, índices espaciais, ST_Within |
| IBGE API Malhas | ✅ Implementado | Setores censitários GeoJSON |
| DOM-MAR API JSON | ✅ Implementado | Habite-se, alvarás, EIV |
| Vertex AI (DPA) | ✅ Implementado | LGPD-compliant LLM |
| DataGEO SP | 🔲 Mapeado | Zoneamento oficial SP — requer download SHP/WFS |
| SIDRA IBGE | 🔲 Parcial | Renda domiciliar por setor — integrar em ibge_sectors.py |
| CEPEA ESALQ-USP | 🔲 Mapeado | Preços commodities → proxy safra → sazonalidade AVM |
| pgvector | 🔲 Pendente | Busca semântica, embeddings de imóvel |
| CMDU Atas | 🔲 Pendente | Decisões urbanísticas 6-12 meses antes de zoneamento |

---

## Backlog priorizado (próximas sessões)

### Imediato (bloqueia outras coisas)

- [ ] Integrar novos coletores em `src/main.py` e `pipeline.yml`
- [ ] Aplicar migrations SQL 042-046 no Supabase (dashboard ou CLI)
- [ ] Configurar `VERTEX_PROJECT` no `.env` e GitHub Secrets

### Alta prioridade

- [ ] `src/collectors/cmdu_atas.py` — coletar atas do CMDU via DOM-MAR
- [ ] `sql/047_pgvector.sql` — reativar embeddings com pgvector
- [ ] `src/avm_calibration.py` — calibrar AVM com ITBI como ground truth real
- [ ] `src/collectors/plano_diretor_monitor.py` — monitorar DOM para keywords de zoneamento/upzoning

### Média prioridade

- [ ] `src/collectors/agronegocio.py` — CEPEA ESALQ correlação safra
- [ ] `src/collectors/heritage_detector.py` — obituários × TJSP × listings
- [ ] `src/vision_conservation.py` — Gemini Vision score de conservação
- [ ] `src/telegram/handlers_callback.py` — exibir rating construtora no bot

### Longo prazo

- [ ] MLS Cooperativo — formulário web simples para corretores
- [ ] Semáforo de Confiança no AVM output
- [ ] DataGEO SP WFS — zoneamento oficial por polígono

---

## Decisões arquiteturais firmadas nesta sessão

1. **Não usar Neo4j agora** — recursive CTEs + pgvector em Supabase são suficientes até escalar
2. **Vertex AI obrigatório para dados com PII** — AI Studio não tem DPA = risco LGPD
3. **5 centroides econômicos** substituem distância única ao centro
4. **Rating por dados públicos exclusivamente** — sem depender de corretores/declarações
5. **EIV como sinal mais adiantado** — aparece antes do alvará, que aparece antes do habite-se
6. **DOM-MAR como hub de sinais** — habite-se + alvará + EIV + CMDU tudo na mesma API

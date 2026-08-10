# Product Roadmap — da inteligência à entrega

> Peer do `ARCHITECTURE_ROADMAP.md`. Aquele documento pergunta "o que coletar";
> este pergunta "o que já temos e ainda não chega ao usuário".
> Gerado em 2026-08-10, a partir de uma varredura multi-agente do código real
> (geoespacial, dashboard, bot Telegram, fluxo de dados, saúde de engenharia).

---

## Diagnóstico central

A camada de ingestão e inteligência correu meses à frente da camada de entrega.
Os números confirmam:

- O **bot** conecta ~5 de ~40 módulos de `src/` (`feedback_loop`, `db`, `viability`, `reporter`, `llm`).
- O **dashboard** consome ~13 de ~55 tabelas/views; puxa `listings` inteiro pro browser e agrega em JS.
- As **migrations 044-050 inteiras** (rating de construtora, radar EIV/alvará, pgvector/RAG, CMDU/plano diretor, CNPJ/agro, heritage/vision) são **100% órfãs**: coletadas, computadas, custando Gemini, sem um único consumidor.
- O **único mapa** mostra só bolhas por bairro. Toda a camada PostGIS (ponto por imóvel, POIs, setores censitários, polos econômicos, score de acessibilidade MCMV, APP) morre no banco.

**Conclusão:** o trabalho de maior alavancagem agora não é coletar mais dado, é
plugar o que já existe na tela e no bot. O custo caro (coleta + LLM) já foi pago;
falta a última milha barata.

> ## ✅ Schema V2 aplicado em produção (2026-08-10, resolvido)
> As migrations **042–050 + 052 estavam ausentes** do Supabase; foram
> aplicadas via `scripts/apply_v2_migrations.sql` após corrigir dois bugs
> latentes (`l.score` numa view de 042; `search_path` sem `extensions` nos
> RPCs de 052). Confirmado: as 14 tabelas/views V2 existem, `economic_centroids`
> já veio com 5 polos, e os RPCs do mapa resolvem. **Falta popular** o resto
> rodando os coletores (`municipal-data.yml`); as tabelas nascem vazias.
>
> **Efeito:** das features entregues, só têm dado vivo hoje `/subprecificados`
> (usa avm_predictions ✅) e os **pins do mapa** (usam opportunities ✅). As
> demais (`/construtora`, `/regras`, `/radar`, camadas Renda/Polos/Concorrência)
> retornam estado vazio até o schema ser aplicado — o código está correto e
> degrada com elegância, mas a tabela não existe.
>
> **Também explica** por que os coletores municipais (cmdu, alvara, agronegocio,
> heritage…) não populam nada: gravam em tabelas inexistentes. O `health-check`
> da fundação passa a flagrar isso.
>
> **Ação:** aplicar `scripts/apply_v2_migrations.sql` (bundle ordenado 042→052,
> idempotente) no SQL editor do Supabase, depois rodar os coletores
> (`municipal-data.yml`) para popular. Requer extensões `postgis` (042) e
> `vector` (047) habilitadas.

---

## Fundação — corrigir antes de qualquer produto novo

Não são features, são pré-condições. Construir tela/mapa em cima disso é construir sobre areia.

- [x] **Coletores falham em silêncio.** `agent_runs` é escrito por todos e lido por ninguém; scraper que retorna 0 itens conta como `completed`. Um portal pode ter quebrado hoje e o pipeline fica verde. → `src/health.py` + comando `health-check` + job final no `pipeline.yml` com alerta Telegram.
- [x] **JWT de terceiro hardcoded** em `config.py:18` (e `.env.example`). → default removido, guard tardio no coletor Toca, `.env.example` sanitizado. *Rotacionar o token da Toca continua pendente do lado humano.*
- [x] **Bug do `SOURCE_CONFIDENCE`**: `zapimoveis` caía no default 0.70 (`hunter.py`), penalizando a maior fonte de anúncios e contaminando o score que alimenta bot, dashboard e mapa. → adicionado `zapimoveis: 0.85`, removido `imovelweb` (aposentado).

---

## Onda 1 — Expor os órfãos de alto valor (backend pronto)

Ordenado por valor × esforço. Dado já computado em todos.

| # | Produto | O que liga | Onde | Esforço |
|---|---|---|---|---|
| 1 | Rating de construtora | `construtoras_rating` + CNPJ/sócios/risco (0 consumidores) | ✅ `/construtora <nome>` no bot + "quem constrói neste bairro" na ficha (feito). Falta: tela no dashboard | Baixo |
| 2 | Subprecificados + SHAP | `avm_predictions` (P10-P90, `mispricing_pct`, `is_undervalued`, `shap_summary` PT-BR) | ✅ `/subprecificados` no bot + drivers SHAP (`avm_explain.py`, antes órfão) na ficha (feito). Falta: tela "abaixo do valor" no dashboard | Baixo |
| 3 | Busca semântica / RAG regulatório | `search_documents` sobre CMDU, alvarás, EIV, plano diretor (indexado, sem chamador) | ✅ `/regras <pergunta>` no bot: retrieval pgvector + síntese com citações, degrada p/ retrieval-only sem LLM (feito). Falta: busca no dashboard | Médio |
| 4 | Radar de lançamentos futuros | `radar_concorrencia` (alvará 18-36 meses antes) + `radar_upzoning` | ✅ `/radar [bairro]` no bot: pipeline competitivo (alvarás/EIV) + sinais de upzoning (feito). Falta: tela + alerta no dashboard | Médio |

> **Onda 1 no bot: completa.** Os quatro órfãos de maior valor têm comando. O bot passou de ~5 para ~10 módulos de backend conectados. Falta a superfície de dashboard de cada um (Onda 1 lado web) e as Ondas 2-3.

---

## Onda 2 — O mapa como superfície unificadora

Hoje o mapa mostra bolha de bairro. A oportunidade é torná-lo o produto central,
empilhando camadas que já existem no PostGIS:

O `PropertyMap` agora tem uma barra de camadas toggleáveis:

- ✅ **Pins por imóvel** (incremento 1): oportunidades como pins coloridos por score (verde=bom), com sub-toggle de cor **score ↔ acessibilidade MCMV**; popup com preço/área/R$m²/link. Usa o conjunto de oportunidades (limitado) para não travar o Leaflet com ~20k listings.
- ✅ **Choropleth de renda** por setor censitário (`census_sectors`): camada "Renda" via RPC GeoJSON. Para MCMV, mapa de renda = mapa de demanda.
- ✅ **Acessibilidade MCMV**: sub-modo de cor dos pins (proximidade escola/ônibus/UBS = elegibilidade Caixa), lendo `mcmv_accessibility_score`.
- ✅ **Polos econômicos** com raio de influência (`economic_centroids`): camada "Polos".
- ✅ **Overlay de APP/cursos d'água** (`WATER_COURSES` espelhado em `dashboard/src/data/waterCourses.ts`): camada "APP", alerta de restrição construtiva.
- ✅ **Radar de concorrência** (camada "Concorrencia"): sinais de alvará/EIV agregados por bairro e plotados no centroide do bairro (v1 sem geocode fino — cruza `radar_concorrencia` com coords de `neighborhoods`).

**Pré-requisito técnico resolvido:** o front acessava Supabase direto sem RPC de geometria. Migration `sql/052_map_geojson.sql` adiciona `census_sectors_geojson()` e `economic_centroids_geojson()` (SECURITY DEFINER, GRANT anon). **Precisa ser aplicada no Supabase** para as camadas Renda/Polos carregarem.

Pendente na Onda 2 (evolução, não bloqueia): geocode fino de alvarás/EIV (hoje no centroide do bairro); `send_location`/static map no bot; POIs individuais no mapa.

> ## ⚠️ Achado de fonte (2026-08-10): alvarás de construção não estão no DOM-MAR dados-abertos
> Ao rodar `alvara_marilia` ponta a ponta pela 1ª vez: a API
> `dados-abertos/diario-oficial` **não publica registros estruturados de
> alvará de aprovação/construção**. Em 2024-2026, "alvará de aprovação/
> construção" = 0 ocorrências; "requerente" aparece só em contextos
> administrativos não-construtivos. Os 2 "alvarás" antes coletados eram
> falso-positivo em "Divisão de Aprovação de Projetos" (cabeçalho).
> **Impacto:** `/construtora` (rating depende de alvarás) e metade do
> `/radar` não têm fonte de dados — não é bug de parser. O sinal do moat
> ("alvará 18-36 meses antes") exige achar a fonte real (sistema de
> licenciamento municipal, SEPLAN, ou PDF do DOM não exposto neste JSON).
> Corrigido no coletor: parser de data (`YYYY-MM-DD HH:MM:SS`) e regex do
> bloco (não casa mais cabeçalho administrativo) → agora retorna 0 honesto
> em vez de linhas-lixo.

---

## Onda 3 — Produtos compostos

Quando os órfãos estiverem expostos, o salto seguinte é compor, não adicionar.

- **Opportunity Dossier por terreno** (P1 do `ARCHITECTURE_ROADMAP`, agora especificável): página que junta AVM+SHAP + viabilidade MCMV + rating de quem constrói ao lado + radar de upzoning do bairro + score de conservação por foto (`vision_conservation_score`) + flag de APP + flag de heritage. Tudo já existe solto; o produto é a composição rastreável.
- **Copiloto conversacional com tool-calling no bot**: hoje o chat é stateless e single-shot (`ai.py` monta prompt fixo por mensagem). Transformá-lo em agente que chama `ficha`, `construtora`, `search_documents` e mantém contexto muda o produto de "consulta" para "consultor". É o M15 (Chat RAG) do brain, viável sem Neo4j.
- **Sinal de timing de compra**: compor `agronegocio_index` + `safra_calendar` (sazonalidade agro, ~30% das transações) + `market_heat` + DOM num indicador "janela de compra/venda por bairro-mês". Nenhum concorrente (Urbit, DataZap) expõe isso, e casa com a tese hiperlocal.

---

## Corte transversal de engenharia (habilita escala, não urgente pra BM3)

- **Multi-cidade é aspiracional**: `CITY_FOCUS` definido e nunca consumido; ~63 arquivos com "Marília" hardcoded. Trava o Vetor 10 (replicação) do `VISION_OPPORTUNITIES`.
- **`main.py` é God File** (~650 linhas) com orquestração duplicada (YAML + Python que podem divergir). Separar CLI de pipeline antes de crescer.
- **Zero teste em CI**; nenhum teste cobre os scrapers (a parte mais frágil). Adicionar job pytest+ruff e fixtures de HTML dos portais é plug-and-play (a suíte roda offline).

---

## Sequência recomendada

1. **Fundação** (os 3 fixes acima). ✅ feito nesta rodada.
2. **Onda 1, itens 1 e 2** (rating + subprecificados): maior valor por menor esforço, backend 100% pronto.
3. **Pré-requisito da Onda 2** (RPC GeoJSON) + pins por imóvel + choropleth de renda.
4. Onda 3 quando o alicerce estiver de pé.

Fio condutor: **parar de coletar, começar a conectar.** O moat já está no banco; só não chegou na tela.

---

*Documento vivo. Revisar a cada rodada de produto.*

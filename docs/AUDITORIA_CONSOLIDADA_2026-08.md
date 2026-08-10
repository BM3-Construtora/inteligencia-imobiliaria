# Auditoria Consolidada — MaríliaBot / Cérebro BM3

> Consolidação de duas auditorias independentes do commit `1502f5e` (2026-08-10):
> **(A)** varredura interna em 3 frentes (entrega, análise, dados) com contagens reais do Supabase;
> **(B)** auditoria externa de arquitetura/segurança/metodologia.
> Onde as duas batem = alta confiança. Onde só uma viu = marcado. Onde os dados vivos mudam a conclusão = destacado.

---

## 0. Veredito conjunto

As duas auditorias chegam à mesma tese por caminhos diferentes:

> O sistema está **mais largo do que profundo**. O gargalo não é falta de feature; é **confiabilidade de dado, calibração financeira, segurança e o loop de decisão nunca ter fechado**. Adicionar coletor ou agente agora piora a relação sinal/ruído. Subir o patamar = religar, calibrar e fechar segurança do que já existe.

O que a auditoria externa não tinha e a interna trouxe: **as contagens reais do banco**. Elas transformam vários "risco teórico" em "está acontecendo" ou, ao contrário, em "ainda não dói porque a tabela está vazia". Isso muda a priorização.

---

## 1. Convergência — o que as duas auditorias acharam igual (confiança alta)

| # | Achado | Fonte código | Confirmação dados vivos |
|---|--------|--------------|-------------------------|
| C1 | **Coleta falha e o pipeline fica "verde".** `base.py:108` engole exceção do batch; `run()` marca `completed`; `main.py` também engole. Depois o normalizer desativa anúncios não vistos há 7 dias sem saber se a fonte veio completa. Risco: portal bloqueia → 0 itens → anúncios desativados → sistema lê como venda/absorção. | `base.py:43-45,108-110`; `normalizer.py:745-866`; `main.py:103-161` | `alvaras_marilia` e `habite_se_records` reportam `items_created>0` em `agent_runs` mas têm **0 linhas**. A falha silenciosa **já ocorre**. `imovelweb` 177 linhas, parado desde 11/05. |
| C2 | **AVM perde do baseline e mesmo assim mexe no ranking.** `eval_avm_result.json`: MAE 125k (AVM) vs 116k (baseline), cobertura P25–P75 de 24,85%, ITBI utilizável 0. O Hunter dá até +20% via `mispricing_pct`. | `hunter.py:380-418`; `docs/eval_avm_result.json` | `avm_predictions` **congelado em 13/05** (346 linhas, 0 desde então). O modelo nem roda; o multiplicador usa predição velha. |
| C3 | **`/ficha` do Telegram nunca usa o AVM treinado.** Consulta colunas inexistentes (`neighborhood`, `n_comps`, `created_at`); exceção engolida; cai sempre no fallback de mediana de preço pedido. O "teto de oferta sugerido" sai de asking, não do modelo. | `telegram/avm.py:44-66`; migration `..._avm_predictions.sql` | Confirmado: schema real tem `p25/p50/p75/confidence/predicted_at`, não os campos consultados. |
| C4 | **Exposição indevida no Supabase (RLS).** A própria migration de hardening admite leitura pública de rankings/oportunidades/viabilidade/projetos/decisões. Pior: policies de `opportunity_decisions` **sem `TO service_role`** → INSERT/UPDATE públicos. | `..._rls_hardening.sql:11-16,53-60`; `..._decision_tracking.sql:27-33` | Dashboard usa **anon key no bundle**, sem auth. Subprecificados quebra porque `avm_predictions` tem RLS sem policy de SELECT. |
| C5 | **Viabilidade não está calibrada para decisão.** Unidades = área/lote mínimo (ignora testada, recuos, APP, topografia, desdobro); receita = 90% do teto do programa (constante por bairro); payback nunca falha por construção; sensibilidade perturba só SINAPI ±10%. Teste marcado `xfail` admitindo descalibração. | `viability.py:27-114,338-349,367-371,411-414,632-650`; `tests/test_viability.py:39-65` | `viability_studies` 453 linhas rodadas sobre essas hipóteses. `bm3_deals` = 0 → nunca foi calibrada com resultado real. |
| C6 | **`score_breakdown` sobrescrito a cada run** → skip-guards nunca disparam → ~50 chamadas Gemini refeitas todo dia sobre os mesmos imóveis, e `llm_justificativa`/`risk_assessment`/`comps` são apagados antes de chegar a qualquer tela. | `hunter.py:153-159`; `scorer_llm.py:48`; `risk_scorer.py:48` | `llm_usage` cresce diariamente sem necessidade. |
| C7 | **LLM/Vertex/LGPD é scaffolding.** `_generate` retorna `None` se não há `GEMINI_API_KEY`, **antes** de tentar Vertex → o caminho com DPA é código morto. Auditoria LGPD (`audit.py`) quase nunca é chamada. | `llm.py:63-64` | `data_audit_log` = **0 linhas**. |
| C8 | **Grafo: manter Postgres, não subir Neo4j agora.** Sem resolução de entidade confiável, grafo alimentado por vínculo incerto só torna o erro mais convincente. | decisão já registrada em `CEREBRO_V2_FINDINGS.md` | Ambas as auditorias concordam com a decisão existente. |

**Leitura:** C1 a C7 são todos bugs/riscos em código **já pago**, não features faltando. É o núcleo do trabalho.

---

## 2. O que cada auditoria viu sozinha

### 2.1 Só a auditoria externa levantou (novos, incorporar)

- **E1 — `raw_listings` não é histórico.** Upsert por `(source, source_id)` sobrescreve `raw_data`; guarda só a última versão. Impede reproduzir o que a fonte mostrava em cada data. **Confirmado no código** (`base.py:72-98`). Proposta: tabela append-only `listing_observations` (`run_id`, `observed_at`, hash do conteúdo, payload, url, versão do extrator); `raw_listings` vira projeção "latest".
- **E2 — "Sumiu do portal" ≠ venda.** Precisa de máquina de estados: `active | price_changed | withdrawn | expired | relisted | sold_confirmed | unknown`. Desaparecimento = evento **censurado/desconhecido** até confirmação. Viva/ZAP não são fontes independentes (mesmo grupo OLX) → não contam como dupla evidência de venda.
- **E3 — Hunter mistura eixos e estoura a escala.** Documentado 0–100, mas soma aditiva chega a 105 e multiplicador a 1,30 → teto real ~136,5. Pior: mistura atratividade econômica + qualidade de dado + confiança de fonte + completude numa nota só. Deveriam ser eixos separados. *(claim de escala reportado pela externa; plausível, vale confirmar somando os pesos em `hunter.py`.)*
- **E4 — Drift regulatório de versão.** Fallback do repo aponta LC 480/2006 e regras aproximadas da LC 753/2017; o município já está na **LC 973/2023**. Faixas MCMV devem seguir a **Portaria MCID 333/2026**, não constantes chumbadas. Regras precisam ser **versionadas por vigência** (`valid_from`/`valid_to`), não hardcoded.
- **E5 — Higiene de engenharia.** Ruff 643 diagnósticos (muitos `except` amplos), dashboard lint 17 erros, `npm audit` 7 vulnerabilidades (6 altas), bundle ~1,04 MB, CI só testa Python (sem build/lint de frontend). Ruff é informativo, não bloqueia.
- **E6 — Escada de fontes para substituir o ITBI** (ver §5). Mais estruturada que o mapa de tiers atual, com links oficiais (e-SIC, 1Doc, ONR, DataGeo/IDE-SP, CETESB áreas contaminadas, SINISA saneamento).
- **E7 — Formulação correta do output de viabilidade:** não `is_viable` booleano, e sim **"preço máximo pagável pelo terreno para atingir VPL/TIR/margem-alvo"**, com cenários e incerteza. Regra de compra: `pedido ≤ min(preço máx por VPL, comparável ajustado P25)` com prob. mínima de TIR e nenhum bloqueio legal.
- **E8 — Contaminação: CETESB áreas contaminadas** como filtro eliminatório (a interna não mapeou essa fonte). Terreno contaminado é veto, não desconto.

### 2.2 Só a auditoria interna levantou (novos, a externa não tinha os dados)

- **I1 — Planta Genérica de Valores do IPTU: 33.466 faces de quadra, 100% órfãs.** `iptu_planta_valores` tem `land_value_per_m2` oficial por logradouro, e nada consome. Join com `listings` dá piso legal de preço e "prêmio sobre valor venal" por bairro. É a maior tabela de referência do banco. *(ref 2013; serve como baseline relativo entre bairros.)*
- **I2 — Renda por setor censitário pronta e desligada.** `enrich_listing_with_census` existe (migration 048) e **nunca é chamada**; `listings.census_renda_pc` = 0 de 11.270 geocodificados. É o proxy de demanda MCMV mais forte disponível.
- **I3 — Receitas municipais: 27 mil linhas, 2021–2026, órfãs.** Arrecadação de ITBI mês a mês = índice de volume transacional real com **5 anos** de história, contra os 4,5 meses da série de portais. Substituiria o proxy ruim de "anúncio removido" no `market_heat`.
- **I4 — `sold_estimates` (1.330 linhas) nunca validam o AVM.** Join com `avm_predictions` responde hoje "o modelo bate a mediana?" com centenas de casos, sem esperar 8 `bm3_deals`. O drift report trava em "amostra insuficiente" (`MIN_CALIBRATION_SAMPLE=8`) por olhar só `bm3_deals`.
- **I5 — `market_heat` usa constante disfarçada.** `avg_risk_score` tem como único escritor uma função morta (`analyst._update_neighborhood`), então os 10 pts de "risco" do heat são **3.33 para todo bairro**. `market_heat.py:102`.
- **I6 — `listing_poi_proximity` cobre 4%.** Só 500 de 11.270 listings com `geom`, por um teto hardcoded em `spatial.py`. Os POIs (296) quase não influenciam o inventário.
- **I7 — Coletores que alimentam telas não estão agendados:** `sales`, `price-model`, `itbi`, `parcelamento`, `sinapi`, `ibge`, `creci`, `regulatory`, `enrich`, `drift-report`, `calibration`. Existem em `main.py`, fora do CI.
- **I8 — Dois registros de decisão desconectados.** Dashboard grava `opportunity_decisions`; calibração lê `bm3_deals`. Decisão feita na web não calibra nada. Ambas as tabelas = 0 linhas hoje.
- **I9 — `/relatorio` quebrado** (`_build_static_report` não existe; é `_build_report`) e `refresh_bairro_stats()` nunca é chamado (Painel do Bairro congelado).
- **I10 — `opp_votes`/`opp_messages` fora das migrations.** Usadas em produção (`handlers_callback.py`, `notifier.py`) mas não versionadas → drift schema↔migrations.
- **I11 — Dupla contagem no Hunter.** `price_m2` (20 pts, pune preço acima da média de pedidos) e `v2_avm_upside` medem o mesmo eixo, porque o alvo do AVM é o preço **pedido**. E `_get_market_context` não filtra canônico/quarentena → média contaminada. `hunter.py:315-339,398-474`.

---

## 3. Onde os dados vivos mudam a conclusão

A auditoria externa tratou alguns itens como risco de arquitetura. As contagens reais reclassificam:

1. **ITBI não é "fonte a integrar", é fonte com consumidor esperando vazio.** `price_model.py:260` já lê `itbi_transactions`; a tabela tem **0 linhas** e o coletor nunca rodou. E os IDs `itbi_...` são string mas o extrator tenta `int` → cai no fallback silencioso. Não é decisão de roadmap; é bug + coletor a disparar.
2. **O loop de decisão está literalmente vazio.** `bm3_deals` 0, `opportunity_decisions` 0, `recommendation_calibration` 0, enquanto `match_review_queue` tem 5.162 pares e `hunter_score_history` tem 687 snapshots. Nenhuma linha de decisão = impossível calcular precisão do Hunter ou treinar re-ranking. O ground truth interno (o item nº 1 da escada de fontes da auditoria externa) **não começou**.
3. **A profundidade temporal boa está desconectada.** Receitas (5 anos), licitações (desde 2002), obras (desde 2017), parcelamento (até 23/07) existem e são estáticas/órfãs. A série que decide (portais) tem 4,5 meses. O valor está em **ligar o histórico profundo à série curta**, não em coletar mais.
4. **Segurança é urgente agora, não depois.** Não é hipótese: anon key no bundle + `opportunity_decisions` com escrita pública + `avm_predictions` com RLS sem SELECT. Antes de qualquer deploy, isso vira porta aberta.

---

## 4. Plano consolidado priorizado

Fundido das duas ordens de execução, com o item de cada auditoria entre colchetes.

### P0 — Parar o dano (1–2 semanas)

Tudo aqui é bug/segurança em código existente. Nenhuma feature nova.

1. **Status de coleta honesto** [C1/E1]. Criar `source_runs` (esperado, recebido, persistido, cobertura vs mediana histórica, `is_complete`). `_flush_batch` deve relançar em falha total; `run()` só marca `completed` se persistiu. **Bloquear desativação de anúncio quando a fonte veio incompleta.** Corrigir a contagem `created` vs `updated` em `base.py:103`.
2. **Desligar o multiplicador AVM** [C2]. Peso zero no Hunter até o modelo bater um baseline ingênuo em validação **espacial e temporal**. AVM em shadow mode (prevê, não decide).
3. **Fechar RLS + auth** [C4]. `TO service_role` nas escritas de `opportunity_decisions`; policy de SELECT (ou RPC `SECURITY DEFINER`) para `avm_predictions`; deny-by-default nas tabelas estratégicas; tirar acesso direto do browser via anon key. Supabase Auth para o dashboard.
4. **Corrigir ou desativar o AVM do Telegram** [C3]. Consultar por `listing_id` com colunas reais; resolver a mistura preço total vs R$/m². Enquanto não, esconder o "veredito AVM" da ficha.
5. **Separar desaparecimento de venda** [E2]. Máquina de estados de listing; "sumiu" = `unknown`/censurado. Corrige a contaminação de liquidez/absorção que vem em cascata do C1.
6. **Corrigir o gasto de LLM à toa** [C6]. Parar de sobrescrever `score_breakdown` inteiro (preservar as chaves caras); os skip-guards voltam a funcionar.
7. **Corrigir Vertex/LGPD** [C7]. Guard de `_generate` deve considerar `USE_VERTEX`. Ligar `audit_llm_call` de fato. **Pausar heritage/obituário e litígio pessoal** até revisão formal de base legal LGPD (inferência de vulnerabilidade financeira a partir de PII).

### P1 — Fechar o loop de evidência (semanas 2–6)

Sem isso o sistema nunca aprende, é a diferença entre "dashboard bonito" e "cérebro".

8. **Observações imutáveis + `source_runs`** [E1] operacionais.
9. **Ligar o registro de decisão da BM3** [I8/ground truth E]. Unificar dashboard + bot + CLI em `bm3_deals`; botão "Registrar oferta" no teclado inline do Telegram. Meta: começar a acumular decisões reais **esta semana**.
10. **Agendar o que existe e não roda** [I7/I9]. `sales`, `price-model`, `itbi`, `parcelamento`, `sinapi`, `ibge`, `creci`, `regulatory`, `enrich`, `drift-report`, `refresh_bairro_stats()`. Corrigir `/relatorio`. Materializar `opp_votes`/`opp_messages` em migration [I10].
11. **Reescrever viabilidade para "preço máximo pagável"** [C5/E7]. Output = teto de oferta por VPL/TIR/margem com cenários e incerteza, não `is_viable`. Substituir unidades-por-área por restrição física/legal mínima. Sensibilidade sobre preço de venda e preço do terreno, não só SINAPI.
12. **Versionar regras por vigência** [E4]. LC 973/2023, Portaria MCID 333/2026, hipóteses financeiras. Nada de constante urbanística/MCMV chumbada em código.
13. **CI de frontend** [E5]. Build + lint do dashboard bloqueantes; tratar as 6 vulnerabilidades altas; reduzir os `except` amplos que o Ruff aponta.

### P2 — Extrair valor dos dados parados (semanas 6–12)

Aqui entram os cruzamentos novos. Todos usam dado já no banco, zero coletor novo, exceto onde marcado.

14. **Validar AVM contra `sold_estimates`** [I4]. Backtest imediato, responde a pergunta do TCC com centenas de casos.
15. **Piso oficial via Planta Genérica de Valores** [I1]. Feature "abaixo do valor venal" (agulha no palheiro) + "prêmio sobre venal por bairro". Precisa de normalizador de logradouro.
16. **Ativar renda por setor censitário** [I2] → demanda MCMV realizável por bairro; conserta a receita constante da viabilidade (C5).
17. **Termômetro fiscal de transações** [I3] → recalibra `market_heat` com dado fiscal (5 anos) em vez de heurística de remoção.
18. **Indicador forward-looking de oferta** [I via parcelamento]. `lotes_count` por bairro vs estoque atual = compressão de preço futura. Primeiro sinal que olha para frente.
19. **Score de investimento público por bairro** [I]. Obras (desde 2017) + licitações vs variação de ppm² em 24 meses. Estudo causal viável hoje; vira feature do AVM.
20. **Cap rate implícito por setor** [I]. Venda × aluguel na mesma tabela × `domicilios_alugados` do Censo. Sustenta a visão de carteira de aluguel da família.
21. **Distress × mercado** [I]. Join geo de `off_market_signals` × `listings`. Sinal de urgência de vendedor, hoje inerte.
22. **Corrigir a constante 3.33 de risco** [I5] e completar `listing_poi_proximity` para os 96% restantes [I6].
23. **Ground truth externo** [E6]: e-SIC/1Doc para microdados ITBI anonimizados por setor; parceria de corretores (feed cooperativo); ONR seletivo para due diligence. **CETESB áreas contaminadas** como veto [E8].
24. **Treinar AVM com validação espaço-temporal** [C2/E], só religar no ranking depois de superar o baseline. Medir `precision@10`: quantas oportunidades viram visita → proposta → aquisição.

---

## 5. Escada de fontes de preço real (fundida)

O ITBI direto falhou. Nenhuma fonte gratuita única entrega preço de escritura com cobertura. Montar uma escada de evidência, do mais confiável ao mais amplo:

1. **Ground truth interno BM3** (o mais valioso e o único 100% sob controle): terrenos analisados, visitas, propostas, recusas, aquisições, preço fechado, orçamento, resultado. **Está em 0 hoje. Começar já.** [E1/I8]
2. **ITBI municipal via e-SIC/1Doc**: microdados anonimizados por mês/setor/tipo/área/valor; se negado, agregações por setor censitário. [E6]
3. **Receitas municipais já coletadas**: arrecadação de ITBI como proxy de volume (não de preço unitário), 5 anos no banco. [I3]
4. **Parceria com corretores**: feed cooperativo de fechados (pedido vs negociado). [E6]
5. **Planta Genérica de Valores** já no banco: piso legal por logradouro. [I1]
6. **ONR/RI Digital** seletivo: due diligence e ground truth pontual, não coleta massiva. [E6]
7. **Geodados oficiais**: DataGeo/IDE-SP (zoneamento por polígono), CETESB (contaminação, veto), Censo/IBGE (setor, já no banco), SINISA (saneamento). [E6/I2]

Regra de compra consolidada:

> Comprar se `preço pedido ≤ min(preço máximo pagável por VPL/TIR-alvo, comparável ajustado P25)`, com probabilidade mínima de atingir a TIR, comparáveis escolhidos **sem** usar o preço do próprio terreno como critério de similaridade, e **nenhum bloqueio legal/ambiental grave** (zoneamento, APP, contaminação, desdobro).

O ranking deve mostrar em eixos separados, não numa nota só [E3]: VPL esperado · prob. de VPL positivo · perda no cenário ruim · confiança do dado · pendências de due diligence · urgência/negociabilidade.

---

## 6. Arquitetura-alvo (consenso)

| Camada | Conteúdo |
|--------|----------|
| Bronze | Observações imutáveis (`listing_observations`), documentos originais, `source_runs` |
| Silver | Imóvel/parcela canônica, anúncios associados, eventos, resolução de duplicata |
| Gold | Features versionadas por `as_of`, valuation, viabilidade, ranking, decisões |
| Vetorial | Só documentos: legislação, atas, explicações com citação (não listings) |
| Grafo | Tabelas de relação no Postgres; Neo4j só quando houver >4 hops consistentemente lentos |

Todo fato carrega: fonte, URL, data de observação, vigência (`valid_from`/`valid_to`), método de extração, confiança e versão. Manter PostgreSQL + PostGIS + pgvector. Não subir Neo4j antes de ter resolução de entidade confiável [C8].

---

## 7. Como medir que subiu de patamar

Nenhuma dessas métricas depende de coletor novo:

- **Confiabilidade:** 0 desativações de anúncio a partir de fonte incompleta (hoje: acontece).
- **Segurança:** 0 tabelas estratégicas com escrita/leitura pública (hoje: várias).
- **Loop:** ≥30 decisões reais em `bm3_deals` em 90 dias (hoje: 0).
- **AVM:** só volta ao ranking se `MAE_AVM < MAE_baseline` em validação out-of-time (hoje: perde).
- **Precisão de funil:** `precision@10` da lista de oportunidades → visita/proposta (hoje: incalculável, sem decisões).
- **Frescor:** `avm_predictions`, `sold_estimates`, rating de construtoras deixam de ficar congelados (hoje: parados desde maio).

---

*Documento vivo. Referência cruzada: `BRAIN_STRATEGY.md` (como construir), `VISION_OPPORTUNITIES.md` (o que fazer com o brain), `CEREBRO_V2_FINDINGS.md` (backlog V2), `project_audit_findings` (memória dos P0/P1).*

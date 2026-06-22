# Revisão Multi-Agente do TCC — Rodada 1
> Gerada pelo workflow `tcc-revisao` (6 agentes especializados). Texto-base: `docs/TCC_draft.md`.

---

# 0. SÍNTESE CONSOLIDADA (Orientador)

## Parecer do Orientador — Consolidação Final

### Veredito de prontidão: 🟡 em desenvolvimento (fechável até a entrega)

O trabalho ainda não está pronto, mas — confirmo após confrontar os cinco pareceres — a distância é de **forma acadêmica, não de substância**. O sistema é real, robusto e bate com o que o texto descreve (auditoria técnica confirmou ~95% das afirmações com `arquivo:linha`). O problema permanece o inverso do habitual: você tem mais sistema do que TCC. As cinco lentes convergem para o mesmo diagnóstico estrutural — falta Metodologia, faltam objetivos específicos, falta Resultados *medidos* — e divergem apenas em ênfase e em dois pontos de calibração de escopo que resolvo abaixo. Nenhum bloqueador exige escrever código novo obrigatório; todos exigem **transpor para o texto o que já existe no repositório**, com honestidade sobre os limites. Se os P0 forem fechados, o trabalho defende com mérito.

### Fio condutor (problema→objetivo→resultado)

- **Entrada coerente e forte** (consenso de todas as lentes): problema (incerteza na escolha de terreno MCMV, dados fragmentados, anúncio ≠ transação) → motivação (BM3, margens apertadas) → solução (MaríliaBot). Preservar.
- **Quebra no objetivo:** "desenvolver **e analisar**" sem critério nem baseline; sem objetivos específicos mensuráveis. A banca usa esse esqueleto para checar entrega — sua ausência é lacuna grave.
- **Quebra fatal no final:** seção 3 entrega "resultados **esperados**" para um sistema que roda há meses. O elo final existe no código (métricas, calibração BM3, feedback loop) e **não foi puxado para o texto**.

### Resolução dos conflitos entre pareceres

Antes do plano, fecho as três tensões reais entre as lentes, com critério acadêmico:

1. **Mercado quer mais (TAM/SAM/SOM, matriz, break-even); Redação/Orientador querem menos "plano de negócios".** Resolução: **ambos, mas subordinados.** A análise de mercado entra com profundidade de MBA (matriz de benchmarking, dimensionamento, break-even ilustrativo) — porém *dentro* de uma seção "Aplicação gerencial / proposta de valor" claramente **subordinada aos Resultados**, não como espinha dorsal. Critério: pesquisa aplicada de MBA admite análise de mercado robusta desde que o eixo do trabalho seja o artefato e sua avaliação, não o Canvas. Conflito dissolvido por hierarquia, não por exclusão.

2. **Validação prospectiva (Experimento B do metodólogo) × realidade de dados (banca: só 1 deal fechado, ITBI sem feed).** Resolução: o **Experimento A (backtest offline contra ITBI, com baseline de bairro) é o núcleo obrigatório e factível**; o **Experimento B (decisão apoiada vs. tradicional) entra em escala reduzida e honesta** — reprodução *ex-post* do caso Casa 1 (margem real 24%) + as duas casas paradas como contra-exemplo, explicitamente rotulado como evidência de caso, não de população. Não prometer validação prospectiva com n suficiente que não existe. A banca recompensa essa honestidade; pune a promessa vazia.

3. **Split temporal e leakage residual (`neigh_avg`): corrigir código antes da defesa ou apenas declarar?** Resolução: **declarar é obrigatório; corrigir é P1 desejável.** O metodólogo aponta a correção ideal; a banca confirma que, hoje, a resposta honesta é "split aleatório com leakage residual". Critério de prazo: se houver tempo, corrija (split temporal + `neigh_avg` só no treino) e reporte o número corrigido — vira força. Se não houver, **declare como limitação metodológica explícita** — vira rigor demonstrado. O que não pode é ficar silencioso e ser exposto na arguição.

### Lacunas estruturais bloqueadoras (consenso das 5 lentes)

1. **Ausência de Metodologia** — a banca classifica o trabalho pelo método; sem ela não há rigor avaliável.
2. **Ausência de pergunta de pesquisa + objetivos específicos** — esqueleto que a banca usa para checar cumprimento.
3. **Resultados reais inexistentes** — "esperados" não é resultado; sem números o mérito não existe.
4. **Conflito de interesse + N=1 não declarados** — objeção previsível, barata de fechar, cara de deixar aberta.
5. **LGPD/base legal ausente** (acréscimo da banca) — você raspa dado pessoal (IPTU devedor, inventários TJSP, diários); zero menção a base legal é flanco jurídico aberto.

### Pontos fortes a preservar (e promover ao texto)

- Introdução e formulação do problema (anúncio ≠ transação; "a viabilidade se decide antes da obra").
- Fundamentação madura que **bate com o código** (AVM quantílico, SHAP, SINAPI, VGV/TIR) — protege na arguição técnica.
- Posicionamento competitivo hiperlocal (lacuna que Urbit/DataZap não cobrem) — contribuição original genuína.
- **Subnotificados a trazer para o texto** (auditoria técnica): ITBI como ground truth com peso 2.0 (a contribuição metodológica que diferencia de um AVM ingênuo); TIR por Newton (implementação própria); 5 centroides econômicos georreferenciados; score MCMV Caixa; calibração com 3 projetos reais BM3; quantile crossing tratado; target-encoding sem leakage (feito corretamente).

---

### Plano de ação priorizado e consolidado

#### P0 — Bloqueadores (sem isto, não defende com mérito)

1. **[P0] Escrever a seção Metodologia.** Enquadramento: **Design Science Research (Hevner/Peffers) + estudo de caso único (Yin)**, pesquisa aplicada quali-quantitativa. Declarar: artefato, classe de problema, requisitos mensuráveis (KPIs), unidade de análise (terreno/oportunidade MCMV em Marília), fontes e período de coleta, protocolo de treino/validação dos modelos, e protocolo da validação com casos BM3. (orientador + metodólogo + banca)

2. **[P0] Inserir pergunta de pesquisa única + 3-5 objetivos específicos mensuráveis**, logo após o objetivo geral. Cada objetivo específico deve mapear para uma seção de Resultados. (orientador + banca)

3. **[P0] Criar a seção "Resultados" (não "esperados") com Experimento A — backtest do AVM.** Rodar o modelo e **congelar uma tabela** com: MAE, MAPE, RMSE do P50; cobertura observada P10–P90 e P25–P75 vs. nominal (50%); **pinball loss por quantil** (métrica correta para regressão quantílica, hoje ausente); tudo **contra o baseline de bairro** (`quick_avm` = preço/m² mediano × área). Sem comparação com baseline, o AVM não se justifica. Hoje MAE/coverage só vão para `logger.info` (`price_model.py:545-556`) — persistir como tabela reportável. (metodólogo + técnico + banca — é a 1ª pergunta da banca)

4. **[P0] Reproduzir pelo menos um caso BM3 ex-post (Experimento B reduzido).** Caso Casa 1 (Santa Antonieta, vendida 2020, margem real 24%): recomendação retrospectiva do sistema vs. desfecho real; e as 2 casas paradas (Santa Clara, estouro 11%) como contra-exemplo. Rotular explicitamente como **evidência de caso, n pequeno, sem significância estatística**. (metodólogo + banca; calibrado pela restrição de dados que a banca confirmou)

5. **[P0] Declarar conflito de interesse + limitações de validade externa.** Autor-BM3 (legítimo em DSR/pesquisa-ação, *se declarado* com salvaguarda); N=1 cidade / N=1 empresa; nota de transferibilidade (por que o **método** transfere mesmo que os **dados** não). (orientador + metodólogo + banca)

6. **[P0] Inserir seção/parágrafos sobre LGPD e licitude do tratamento.** Distinguir dados abertos × dado pessoal; hipótese legal (legítimo interesse); minimização/anonimização; respeito a termos de uso/robots.txt dos portais. Sistema processa nome de devedor/inventariado — sem isso é flanco jurídico. (banca — acréscimo crítico não coberto pelas outras lentes)

#### P1 — Importantes (fortalecem o mérito e blindam a arguição)

7. **[P1] Corrigir overclaims técnicos no texto** (deflação para honestidade defensável), conforme auditoria técnica + redação:
   - XGBoost/Gradient Boosting: manter como **referencial teórico**; declarar que a implementação usa LightGBM (principal) + RandomForest (fallback).
   - **VPL**: não é exposto como saída (só interno ao cálculo da TIR, `viability.py:505`). Reposicionar como *base conceitual da TIR* ("a taxa que zera o VPL") **ou** expor o VPL como saída no código. Não prometer indicador que a interface não entrega.
   - **RAG/busca semântica**: frasear como "infraestrutura de embeddings (text-embedding-004, 768d, pgvector) em produção indexando listings e documentos; busca semântica implementada como serviço, integração à interface em andamento". Nunca como feature de produto entregue (retrieval não tem consumidor — `embedder.py:244,260`).
   - **Não reivindicar grafo de proprietários** (não existe; decisão "sem Neo4j" registrada).
   - Trazer ao texto o **ITBI peso 2.0** como mitigação explícita do viés de oferta.

8. **[P1] Reposicionar Canvas/SWOT/MVP como "Aplicação gerencial", subordinada aos Resultados** — e torná-los acionáveis (resolução do conflito nº1):
   - Canvas: adicionar **Estrutura de custos** (bloco faltante — o custo dominante é manutenção de coletores, não infra) e **KPIs** (MAPE/cobertura, oportunidades/mês, frescor dos dados).
   - SWOT: tornar acionável — moat = profundidade municipal local cumulativa; barreira de entrada = economia de atenção do incumbente; fraqueza honesta = **ITBI de Marília sem feed estruturado** (`itbi_marilia.py:13,111`), o dado mais valioso é o mais frágil.
   - Matriz de benchmarking (MaríliaBot × Urbit × DataZAP+ × Hiperdados × Locates) substituindo o parágrafo corrido, com fontes verificadas jun/2026.

9. **[P1] Dimensionamento de mercado e modelo de receita com números** (mercado, dosado): TAM/SAM/SOM mínimo com fontes (FJP déficit habitacional ~6mi; CBIC/Sinduscon; cidades médias IBGE; MCMV Min. Cidades); precificação ancorada no **valor da decisão** (laudo R$300–800 frente a decisão de R$100k–1M+); break-even ilustrativo (poucos clientes cobrem custo). Assumir o nicho como **cunha (wedge)** explícita, não fingir mercado grande.

10. **[P1] Corrigir split aleatório → temporal e isolar `neigh_avg` no treino** (se houver tempo — resolução do conflito nº3). Reportar holdout só-ITBI separado. Se não houver tempo, declarar como limitação (já coberto no P0-5, mas o ideal é corrigir e virar força). (metodólogo + banca)

11. **[P1] Justificar premissas financeiras**: `WORKING_CAPITAL_ANNUAL_PCT=18%` ancorado a custo de capital BM3 ou Selic+prêmio; declarar calibração de custos como **n=3 engineering priors** (1 ciclo completo + 2 paradas), não estimativa estatística; citar o `TODO(prod-calibration)` de `test_viability.py` como maturidade. Estender análise de sensibilidade (já existe SINAPI ±10%) a preço de venda e prazo. (metodólogo + técnico)

#### P2 — Melhorias (lapidação final)

12. **[P2] Calibrar o objetivo geral**: trocar "desenvolver e analisar" por verbo com critério — "desenvolver e **avaliar a acurácia e a utilidade decisória** de…, comparando recomendação do sistema vs. decisão tradicional em casos da BM3".

13. **[P2] Resolver os cortes de transcrição `[…]`** na Introdução e Fundamentação — sinalizam texto inacabado.

14. **[P2] Acionar o `tcc-redator` para a passada de prosa** (somente após P0 fechados): aplicar as reescritas trecho-a-trecho propostas; padronizar siglas (sigla + extenso na 1ª ocorrência: AVM, VGV, TIR, VPL, SHAP, SINAPI, MCMV), estrangeirismos em itálico, voz impessoal no presente para o artefato e futuro só para a avaliação, aspas tipográficas. **Não acionar antes dos P0** — lapidar prosa de estrutura incompleta é desperdício (consenso orientador + redator).

15. **[P2] Caracterizar robustez de coleta**: estar pronto para discutir taxa de sucesso/falha dos coletores (pipeline usa `continue-on-error` + retries); não introduzir o termo "score de risco robusto" (`risk_scorer.py` tem só 158 linhas).

---

### Cronograma sugerido até a entrega

Sequenciamento por dependência (estrutura antes de prosa; números antes de discussão). Assumindo ~4 semanas até a entrega — comprima proporcionalmente se houver menos tempo, mas **mantenha a ordem**:

| Fase | Janela | Entregáveis | Lentes que validam |
|---|---|---|---|
| **Semana 1 — Esqueleto + números (P0 estruturais)** | dias 1–7 | (a) Rodar o modelo e congelar a **tabela de métricas** do Experimento A (MAE/MAPE/RMSE/cobertura/pinball vs. baseline de bairro); (b) escrever **pergunta de pesquisa + objetivos específicos**; (c) rascunho da **seção Metodologia** (DSR + estudo de caso). | metodólogo, técnico |
| **Semana 2 — Resultados + salvaguardas (P0 restantes)** | dias 8–14 | (d) Seção **Resultados** com tabela + **caso Casa 1 ex-post** e contra-exemplo das paradas; (e) parágrafos de **conflito de interesse + limitações N=1 + transferibilidade**; (f) seção **LGPD/licitude**. Fechar todos os P0 ao fim da semana. | orientador, banca |
| **Semana 3 — Honestidade técnica + mercado (P1)** | dias 15–21 | (g) **Correção dos overclaims** (XGBoost/VPL/RAG/grafo) + ITBI peso 2.0 no texto; (h) reposicionar **Canvas/SWOT/MVP** como aplicação gerencial + **matriz de benchmarking** + dimensionamento/receita/break-even; (i) justificar premissas financeiras; (j) *se houver folga*: corrigir split temporal + `neigh_avg`. | técnico, mercado, metodólogo |
| **Semana 4 — Lapidação + ensaio de defesa (P2)** | dias 22–28 | (k) Passada do **`tcc-redator`** (reescritas, siglas, estrangeirismos, `[…]`); (l) calibrar objetivo geral; (m) **simulação de banca** com as 7 perguntas vermelhas — confirmar que cada uma tem resposta com número/declaração no texto. | redator, banca, orientador (consolidação final) |

**Marcos de não-regressão:** ao fim da Semana 2, nenhum P0 pode estar aberto — é o gate de prontidão para defesa com mérito. As Semanas 3–4 elevam a nota; a Semana 2 é o que separa aprovação de reprovação no enquadramento.

**Observação de consolidação:** os P0 são todos de *transposição texto↔código + honestidade*, não de engenharia nova — exceto o item P0-3 (rodar o modelo e tabular métricas), que é a única peça que exige execução de código e por isso vai no início. Se um único item tiver de cair por falta de tempo, **nunca corte um P0**; corte P1-9 (dimensionamento de mercado) ou P1-10 (correção do split, desde que declarado como limitação).

Arquivos canônicos: `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/docs/TCC_draft.md`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/price_model.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/viability.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/feedback_loop.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/embedder.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/collectors/itbi_marilia.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/tests/test_viability.py`.

---

# 1. Orientador — estrutura e prontidão

O lastro técnico existe e é robusto (LightGBM quantílico, SHAP, fallback RF, viabilidade com VGV/TIR/payback/margem calibrada por casos reais da BM3, SINAPI via IBGE). Tenho material suficiente para confrontar texto e código. Vou produzir o parecer no formato definido.

## Parecer do Orientador

### Veredito de prontidão: 🟡 em desenvolvimento

O trabalho **não está pronto para defesa**, mas a distância é menor do que o texto sozinho sugere — e o problema é quase inteiramente de *forma acadêmica*, não de substância. Há um produto real e tecnicamente sério por trás (LightGBM quantílico com intervalos de incerteza, SHAP para explicabilidade com fallback para RandomForest, motor de viabilidade com VGV/TIR/payback/margem calibrado em casos reais da BM3, coletor SINAPI via IBGE, dezenas de coletores de fontes públicas). O risco é o inverso do habitual: você tem mais sistema do que TCC. O documento de 65 linhas é, hoje, um **plano de negócios bem escrito disfarçado de monografia** — Canvas, SWOT, proposta de valor, MVP, fontes de receita — sem os elementos que uma banca de MBA USP exige para chamar isso de pesquisa: pergunta de pesquisa explícita, objetivos específicos, **Metodologia** e **resultados medidos** (não "esperados"). Como está, a banca aprova o esforço de engenharia mas reprova o enquadramento acadêmico.

### Fio condutor (problema→objetivo→resultado)

- **Conecta bem na entrada:** problema (incerteza na escolha de terreno para MCMV, dados fragmentados, preço de anúncio ≠ preço de transação) → motivação (BM3, margens apertadas) → solução (MaríliaBot). Os três primeiros elos são coerentes e bem argumentados. Esta é a maior força do texto.
- **Quebra no objetivo geral:** "desenvolver **e analisar**" — analisar com qual critério? Contra qual baseline? O verbo "analisar" promete uma avaliação que o texto nunca operacionaliza. Não há objetivos *específicos* (lista de 3-5 verbos mensuráveis). Para MBA isso é lacuna grave, não estilística.
- **Quebra fatal no final:** a seção 3 fala em "resultados **esperados**" e "critérios que **poderão** ser considerados". Um TCC que defende um sistema já construído não pode entregar só expectativa — você tem código rodando e casos da BM3 (a calibração da viabilidade cita "Casa 1, Santa Antonieta, vendida 2020, margem 24%"). O elo final do fio condutor existe no repositório mas **não foi puxado para dentro do texto**. Hoje o trabalho promete e não mostra, quando na verdade tem o que mostrar.

### Lacunas estruturais bloqueadoras

1. **Ausência de seção Metodologia** — bloqueia porque uma banca de MBA classifica o trabalho pelo método. Sem ela não há como avaliar rigor. Precisa declarar: natureza (pesquisa aplicada / estudo de caso único / pesquisa-ação — recomendo **estudo de caso único com elementos de design science / pesquisa-ação**, já que você é agente do caso), unidade de análise, fontes de dados, período de coleta, como os modelos foram treinados/validados (split, métrica, n de transações ITBI), e como a validação com casos reais da BM3 foi feita.

2. **Ausência de pergunta de pesquisa e objetivos específicos explícitos** — o objetivo geral existe em prosa diluída; faltam a pergunta única e a lista de objetivos específicos. Bloqueia porque é o esqueleto que a banca usa para checar se o trabalho cumpriu o que prometeu.

3. **Seção de Resultados reais inexistente** — "resultados esperados" não é resultado. Bloqueia a nota de mérito. Você precisa de números: MAE/MAPE do AVM, cobertura de bairros, nº de oportunidades detectadas, e pelo menos **um caso BM3 reproduzido** (decisão real vs. recomendação do sistema). O material existe no código — falta transpor.

4. **Conflito de interesse não declarado** — você é da BM3 e o caso é a BM3. Isso é legítimo em pesquisa-ação, mas **tem de estar declarado** com a salvaguarda metodológica (por que isso não invalida os achados). Sem declaração, a banca levanta como objeção e você fica na defensiva.

5. **Generalização a partir de N=1 cidade / N=1 empresa não endereçada** — o texto vende "solução hiperlocal" como diferencial mas não discute limites de validade externa. A banca vai perguntar "isso vale só para Marília?". Precisa de um parágrafo honesto de limitações + nota de transferibilidade.

### Pontos fortes a preservar

- **Introdução e formulação do problema** são sólidas: o ponto "anúncio ≠ transação" e a lógica "a viabilidade se decide antes da obra" são teses defensáveis e bem colocadas.
- **Fundamentação teórica madura:** AVM, quantis para incerteza, SHAP para explicabilidade, SINAPI, VPL/TIR/VGV — o referencial está ancorado em conceitos certos e, raro, **batem com o que o código realmente faz**. Não há descolamento teoria-implementação aqui; isso protege você na arguição técnica.
- **Posicionamento competitivo** (Urbit/DataZap/Hiperdados concentrados em capitais → lacuna hiperlocal) é uma contribuição original genuína e defensável.
- **Lastro técnico real:** ao contrário de muitos TCCs de MBA, o sistema existe, roda e tem testes (incluindo `test_viability.py`). Isso é trunfo — desde que entre no texto como evidência.

### Plano de ação priorizado (o que fazer antes da entrega)

1. **[P0] Escrever a seção Metodologia** (atualmente ausente). Declarar tipo de pesquisa (sugiro estudo de caso único + design science/pesquisa-ação), unidade de análise, fontes, período, protocolo de treino/validação dos modelos e protocolo da validação com casos BM3.
2. **[P0] Inserir pergunta de pesquisa única + 3-5 objetivos específicos mensuráveis** logo após o objetivo geral, na Introdução. Cada objetivo específico deve mapear para uma seção de resultado.
3. **[P0] Criar a seção "Resultados" (não "esperados")** com métricas reais extraídas do sistema (acurácia do AVM, cobertura, nº de oportunidades) e **pelo menos um caso BM3 reproduzido** — o material já existe no repositório (`src/viability.py`, dados ITBI/SINAPI). Sem isso não há mérito a defender.
4. **[P1] Declarar conflito de interesse e limitações** (autor-BM3; N=1 cidade/empresa; dependência de qualidade de dados públicos). Transforme objeção da banca em rigor demonstrado.
5. **[P1] Reposicionar Canvas/SWOT/MVP como aplicação gerencial, não como espinha dorsal.** Mova-os para uma seção "Modelo de aplicação / proposta de valor" subordinada aos resultados, para que o trabalho leia como pesquisa aplicada e não como plano de negócios.
6. **[P2] Calibrar o objetivo geral:** trocar "desenvolver e analisar" por verbo com critério ("desenvolver e **avaliar a acurácia e a utilidade decisória** de…, comparando recomendação do sistema vs. decisão tradicional em casos da BM3").
7. **[P2] Resolver os cortes de transcrição `[…]`** nos parágrafos da Introdução e Fundamentação antes da versão final — sinalizam texto inacabado para a banca.

Observação de consolidação: antes da defesa, recomendo fechar a rodada com os pareceres de `tcc-metodologo` (seção Metodologia, P0) e `tcc-tecnico` (confirmar que as métricas levadas ao texto correspondem ao que o sistema entrega — particularmente o AVM e a calibração da viabilidade). Não acione `tcc-redator` antes dos P0 estruturais estarem fechados; lapidar prosa de uma estrutura ainda incompleta é desperdício.

Arquivos relevantes confrontados: `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/docs/TCC_draft.md`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/price_model.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/viability.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/avm_explain.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/collectors/sinapi.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/tests/test_viability.py`.

---

# 2. Técnico — auditoria texto × código

Auditoria completa. Confirmei os fatos-chave com arquivo:linha. Os achados decisivos: (1) embeddings/pgvector ESTÃO ativos em produção (geração), corrigindo a base de partida; (2) as funções de busca semântica RAG existem mas NÃO estão consumidas — geração sem retrieval ligado; (3) train/test split real com test_size=0.2; (4) MAE e coverage são logados mas não persistidos como métrica de validação reportável; (5) grafo de entidades realmente não existe; (6) zoning usa Gemini+pdfplumber, não é mero heurístico.

## Auditoria Técnica (texto × código)

### Afirmações verificadas

| Afirmação do TCC | Status | Evidência (arquivo:linha) | Fraseado sugerido |
|---|---|---|---|
| "estima valores de mercado" (AVM) — §1 (L21), §3 | ✅ | `src/price_model.py:1-8, 526-559` — LightGBM quantile (alpha 0.10/0.25/0.50/0.75/0.90), fallback RandomForest em `:134-147` | — |
| "regressão por quantis... estimar não apenas valor único, mas intervalos de incerteza" — §2 (L33) | ✅ | `src/price_model.py:42 QUANTILES`, `:522-559` produz P10–P90 + intervalo P25–P75; guard contra crossing em `:621-623` | — |
| "Random Forest, Gradient Boosting, XGBoost e LightGBM... LightGBM" — §2 (L32) | ⚠️ | Só LightGBM + RandomForest existem (`:466, :136`). XGBoost/GB citados como teoria, não implementados | Manter como referencial teórico; deixar claro que a implementação usa LightGBM (principal) e RandomForest (fallback) |
| "Técnicas como SHAP permitem decompor a previsão... justificativas interpretáveis" — §2 (L35) | ✅ | `src/price_model.py:561-580` (TreeExplainer sobre P50) + fallback feature_importance `:586-604`; narrativa PT-BR em `src/avm_explain.py:43-87`, labels em `FEATURE_LABELS_PT:68` | — |
| "VGV, custo total, margem, VPL, TIR e prazo de retorno" — §2 (L37) | ⚠️ | `src/viability.py` calcula VGV `:267`, margem `:282-283`, ROI `:284`, **TIR via Newton** `:500-517`, payback (`MAX_PAYBACK_ANOS:125`). **VPL/NPV não é exposto como indicador** — só usado internamente dentro do cálculo de TIR (`:505`) | Trocar "VPL" por "TIR (calculada pelo método de Newton), margem e payback", ou expor o VPL como saída se quiser citá-lo |
| "limites de preço, faixas de renda... MCMV" — §2 (L37) | ✅ | `src/viability.py:69-115` 4 faixas (Faixa 1/2/3 + teto R$600k), tetos por faixa, lote mínimo 125m², RET 1%/4% | — |
| "SINAPI... referência de custos" — §2 (L39) | ✅ | `src/collectors/sinapi.py`; `src/viability.py:41` calibra contra SINAPI 2020 | — |
| "coleta de dados de diferentes fontes públicas e abertas" — §1 (L21) | ✅ | 35 coletores em `src/collectors/` (5 portais on-market: vivareal, zapimoveis, imovelweb, chavesnamao, toca; 5 off-market: leilão, alvará, inventário TJSP, IPTU devedor; institucionais: SINAPI, IBGE, ITBI, obras públicas, CNPJ, EIV, CMDU, agronegócio, etc.) | — |
| "organiza em base estruturada / banco com extensão geoespacial" — §1, §3 (L61) | ✅ | `sql/042_postgis.sql`; `src/spatial.py:8` `get_economic_centroid_distances`, score MCMV `:162` | — |
| "bot de mensagens" / canais de entrega — §3 (L51) | ✅ | `src/telegram_bot.py:167-194` — 12+ comandos (`/top`, `/bairro`, `/viabilidade`, `/ficha`, `/mercado`, `/relatorio`, `/deal_*`, `/calibration`) | — |
| "dashboard web" — §3 (L51, L59) | ✅ | `dashboard/` (React + Vite, ~15 componentes) | — |
| "serviços de IA em nuvem" — §3 (L61) | ✅ | Gemini/Vertex em `src/embedder.py:62-71`, `src/collectors/zoning_marilia.py:153` | — |
| "alertas automatizados" — §3 (L51) | ✅ | `src/alerts.py:46-70` | — |
| Pipeline automatizado / "coleta automatizada" — §1 (L19) | ✅ | `.github/workflows/pipeline.yml:4-6` cron `0 9 * * *` = 06:00 BRT; jobs até timeout 30min `:23` | — |
| "deduplicação / normalização" — §3 (L53) | ✅ | `src/deduplicator.py` (28KB), `src/normalizer.py` (29KB), `src/address.py:118` similaridade | — |
| "valores anunciados nem sempre representam transações reais" → mitigação | ✅ ➕ | `src/price_model.py:35, 125-130, 477-486` — ITBI real como ground truth com **peso 2.0** vs listings peso 1.0; comentário explícito "elimina survivorship bias" | O texto descreve o problema mas **não menciona que o sistema o resolve** — ver subnotificado |

### ❌ / ⚠️ Não suportadas ou parciais

| Afirmação implícita | Status | Evidência | Ação |
|---|---|---|---|
| Grafo de proprietários/relacionamentos | ❌ | Tabelas `entities`/`relationships` não existem em `sql/` (grep sem resultado) | Não reivindicar; trabalho futuro |
| RAG / busca semântica como funcionalidade ativa | ⚠️ | Embeddings **são gerados** em produção (`embedder.py` + job `embedding-generation` em `municipal-data.yml:128-145`, dependência do job final `:187`). Porém `search_similar_listings` (`:244`) e `search_documents` (`:260`) **não têm consumidor** no código — nenhuma chamada fora da própria definição. RAG = pipeline de indexação pronto, recuperação não conectada | Dizer "infraestrutura de embeddings (text-embedding-004, 768d, pgvector) em produção indexando listings e documentos municipais; busca semântica implementada como serviço, integração à interface em andamento" |
| Parser formal do Plano Diretor | ⚠️ (melhor que a base assumia) | `src/collectors/zoning_marilia.py:153-198` usa **pdfplumber + Gemini** para extrair zonas do PDF, com fallback de 5 zonas hardcoded (`:28-82`, baseadas na LC 753/2017). Não é mero heurístico, mas depende de LLM e tem fallback estático | Pode reivindicar "extração de zoneamento do PDF do Plano Diretor via LLM (Gemini), com fallback determinístico" — honesto e forte |

### ➕ Subnotificado (use isto a favor!)

- **ITBI real como ground truth com peso 2.0** para mitigar viés de sobrevivência — `src/price_model.py:35, 477-486`. O TCC descreve o problema ("anúncios ≠ transações reais", §1 L15) mas não diz que o sistema o ataca diretamente. É exatamente a contribuição metodológica que diferencia de um AVM ingênuo. **Coloque isso no texto.**
- **TIR pelo método de Newton** (implementação própria, não biblioteca) — `src/viability.py:500-517`. Demonstra rigor financeiro.
- **Calibração com 3 projetos reais da BM3** — `src/viability.py:27-41` (Casa 1 Santa Antonieta vendida 2020; Casas 2/3 Santa Clara, estouro 11%). Ancora o trabalho em dados primários reais, não só públicos.
- **5 centroides econômicos georreferenciados de Marília** (comercial/saúde/educação/industrial/histórico) — `src/spatial.py:201-211` + features no AVM `price_model.py:51-56`. Hiperlocalização concreta, não genérica.
- **Score de acessibilidade MCMV (0-100) com critérios da Caixa** — `src/spatial.py:24, 162`; usado como feature `price_model.py:58`.
- **18 features no AVM** (`FEATURE_NAMES`, `price_model.py:44-65`: 17 base + target-encoding de bairro adicionado pós-split `:64, 514`), incluindo índice de agronegócio/safra `:63`.
- **RET dinâmico (1% Faixa 1 / 4% demais)** — `src/viability.py:57-58, 271`. Detalhe tributário real do MCMV.

### Riscos técnicos para a defesa

- **Métricas de validação do AVM não são reportáveis.** O código calcula MAE por quantil (`price_model.py:545`) e coverage P25–P75 (`:554-556`), com train/test split real (`test_size=0.2, random_state=42` em `:499`). MAS: MAE só vai para log (`logger.info`), e coverage é persistido em `stats` mas não há tabela/relatório de validação histórica. **Não há MAPE.** O comentário em `:523` revela que a coverage já esteve em 31.7% contra alvo de 50% — a banca pode perguntar o valor atual e você não tem um número consolidado pronto. **Recomendação ao metodólogo:** rodar o modelo e registrar MAE/MAPE/coverage atuais como tabela no TCC antes da defesa.
- **RAG anunciado vs. entregue.** Se o texto sugerir "busca semântica" como recurso do usuário, a banca pode pedir demonstração — e a recuperação não está ligada à interface. Fraseie como infraestrutura/serviço, não como feature de produto.
- **`risk_scorer.py` tem só 158 linhas** (`wc -l`) — não sustenta a expressão "score de risco robusto". O TCC atual não usa esse termo explicitamente (bom), mas evite introduzi-lo.
- **Cobertura de dados depende de coletores frágeis** (scrapers de portais on-market). A "qualidade dos dados" é citada como critério de avaliação (§3 L65) — esteja pronto para discutir taxa de sucesso/falha de coleta, já que o pipeline usa `continue-on-error` e retries (`municipal-data.yml`).

Arquivos-chave para a defesa: `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/price_model.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/viability.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/spatial.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/embedder.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/.github/workflows/pipeline.yml`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/.github/workflows/municipal-data.yml`.

---

# 3. Metodólogo — método e rigor de ML

Tenho tudo que preciso. Vou compor o parecer no formato exato definido pela persona.

## Parecer Metodológico

### Enquadramento de pesquisa recomendado

O TCC deve declarar-se como **pesquisa aplicada, de abordagem quali-quantitativa**, conduzida sob **Design Science Research (DSR)** combinada com **estudo de caso único** (BM3/Marília-SP). O DSR é o enquadramento mais forte porque o trabalho não testa uma hipótese sobre o mundo — ele *constrói um artefato* (a plataforma MaríliaBot/Cérebro V2) para resolver um problema de classe ("reduzir incerteza na análise de viabilidade de terrenos para habitação popular em cidades médias"). DSR exige justamente o que o draft não tem: (i) identificação rigorosa do problema e dos *requisitos*; (ii) ciclos de relevância–design–rigor; e (iii) **avaliação do artefato** contra critérios mensuráveis — não basta "demonstrar que foi construído". O estudo de caso da BM3 fornece o ambiente de relevância e os dados de validação (3 projetos históricos + funil de deals reais via `bm3_deals`). A unidade de análise é o terreno/oportunidade de empreendimento MCMV em Marília. Recomendo escrever explicitamente: artefato, classe de problema, requisitos de design (KPIs), proposições de avaliação e limitações do generalização (n=1 cidade, n pequeno de projetos).

### Esqueleto da seção Metodologia (que falta no TCC)

O TCC atual **não possui seção de Metodologia** — é a lacuna nº1. Esqueleto proposto:

**1. Natureza e abordagem.** Pesquisa aplicada, quali-quantitativa, exploratória-descritiva. Justificar DSR (cite Hevner et al. / Peffers et al. — DSRM) e estudo de caso (Yin).

**2. Método (DSR — ciclos e atividades).** Mapear as 6 atividades do DSRM: (a) identificação do problema (Seção 1); (b) objetivos da solução = requisitos mensuráveis do artefato; (c) design e desenvolvimento (pipeline de coletores → normalização/dedup → AVM → viabilidade → ranking → bot); (d) demonstração (caso BM3); (e) **avaliação** (Seção 5 abaixo); (f) comunicação (o próprio TCC). Declarar que ocorreram iterações (o repositório já evidencia versionamento do modelo: `lgbm_q_v3` com nota de recalibração de cobertura em 2026-05-11).

**3. Fontes e coleta de dados.** Tabela das fontes públicas com: órgão, natureza (oferta vs transação), periodicidade, volume e *limitações*. Distinguir explicitamente **dados de oferta** (portais: Viva Real, ZAP, ImovelWeb, Chaves na Mão) de **dados de transação** (ITBI/`itbi_transactions`, receitas municipais). Declarar período de coleta, unidade de análise, deduplicação (`fingerprint`/`deduplicator`) e tratamento de PII. Aprovação ética/uso de dados abertos.

**4. Construção do artefato.** Arquitetura em camadas (coleta → enriquecimento espacial → modelos → decisão → interface). Descrever o AVM (LightGBM quantílico, features em `FEATURE_NAMES`), o simulador de viabilidade (SINAPI + premissas BM3) e o ranqueador (Hunter). Declarar versão dos modelos e dependências.

**5. Protocolo de avaliação (métricas + experimento).** É o que separa um TCC de engenharia de um TCC científico. Ver as duas subseções seguintes.

### Rigor estatístico / ML — achados

| Tópico | Situação (verificada no código) | Risco | Recomendação |
|---|---|---|---|
| Métricas do AVM | **Parcial.** `price_model.py` calcula MAE de teste por quantil (l.545) e *coverage* P25–P75 (l.549-556), mas **nada disso aparece no TCC**; falta MAPE/RMSE e **pinball loss** (a métrica correta para regressão quantílica) | alto | Reportar no TCC: MAE, MAPE, RMSE do P50 + **cobertura** P10–P90 e P25–P75 vs nominal (50%) + pinball loss por quantil. A cobertura é o melhor argumento de calibração de incerteza. |
| Split temporal vs aleatório | **Inadequado.** `train_test_split(..., random_state=42)` (l.499) é split **aleatório**; imóveis têm dimensão temporal (e o ITBI traz `transaction_date`) | alto | Adotar **split temporal** (treinar no passado, testar no futuro) ou *rolling-origin backtest*. Split aleatório com `days_listed`/`first_seen_at` infla otimisticamente o desempenho. Declarar isto como decisão metodológica. |
| Leakage — target encoding | **Correto, e bem feito.** `enc` é ajustado só com índices de treino (l.502-512) e o `global_mean` também vem só do treino. Documentar como ponto forte | baixo | Manter. Mencionar como mitigação explícita de leakage no TCC — banca valoriza. |
| Leakage — `neigh_avg_price_m2` | **Vazamento residual.** A feature `neigh_avg_price_m2` (l.359-366) e a target-enc são calculadas sobre **todos** os listings antes do split em parte do fluxo; `neigh_avg` é construído no conjunto inteiro (l.469) e depois usado em treino e teste | médio | Calcular médias de bairro apenas com observações de treino, igual ao target-enc. Caso contrário o teste "vê" o próprio preço médio. |
| Leakage — feature ≈ alvo | **Conceitual.** `neigh_avg_price_m2` e `neigh_target_enc` são quase a média do próprio preço/m² — preditores fortíssimos que podem mascarar a real capacidade preditiva | médio | Reportar desempenho com e sem essas features; discutir que parte do R²/MAE vem de "memorizar o bairro". |
| Viés de sobrevivência (oferta ≠ transação) | **Bem endereçado.** v3 injeta ITBI como ground truth com `sample_weight=2.0` (l.477-487) — mitigação real e citável | médio→baixo | Formalizar academicamente: (i) nomear o problema (preço anunciado superestima o transacionado / survivorship + asking-price bias); (ii) descrever a mitigação (ITBI ponderado); (iii) limitação residual: ITBI é **valor declarado** (subdeclaração fiscal) e mistura unidades; o peso 2.0 é heurístico, não otimizado. |
| ITBl no split | **Risco metodológico.** ITBI é concatenado ao pool *antes* do split (l.483-499), então transações reais caem tanto no treino quanto no teste de forma aleatória — mistura duas populações no holdout | médio | Avaliar separadamente em **holdout só-ITBI** (transações reais), que é o ground truth honesto. Reportar MAE/MAPE nesse subconjunto isolado. |
| Quantile crossing | **Tratado.** Há reordenação dos quantis por linha (l.622) — boa prática, citar | baixo | Manter; mencionar que cada quantil é um modelo independente (daí o crossing) e que o sort corrige. |
| Confiança/`confidence` | Heurística baseada em suporte do bairro (l.638), não probabilística | baixo | Descrever como índice de suporte amostral, não como intervalo de confiança estatístico — evitar overclaim. |
| Fallback RF | RF gera "quantis" por ±10/20% fixos (l.713-716) — não são quantis reais | médio | Declarar no TCC que a faixa do fallback é nominal, não estatística; usado só quando LightGBM indisponível. |
| Viabilidade (TIR/VPL) | TIR via Newton (`_calc_irr`) razoável, mas **VPL não é reportado** apesar de citado na fundamentação; taxa de desconto/`WORKING_CAPITAL_ANNUAL_PCT=18%` é premissa não justificada empiricamente; fluxo de caixa é estilizado (investimento linear na obra, receita linear na venda) | médio | Reportar VPL explicitamente (há TIR mas não VPL). Justificar a taxa de desconto (custo de capital BM3 ou Selic+prêmio). Fazer **análise de sensibilidade** já parcialmente existente (SINAPI ±10%, l.620-633) e estendê-la a preço de venda e prazo. |
| Calibração com n=3 projetos | `EFFICIENCY_FACTOR=0.85`, `REWORK_BUFFER=11%` derivados de **1 casa vendida + 2 paradas** | alto | Tratar explicitamente como **limitação**: calibração com n=3 (sendo só 1 ciclo completo) não tem poder estatístico; as constantes são *engineering priors*, não estimativas. O `test_viability.py` inclusive tem um `TODO(prod-calibration)` admitindo margens negativas em Faixa 1/2. |
| Validação online (já existe!) | **Ponto forte subexplorado.** `feedback_loop.py` já implementa o experimento de validação: snapshot de AVM/Hunter/viabilidade no momento da visita e cruzamento com resultado real (`run_calibration`): AVM hit-rate P25–P75, AVM mean error %, viability error vs margem realizada, hunter hit-rate | — | Promover isto ao **núcleo do capítulo de avaliação**. Já há targets definidos (`AVM_TARGET=±10%`, `VIAB_TARGET=±5%`, `HUNTER_TARGET=25%`). |

### Experimento de validação proposto (factível com dados da BM3)

A defesa contra a pergunta nº1 da banca — *"como você sabe que o modelo acerta?"* — exige **dois experimentos**, ambos viáveis com o que já existe no repositório:

**Experimento A — Validação offline do AVM (backtest contra ITBI).**
- **Amostra:** transações reais de terreno em `itbi_transactions` (já coletadas), particionadas por **corte temporal** (treino: transações até T; teste: transações após T).
- **Baseline:** estimador ingênuo = preço/m² mediano do bairro × área (exatamente o `quick_avm` fallback). O AVM LightGBM só se justifica se *bater* esse baseline.
- **Métricas:** MAE, MAPE, RMSE do P50 no holdout só-ITBI; **cobertura** observada de P10–P90 e P25–P75 vs nominal; **pinball loss** por quantil.
- **Resultado esperado / critério de sucesso:** MAPE do AVM menor que o do baseline de bairro, e cobertura P25–P75 próxima de 50% (o código registra que estava em 31,7% antes da recalibração — material honesto para a seção de resultados e discussão).

**Experimento B — Validação prospectiva / decisão apoiada vs tradicional (estudo de caso quase-experimental).**
- **Desenho:** para um conjunto de N terrenos avaliados pela BM3 no período, registrar em paralelo (a) o **julgamento tradicional** do gestor (GO/NO-GO + preço-alvo, registrado *antes* de ver a plataforma) e (b) a **recomendação da plataforma** (AVM P25–P75, margem de viabilidade, score Hunter). Acompanhar os que avançaram no funil `bm3_deals` até `closed_won` e gravar o **resultado real** via `record_outcome` (margem e payback realizados).
- **Métricas:** (i) **erro absoluto do AVM** vs preço aceito real (`avm_mean_error_pct`); (ii) **acurácia da faixa** (% de preços aceitos dentro de P25–P75 — o `avm_hit_rate_p25p75` já calculado); (iii) **erro da margem projetada** vs margem realizada (`viability_mean_error_pct`); (iv) **hit-rate do Hunter** (oportunidades score≥70 que viraram deal); (v) concordância/discordância qualitativa entre gestor e plataforma e quem acertou *ex-post*.
- **Análise estatística honesta:** com n pequeno, **não** alegar significância; reportar erros médios com intervalo, número de observações, e tratar como evidência de *caso*, não de população. O próprio `weekly_drift_report` já emite o aviso "amostra pequena ... baixa significância estatística" quando n<5 — citar isso é honestidade metodológica que a banca recompensa.
- **Resultado esperado:** demonstrar que a análise apoiada reduz o erro de estimativa de preço/margem e/ou aumenta a velocidade/consistência da decisão frente ao método tradicional, *reconhecendo* que a validação definitiva exige acúmulo de mais ciclos de deal.

**Limitações a declarar explicitamente:** (1) generalização limitada (1 cidade, 1 empresa); (2) calibração de custos com n=3 projetos; (3) ITBI = valor declarado, sujeito a subdeclaração; (4) split temporal e isolamento de leakage residual (`neigh_avg`) ainda a corrigir no código; (5) baixa significância estatística da validação prospectiva no horizonte do TCC.

---
Arquivos canônicos lidos: `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/price_model.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/viability.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/comps.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/feedback_loop.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/reporter_drift.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/telegram/avm.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/tests/test_viability.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/docs/TCC_draft.md`.

**Achados load-bearing no código:** o leakage do target-encoding está corretamente mitigado (`price_model.py` l.502-512), mas o split é aleatório e não temporal (`train_test_split(..., random_state=42)`, l.499) e `neigh_avg` é calculado sobre o dataset inteiro (l.469) — vazamento residual. MAE de teste e cobertura P25–P75 **são calculados** (l.545-556) mas não constam no TCC. A validação online completa já existe em `feedback_loop.run_calibration()` (AVM hit-rate, erro médio, viability error vs outcome real) e deve ser o núcleo do capítulo de avaliação.

---

# 4. Mercado — negócio e benchmarking

Confirmei os diferenciais técnicos no código real. Tenho tudo o que preciso: o AVM (LightGBM quantílico + SHAP) é real, a viabilidade MCMV com SINAPI calibrada por dados reais da BM3 é real, o ITBI estruturado **não** existe em Marília (apenas dados parciais), pgvector/embeddings é real, e o "grafo de proprietários" não aparece como módulo. Vou produzir o parecer.

## Parecer de Mercado e Negócio

### Proposta de valor — está afiada?

A dor está bem **narrada** mas mal **quantificada**, e essa é a maior fraqueza da seção 3. O texto repete três vezes a ideia de "reduzir incerteza na escolha de terreno", mas em nenhum momento dimensiona o custo de errar nem o tamanho do problema. Para um TCC de MBA, faltam números que tornem a dor tangível:

- **Custo de um erro de terreno**: no caso BM3 (Casa 2/3 Santa Clara, paradas, estouro de 11% e 52% pago em cartão — dados que o próprio `viability.py` já calibra), há um caso real de prejuízo que deveria estar na seção de mercado, não só no código. Quantifique: qual foi o capital imobilizado? Quanto custou o erro de produto/terreno? Esse é o seu "antes" mais persuasivo.
- **Tamanho do segmento (TAM/SAM/SOM ausente)**: o texto diz "pequenas e médias incorporadoras em cidades médias" sem nenhum número. Falta: nº de incorporadoras/construtoras ativas no Brasil (CBIC/Sinduscon), nº de cidades médias (50–500k hab., faixa do IBGE onde Marília se encaixa), déficit habitacional (FJP ~6 milhões de moradias) e VGV do MCMV (programa relançado, meta de milhões de unidades). Sem isso, a banca pergunta: "para quantos clientes isso serve?"
- **A proposta de valor real está mais afiada no código do que no texto.** O diferencial defensável não é "transformar dados públicos em informação" (todo concorrente faz isso) — é **intervalo de negociação P25–P75 com SHAP em PT-BR + simulação MCMV calibrada com SINAPI e dados históricos reais da própria construtora**. Isso é específico e raro. O texto vende genérico ("análise integrada"); deveria vender o específico.

**Honestidade sobre nicho**: o segmento "habitação popular + cidade média + dados públicos" é genuinamente pequeno como mercado endereçável imediato. Mas é defensável como **cunha (wedge)**: começar onde os grandes (Urbit/DataZap) têm cobertura rasa e expandir cidade a cidade. O TCC ficará mais forte se assumir isso explicitamente como estratégia, em vez de fingir que o mercado é grande.

### Matriz de benchmarking (proposta)

Substitua o parágrafo corrido (linha 55) por esta tabela. Todos os concorrentes foram verificados em jun/2026 (fontes ao final).

| Critério | **MaríliaBot / Cérebro V2** | Urbit | DataZAP+ | Hiperdados | Locates |
|---|---|---|---|---|---|
| **Cobertura geográfica** | Hiperlocal (Marília-SP; expansível cidade a cidade) | Nacional, foco grandes centros | 280 cidades (precificação) | 120+ cidades, 16k+ empreendimentos | Grande Floripa, BH, SP, NE |
| **Fonte de dados** | Públicas/abertas + scraping de portais + bases municipais (IPTU, ITBI parcial, alvará, EIV, CMDU, Habite-se) | Big data geoespacial proprietário (120 camadas) | Base proprietária do grupo OLX/ZAP (1 bi+ anúncios) | Banco proprietário 1 bi+ registros, 17 anos | Geo + Plano Diretor + ambiental |
| **Precificação (AVM)** | LightGBM quantílico P25–P75 + SHAP em PT-BR (real, `price_model.py`) | Urbit AVM (apartamentos) | "Quanto Vale" AVM (foco listing/captação) | Data science + viabilidade | Projeção de indicadores financeiros |
| **Viabilidade construtiva** | Simulador MCMV (VGV/TIR/Payback) com SINAPI, calibrado em dados reais BM3 | Não é foco | Não | Sim (módulo viabilidade) | Sim (uso do solo + VGV potencial) |
| **Foco de produto** | Habitação popular / MCMV | Localização varejo + incorporação | Precificação + índices (FipeZAP) | ERP + BI + inteligência ponta a ponta | Prospecção de terreno + fundo imobiliário |
| **Público-alvo** | Pequena/média incorporadora interior | Incorporadoras, fundos, varejo | Corretoras, bancos, incorporadoras | Incorporadoras (40k+ usuários) | Incorporadoras + landowners |
| **Entrega** | Bot Telegram + relatório + (futuro) dashboard | Web/API/Ficha Territorial | API + plataforma + índices | Plataforma SaaS + ERP | Plataforma SaaS analytics |
| **Modelo comercial** | A definir (laudo/assinatura/consultoria) | SaaS + API + relatórios | SaaS + dados B2B | SaaS + ERP (ticket alto) | SaaS + co-investimento (fundo) |

**Leitura estratégica da matriz** (incluir no texto):
1. **Ninguém combina os 3 eixos do MaríliaBot ao mesmo tempo**: hiperlocal de cidade média + viabilidade MCMV específica + dados públicos municipais granulares (alvará/EIV/CMDU/Habite-se). Urbit e DataZAP têm AVM forte mas viabilidade MCMV não é foco; Locates tem viabilidade mas foca SC/grandes praças; Hiperdados é completo mas é ERP de ticket alto para incorporadora estabelecida.
2. **O moat defensável é a profundidade municipal local**, não a tecnologia de IA (LightGBM/SHAP são commodities). Os concorrentes não vão raspar o diário oficial e o CMDU de Marília — não compensa para eles. Essa **base cumulativa local** (já citada na SWOT) é o verdadeiro ativo.
3. **Ponto fraco honesto**: os concorrentes têm volume de dados de transação (1 bilhão+ de registros) que o MaríliaBot nunca terá. A resposta é que para terreno em cidade média, o sinal está nos dados públicos municipais + poucos comparáveis locais — não em big data nacional. Argumente isso.

### Canvas / SWOT — o que reforçar

**Canvas — lacunas:**
- **Estrutura de custos ausente** (o Canvas atual lista 8 dos 9 blocos e pula este). Precisa de ordem de grandeza: cloud (Supabase/Postgres+pgvector, ~US$25–100/mês inicial), APIs de IA (embeddings text-embedding-004 + LLM para laudo, custo por laudo na casa de centavos a poucos reais), scraping/proxies, e o custo dominante real = **horas de manutenção dos coletores** (cada portal/diário muda layout e quebra o scraper). Diga isso: o custo não é infra, é manutenção de pipeline.
- **Métricas-chave (KPIs) ausentes**: defina 3–4. Sugestão — (a) acurácia do AVM (MAPE / cobertura do intervalo P25–P75), (b) nº de oportunidades de terreno detectadas/mês, (c) taxa de decisões BM3 apoiadas pela plataforma vs. intuição, (d) frescor dos dados (lag de atualização). O TCC tem critérios de avaliação na seção 3 final — promova-os a métricas do Canvas.

**SWOT — está genérica; torne acionável:**

| Item atual (genérico) | Reescrita acionável |
|---|---|
| Força: "base cumulativa própria" | **Moat real**: base municipal local cumulativa (IPTU/ITBI/alvará/EIV/CMDU/Habite-se de Marília) que custa caro para um concorrente nacional replicar e barato para o MaríliaBot manter — efeito de dados que cresce com o tempo. |
| Força: "baixo custo operacional" | Quantificar (ver custos acima); só é força se sustentado com número. |
| Fraqueza: "dados públicos inconsistentes" | Específico: **ITBI de Marília não tem feed estruturado** (confirmado no código — só parcelamento e agregados), então o valor de transação real, o dado mais valioso para AVM, é o mais frágil. Mitigação: ARISP/cartórios + inferência. Admitir isso é maturidade. |
| Ameaça: "concorrente maior entra" | Resposta de barreira: por que Urbit não entra em Marília? Porque o ROI de raspar 1 cidade média não justifica o custo de manutenção do pipeline local para eles. A barreira é **economia de atenção do incumbente**, não tecnologia. Diga isso. |
| Ameaça: "mudança nas regras do MCMV" | Real e relevante — o produto está acoplado a um programa de governo. Mitigação: motor de viabilidade parametrizável por faixa/teto, já no código (`viability.py` com env vars). |

### Modelo de receita — plausibilidade

As quatro fontes (laudo, assinatura, consultoria, licenciamento) são plausíveis mas **sem precificação nenhuma** — isso precisa entrar para a banca não perguntar "por que alguém pagaria?".

- **Laudo de viabilidade sob demanda**: âncora natural. Compare com o custo de oportunidade — uma decisão de terreno mobiliza R$ 100k–R$ 1M+. Um laudo de R$ 300–800 é ruído frente a isso. **Ancore o preço no valor da decisão, não no custo de produzir o laudo.** Essa é a frase de defesa do modelo.
- **Assinatura (radar de oportunidades)**: receita recorrente, modelo SaaS. Sugira faixa (ex.: R$ 200–500/mês por incorporadora regional) e calcule break-even simples: se o custo operacional fixo é ~R$ X/mês (cloud + manutenção), bastam N assinantes para cobrir. Mesmo um break-even ilustrativo com 5–15 clientes mostra que o negócio "fecha" em escala pequena — o que reforça a tese de nicho viável.
- **Consultoria**: serviço, não escala — bom para validar/financiar o início, ruim como tese de produto. Posicione como bootstrap, não como core.
- **Licenciamento para outras cidades**: este é o **upside** e a resposta ao "nicho pequeno demais". O playbook é replicável: cada cidade média é um SAM novo. Mas só é crível se o custo de onboarding de uma nova cidade for baixo — e hoje NÃO é (cada cidade = novos coletores). Seja honesto: o licenciamento depende de reduzir o custo marginal de adicionar uma cidade, que hoje é a principal barreira interna.

**Break-even — incluir uma estimativa, mesmo que ilustrativa.** Sem ela a seção parece plano de negócios sem números. Com custo operacional na casa de centenas de reais/mês e ticket de laudo/assinatura nas centenas, o ponto de equilíbrio cai em pouquíssimos clientes — argumento forte de viabilidade em nicho.

### Verificação de diferenciais técnicos (antes de usá-los como vantagem)

Conferi no código para você não vender moat inexistente:
- **AVM quantílico P25–P75 + SHAP PT-BR**: REAL (`src/price_model.py`, `src/avm_explain.py`). Pode usar como diferencial.
- **Viabilidade MCMV com SINAPI calibrada em dados reais BM3**: REAL (`src/viability.py`). É o diferencial mais forte e mais honesto — pode e deve destacar.
- **Coletores municipais profundos** (IPTU, alvará, EIV, CMDU, Habite-se, zoneamento, ITBI): REAIS como módulos. Mas **ITBI estruturado NÃO existe em Marília** (confirmado no cabeçalho de `itbi_marilia.py`: prefeitura não publica feed) — não venda "valor de transação real" como capacidade consolidada; venda como esforço com fontes parciais (ARISP/cartório).
- **Embeddings/pgvector (RAG de documentos municipais)**: REAL (`src/embedder.py`).
- **"Grafo de proprietários"**: NÃO há módulo de grafo no `src/`. A própria memória do projeto registra decisão de "sem Neo4j". **Não use grafo de proprietários como moat** — não existe.

### Lacunas de dados de mercado a preencher (com fontes sugeridas)

| Lacuna | Fonte sugerida |
|---|---|
| Déficit habitacional (Brasil e região de Marília) | Fundação João Pinheiro (FJP); Atlas do Desenvolvimento Humano |
| Nº de incorporadoras/construtoras ativas e VGV do setor | CBIC, Sinduscon-SP, ABRAINC |
| Dimensionamento do MCMV (unidades/ano, tetos por faixa) | Ministério das Cidades / Caixa (regras 2025–2026 vigentes) |
| Nº e perfil de cidades médias no Brasil (universo do SAM) | IBGE (classificação por porte populacional) |
| Tamanho do mercado proptech BR e investimentos no setor | Distrito (Mapping Proptech), relatórios ABStartups |
| Posicionamento/preço dos concorrentes | Confirmados em jun/2026: Urbit (AVM, Ficha Territorial 120 camadas, API); DataZAP+ (280 cidades, "Quanto Vale", FipeZAP); Hiperdados (120+ cidades, 16k empreendimentos, 1bi+ registros, ERP); Locates (600k imóveis mapeados, ~R$8bi VGV potencial, fundo imobiliário) |
| Custo real de operar (cloud + IA + manutenção) | Tabelas de preço Supabase/Google AI; medir consumo real do próprio repositório |

### Veredito (lente de MBA)

A seção 3 hoje é **descritiva e qualitativa demais** — lê como apresentação de produto, não como análise de mercado de MBA. Para fortalecê-la sem virar plano de negócios (alerta ao orientador: dosar): adicione (1) dimensionamento mínimo TAM/SAM/SOM com fontes, (2) a matriz de benchmarking acima, (3) precificação + break-even ilustrativo, (4) estrutura de custos no Canvas, (5) SWOT acionável com a barreira de entrada explicitada. O ativo defensável é a **profundidade de dados municipais local + viabilidade MCMV calibrada com caso real BM3** — não a tecnologia de IA, que é commodity. E reconheça abertamente o risco de nicho: isso fortalece o trabalho, não enfraquece.

Arquivos relevantes consultados: `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/docs/TCC_draft.md`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/price_model.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/avm_explain.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/viability.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/collectors/itbi_marilia.py`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/embedder.py`

Fontes (verificação jun/2026): [Urbit](https://urbit.com.br/), [Urbit Ficha Territorial](https://urbit.com.br/ficha-territorial/), [DataZAP](https://www.datazap.com.br/en/), [DataZAP+ 280 cidades](http://www.revistaqualimovel.com.br/noticias/datazap-expande-precificacao-automatizada-de-imoveis-para-280-cidades-do-pais), [Hiperdados](https://hiperdados.com.br/site/), [Locates](https://locates.com.br/locates-plataforma-de-inteligencia-geografica-anuncia-fundo-imobiliario-para-acelerar-projetos/)

---

# 5. Banca — perguntas de defesa

All facts confirmed. The validation loop reads from `bm3_deals` outcomes that depend on completed deal cycles (which BM3 doesn't have yet — only 1 closed sale historically), there's no persisted AVM validation table, ITBI has no feed (no real ground-truth holdout possible today), and LGPD is essentially unaddressed in the text despite scraping personal-data sources (IPTU debtors, inventories, alvarás). Now I have everything to formulate the banca attacks.

## Simulação de Banca — Perguntas e Vulnerabilidades

> Persona: examinador de MBA USP, cético e implacável. Texto confrontado: `docs/TCC_draft.md`. Munição: pareceres do orientador, técnico, metodólogo e mercado, mais verificação direta no código (`price_model.py`, `viability.py`, `feedback_loop.py`, `itbi_marilia.py`).

### 🔴 Perguntas que o trabalho NÃO consegue responder hoje (resolver antes da defesa)

1. **P: "Você diz que o sistema 'estima valores de mercado'. Qual é o erro do seu AVM? Me dê o MAE, o MAPE e contra qual baseline você comparou."**
   Por que dói: o código calcula MAE de teste (`price_model.py:545`) e cobertura P25–P75 (`:554`), mas **nada é persistido nem reportado** — só vai para `logger.info`. Não existe MAPE, não existe tabela de validação (`grep` em `sql/` não acha nenhuma `model_metrics`/`avm_validation`), e **não há comparação com baseline** (o `quick_avm` de preço/m² mediano de bairro existe no código mas nunca foi usado como controle). O TCC inteiro promete "analisar" um sistema cuja acurácia não está medida no papel. Sem número, o mérito não existe.
   O que falta para responder: rodar o modelo e congelar uma tabela com MAE/MAPE/RMSE do P50, cobertura P10–P90 e P25–P75 vs. nominal, e **pinball loss por quantil** (a métrica correta para regressão quantílica, hoje ausente) — tudo contra o baseline de bairro. Sem isso, é a primeira pergunta da banca e a que mais derruba.

2. **P: "Você admite no próprio texto (§1) que anúncio ≠ transação. Seu modelo treina majoritariamente em anúncios. Então por que eu deveria acreditar na estimativa? E quando você valida contra transação real, qual o erro nesse subconjunto?"**
   Por que dói: o sistema *ataca* o problema (ITBI como ground truth com peso 2.0, `price_model.py:477-487`) — isso é uma contribuição metodológica real e nem está no texto. Mas a defesa quebra em dois pontos: (a) **Marília não publica ITBI estruturado** (`itbi_marilia.py:13,111` — "é necessário pedido LAI"), então o volume de ground truth real é frágil/quase inexistente hoje; (b) o ITBI é concatenado ao pool **antes** do split aleatório (`:483-499`), de modo que não há um holdout só-ITBI isolado para medir o erro contra transação verdadeira. A banca vai pedir exatamente esse número e ele não existe.
   O que falta para responder: confirmar quantas transações ITBI reais existem hoje na base; criar um **holdout só-ITBI** e reportar MAE/MAPE nele; e declarar a limitação residual de que ITBI é valor *declarado* (subdeclaração fiscal).

3. **P: "Seu split de treino/teste é aleatório (`random_state=42`). Imóvel tem dimensão temporal. Você não está deixando o modelo 'ver o futuro' e inflando o desempenho?"**
   Por que dói: confirmado — `train_test_split(..., test_size=0.2, random_state=42)` em `price_model.py:499` é split **aleatório**, não temporal, apesar de o ITBI trazer data de transação e os listings terem `first_seen_at`. Pior: `neigh_avg_price_m2` é calculada sobre o dataset inteiro (parecer do metodólogo, `:469`), então o conjunto de teste "enxerga" o próprio preço médio do bairro — **vazamento residual**. Qualquer métrica boa que ele apresentar será atacada como otimista.
   O que falta para responder: refazer com split temporal (ou rolling-origin backtest) e recalcular `neigh_avg` só no treino. Como isso exige mexer no código antes da defesa, hoje a resposta honesta é "está aleatório e há leakage residual" — uma admissão que enfraquece qualquer resultado apresentado.

4. **P: "Onde está a sua Metodologia? Qual a natureza da pesquisa, a unidade de análise, o protocolo de validação do artefato?"**
   Por que dói: **não existe seção de Metodologia** — é a lacuna nº1 apontada por orientador e metodólogo. Sem método declarado, uma banca de MBA não tem como classificar nem avaliar rigor. O verbo do objetivo geral é "desenvolver e **analisar**", mas o texto nunca operacionaliza "analisar com qual critério, contra qual baseline".
   O que falta para responder: escrever a seção declarando Design Science Research + estudo de caso único (BM3/Marília), com artefato, requisitos mensuráveis (KPIs), protocolo de treino/validação e protocolo da validação com casos BM3.

5. **P: "Seção 3 fala em resultados ESPERADOS e critérios que PODERÃO ser considerados. Você tem um sistema rodando há meses. Cadê os resultados medidos? Mostre um caso real da BM3 reproduzido: decisão tradicional vs. recomendação do sistema, com o desfecho real."**
   Por que dói: o trabalho defende um sistema construído mas entrega só expectativa. E a validação prospectiva que o sistema *poderia* mostrar depende de `bm3_deals` com `actual_outcome_margin_pct` preenchido (`feedback_loop.py`), ou seja, de **ciclos de deal fechados** — e a própria memória do projeto indica que a BM3 tem só **1 venda histórica concluída (Casa 1, 2020) e 2 casas paradas**. Não há volume de desfechos reais para reproduzir o experimento de decisão-apoiada-vs-tradicional hoje. A banca vai perceber que "validação por casos reais da BM3" é uma promessa sem dados.
   O que falta para responder: reproduzir pelo menos o **caso Casa 1** ex-post (recomendação retrospectiva do sistema vs. resultado real conhecido: margem 24%) e o caso das casas paradas como contra-exemplo. Mais que isso, hoje, não há.

6. **P: "Uma cidade, uma empresa — a sua. Isso é ciência ou consultoria interna? Como você mitigou o viés de avaliar a própria ferramenta na própria empresa?"**
   Por que dói: **conflito de interesse não declarado** + generalização N=1 não endereçada. O texto vende "solução hiperlocal" como diferencial mas não discute validade externa. Em pesquisa-ação isso é legítimo — *se declarado com salvaguarda*. Como não há nenhuma palavra sobre isso no texto, vira objeção aberta e o autor responde na defensiva.
   O que falta para responder: parágrafo declarando o conflito, justificando-o no enquadramento DSR/pesquisa-ação, e uma nota honesta de transferibilidade (por que o método transfere mesmo que os dados não).

7. **P: "Você raspa portais imobiliários, diários oficiais, lista de IPTU devedor, inventários do TJSP. Qual a base legal disso sob a LGPD? Você leu os termos de uso dos portais?"**
   Por que dói: o texto **não menciona LGPD, base legal, termos de uso ou robots.txt em lugar nenhum** (confirmado: nenhuma ocorrência em `docs/`; só um `audit.py` técnico em `src/`). E os coletores incluem fontes de **dado pessoal sensível** — `iptu_planta_marilia.py`, `cnpj_construtoras.py`, coletor de inventário/devedores. Para um sistema que processa nome de devedor e de inventariado, a ausência de qualquer discussão de licitude do tratamento é um flanco jurídico aberto que a banca de MBA explora com prazer.
   O que falta para responder: seção sobre licitude (dados abertos vs. dado pessoal), hipótese legal de tratamento (legítimo interesse), minimização/anonimização e respeito a termos de uso/robots dos portais. Hoje: zero.

### 🟡 Perguntas respondíveis, mas que exigem preparo

1. **P: "Já existem Urbit, DataZap, Hiperdados. O que você fez de novo além de aplicar a uma cidade pequena?"**
   Resposta sugerida: o diferencial defensável não é a tecnologia de IA (LightGBM/SHAP são commodity), e sim a **combinação de três eixos que nenhum concorrente cobre junto**: (i) profundidade de dados municipais hiperlocais (IPTU, alvará, EIV, CMDU, Habite-se de Marília) que não compensa um player nacional raspar; (ii) simulador de viabilidade **MCMV** com SINAPI calibrado por dados primários reais da BM3 (`viability.py:27-41`); (iii) intervalo de negociação P25–P75 com explicação SHAP em PT-BR. Os incumbentes têm AVM forte mas viabilidade MCMV não é foco; têm volume de transação que você nunca terá, mas o sinal para terreno em cidade média está no dado público municipal, não no big data nacional. A barreira de entrada é a **economia de atenção do incumbente**, não a tecnologia.

2. **P: "Cobertura dos intervalos de quantis — você mediu? Um intervalo P25–P75 que cobre 30% dos casos é inútil."**
   Resposta sugerida: sim, é medida (`price_model.py:554`), e há honestidade aqui — o comentário em `:523` registra que a cobertura **esteve em 31,7% contra alvo de 50%** e foi recalibrada (modelo `lgbm_q_v3`). Levar para o texto o valor *atual* consolidado e tratar o histórico de recalibração como evidência de ciclo DSR (design → avaliação → redesign), não esconder. Atenção: só vire isso uma força se o número atual estiver próximo de 50%; caso contrário a pergunta migra para o bloco vermelho.

3. **P: "Você cita VPL na fundamentação. Onde está o VPL nos resultados? E a taxa de desconto de 18% ao ano, de onde saiu?"**
   Resposta sugerida: ser honesto — o sistema calcula **TIR via método de Newton** (`viability.py:_calc_irr`, implementação própria, demonstra rigor) e payback, mas **o VPL não é exposto como indicador de saída**, só usado internamente no cálculo da TIR. Corrigir o texto: ou expor o VPL como saída, ou substituir "VPL" por "TIR, margem e payback" na fundamentação. Sobre o `WORKING_CAPITAL_ANNUAL_PCT=18%` (`:33`): hoje é premissa não justificada empiricamente — ancorá-la ao custo de capital real da BM3 ou Selic+prêmio antes da defesa.

4. **P: "Sua calibração de custos vem de quantos projetos?"**
   Resposta sugerida: assumir abertamente — `EFFICIENCY_FACTOR=0.85` e `REWORK_BUFFER=11%` derivam de **n=3 projetos** (1 venda completa + 2 paradas, `viability.py:27-41`). São *engineering priors*, não estimativas estatísticas. Tratar como limitação declarada, não como dado robusto. Mencionar que o próprio `test_viability.py` traz um `TODO(prod-calibration)` admitindo margens negativas em Faixa 1/2 — admitir isso é maturidade metodológica que a banca recompensa, e blinda contra a pergunta vir como ataque.

5. **P: "Você menciona busca semântica / RAG. Demonstre."**
   Resposta sugerida: fraseado defensivo — a infraestrutura de embeddings (text-embedding-004, 768d, pgvector) **está em produção indexando** listings e documentos municipais, e a busca semântica está implementada como serviço (`embedder.py`), mas a **recuperação ainda não está conectada à interface do usuário**. Vender como "infraestrutura pronta, integração em andamento", nunca como feature de produto entregue. Se prometer "busca semântica para o usuário", a banca pede demo e não há.

6. **P: "Qualidade dos dados públicos: como você trata defasagem, inconsistência e cobertura incompleta dos scrapers?"**
   Resposta sugerida: pipeline com deduplicação (`deduplicator.py`), normalização (`normalizer.py`), `continue-on-error` e retries no workflow; o custo dominante real do negócio é manutenção dos coletores (cada portal muda layout e quebra). Estar pronto para falar de taxa de sucesso/falha de coleta. Reconhecer que o dado mais valioso (transação real/ITBI) é justamente o mais frágil em Marília.

### Top 3 vulnerabilidades existenciais (se não resolver, compromete a aprovação)

1. **Ausência de resultados medidos + ausência de Metodologia.** O TCC defende um sistema cuja acurácia não está reportada e cujo método não está declarado. Hoje é um plano de negócios bem escrito, não uma monografia de pesquisa. Sem (a) tabela de métricas reais do AVM contra baseline e (b) seção de Metodologia DSR, **não há mérito acadêmico a defender** — é reprovação no enquadramento, independentemente da qualidade da engenharia.

2. **A própria afirmação central ("anúncio ≠ transação") vira arma contra o autor, e a validação real está vazia.** O modelo treina em anúncios; o ground truth (ITBI) não tem feed em Marília; o split é aleatório com leakage residual; e a validação prospectiva via `bm3_deals` não tem desfechos suficientes (1 deal fechado). A banca pode demonstrar, com o próprio texto e código, que a estimativa não está validada contra o mundo real. **Mitigação mínima:** holdout só-ITBI + reprodução ex-post do caso Casa 1.

3. **Conflito de interesse + LGPD não declarados.** Avaliar a própria ferramenta na própria empresa (N=1) sem salvaguarda metodológica, somado a raspar dados pessoais (IPTU devedor, inventários, diários) sem uma linha sobre base legal, abre dois flancos que a banca explora para colocar o autor na defensiva o tempo todo. São baratos de fechar no texto (dois parágrafos honestos cada) e caros de deixar abertos — transformam objeção previsível em rigor demonstrado.

---
Arquivos confrontados: `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/docs/TCC_draft.md`, `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/price_model.py` (split aleatório `:499`, MAE/coverage só em log `:545-556`, ITBI ground truth `:477-487`), `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/viability.py` (calibração n=3 `:27-43`, TIR Newton sem VPL exposto `:500`, capital 18% `:33`), `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/feedback_loop.py` (validação depende de `bm3_deals` com outcome, aviso n<5 `:499`), `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/src/collectors/itbi_marilia.py` (sem feed estruturado `:13,111`). Confirmado: nenhuma menção a LGPD/base legal/termos de uso em `docs/`; nenhuma tabela de validação persistida em `sql/`; nenhum consumidor de retrieval RAG ligado à interface.

---

# 6. Redator — reescritas e ortografia

Confirmei os fatos load-bearing no código: split aleatório (`random_state=42`, linha 499), MAE/coverage apenas logados (linhas 545-556), target-encoding fit só no treino (502-512), ITBI peso 2.0 (486), TIR por Newton (500-517), NPV usado só internamente dentro de `_calc_irr` (505) e não exposto como saída. Tenho tudo que preciso. Vou redigir as reescritas no formato da persona.

## Revisão de Redação

### Diagnóstico geral
O texto tem registro acadêmico razoável, mas comete três problemas de precisão técnica que a auditoria expôs: (1) lista algoritmos e indicadores que não estão de fato implementados (XGBoost, Gradient Boosting, VPL como saída), induzindo a banca a cobrar o que não existe; (2) descreve o viés de oferta-vs-transação como problema sem dizer que o sistema o ataca (ITBI ponderado) — desperdiçando a principal contribuição metodológica; (3) usa verbos de capacidade plena ("estima valores", "gerar recomendações") sem qualificar incerteza nem o estágio do RAG. As reescritas abaixo deflacionam os exageros e, simultaneamente, promovem ao texto pontos fortes reais subnotificados. Prolixidade ("transformar dados públicos dispersos" repetido em §1, §2 e §3) também é sinalizada.

### Reescritas propostas (trecho a trecho)

> ORIGINAL (§1, L15): "Os valores anunciados em portais imobiliários nem sempre representam os valores efetivamente praticados em transações reais, o que pode distorcer análises baseadas apenas em ofertas disponíveis ao público."
> SUGESTÃO: "Os valores anunciados em portais imobiliários nem sempre representam os valores efetivamente praticados em transações reais, o que pode distorcer análises baseadas apenas em ofertas — fenômeno associado ao viés de seleção do preço de oferta. Para mitigar essa distorção, a plataforma incorpora as transações registradas no ITBI municipal como referência de valor efetivamente praticado, atribuindo-lhes peso maior do que aos anúncios no treinamento do modelo de avaliação."
> POR QUÊ: precisão sem inflar — o texto descrevia o problema mas omitia que o sistema o resolve (`src/price_model.py:477-486`, ITBI com `sample_weight=2.0`). É a contribuição metodológica que diferencia de um AVM ingênuo; ancorá-la aqui antecipa a pergunta da banca.

> ORIGINAL (§1, L19): "Diferentemente de uma análise tradicional, baseada em planilhas estáticas e avaliações pontuais, a solução proposta busca combinar coleta automatizada de dados, modelos preditivos, indicadores de custo e simulações econômico-financeiras para gerar recomendações mais transparentes, explicáveis e reproduzíveis."
> SUGESTÃO: "Diferentemente da análise tradicional, baseada em planilhas estáticas e avaliações pontuais, o trabalho integra coleta automatizada de dados, modelos preditivos, indicadores de custo e simulações econômico-financeiras, de modo a tornar as estimativas mais rastreáveis, explicáveis e reproduzíveis."
> POR QUÊ: registro (remove "a solução proposta busca", tom de folder) e precisão — "gerar recomendações transparentes" vira "tornar estimativas rastreáveis e explicáveis", o que a explicabilidade via SHAP de fato sustenta (`src/price_model.py:561-580`).

> ORIGINAL (§1, L21): "O sistema coleta dados de diferentes fontes públicas e abertas, organiza essas informações em uma base estruturada, identifica oportunidades de terrenos, estima valores de mercado, considera custos referenciais de construção e simula cenários de viabilidade econômico-financeira."
> SUGESTÃO: "O sistema coleta dados de diferentes fontes públicas e abertas, organiza essas informações em uma base estruturada georreferenciada, identifica oportunidades de terrenos, estima faixas de valor de mercado com intervalos de incerteza, considera custos referenciais de construção e simula cenários de viabilidade econômico-financeira."
> POR QUÊ: precisão — "estima valores de mercado" sugere ponto único, mas o modelo é quantílico e produz faixa P10–P90 (`src/price_model.py:42, 522-559`). "Faixas de valor com intervalos de incerteza" é mais defensável e mais forte. "Base estruturada georreferenciada" reflete o PostGIS (`sql/042_postgis.sql`).

> ORIGINAL (§2, L32): "Entre os algoritmos utilizados em problemas de precificação e regressão, destacam-se árvores de decisão, Random Forest, Gradient Boosting, XGBoost e LightGBM. Esses modelos são adequados para problemas imobiliários porque conseguem capturar relações não lineares entre as variáveis e lidar com diferentes tipos de atributos, como características numéricas, categóricas e espaciais."
> SUGESTÃO: "Entre os algoritmos utilizados em problemas de precificação e regressão, destacam-se árvores de decisão e seus métodos de ensemble, como Random Forest, Gradient Boosting, XGBoost e LightGBM. Esses modelos são adequados para problemas imobiliários porque capturam relações não lineares entre as variáveis e lidam com atributos numéricos, categóricos e espaciais. Neste trabalho, a implementação utiliza o LightGBM como modelo principal e o Random Forest como alternativa de contingência (fallback), conforme detalhado na seção de construção do artefato."
> POR QUÊ: precisão sem inflar — XGBoost e Gradient Boosting são citados como referencial teórico, mas só LightGBM e RandomForest existem no código (`src/price_model.py:466, 134-147`). A frase final separa teoria de implementação e evita que a banca cobre demonstração de XGBoost.

> ORIGINAL (§2, L33): "O uso de regressão por quantis também se mostra relevante, pois permite estimar não apenas um valor único, mas intervalos de incerteza."
> SUGESTÃO: "O uso de regressão por quantis também se mostra relevante, pois permite estimar não apenas um valor central, mas intervalos de incerteza — neste trabalho, os quantis de 10% a 90%, ajustando um modelo independente por quantil e reordenando as previsões por linha para evitar cruzamento de quantis (quantile crossing)."
> POR QUÊ: precisão e força — descreve o que está de fato implementado (`src/price_model.py:42 QUANTILES`, guard contra crossing em `:621-623`). Citar a correção de crossing é boa prática que a banca valoriza.

> ORIGINAL (§2, L35): "Técnicas como SHAP permitem decompor a previsão de um modelo e indicar quais variáveis tiveram maior influência no resultado. Assim, a Inteligência Artificial deixa de funcionar como uma "caixa-preta" e passa a oferecer justificativas interpretáveis para apoiar a decisão humana."
> SUGESTÃO: "Técnicas como SHAP (SHapley Additive exPlanations) permitem decompor a previsão de um modelo e indicar quais variáveis tiveram maior influência no resultado. Na plataforma, esse mecanismo é aplicado sobre a estimativa central (quantil de 50%), com fallback para a importância global de variáveis quando a biblioteca não está disponível, gerando uma narrativa interpretável em linguagem natural para apoiar a decisão humana."
> POR QUÊ: precisão (define a sigla na 1ª ocorrência) e ancoragem — descreve o comportamento real, inclusive o fallback (`src/price_model.py:561-604`; narrativa PT-BR em `src/avm_explain.py:43-87`). Mais honesto do que afirmar SHAP incondicional.

> ORIGINAL (§2, L37): "Indicadores como Valor Geral de Vendas, custo total do empreendimento, margem esperada, Valor Presente Líquido, Taxa Interna de Retorno e prazo de retorno são utilizados para avaliar se um projeto é atrativo."
> SUGESTÃO: "Indicadores como Valor Geral de Vendas (VGV), custo total do empreendimento, margem esperada, Taxa Interna de Retorno (TIR) e prazo de retorno (payback) são utilizados para avaliar a atratividade de um projeto. O Valor Presente Líquido (VPL) é o fundamento do cálculo da TIR — a taxa que zera o VPL do fluxo de caixa do projeto."
> POR QUÊ: precisão sem inflar — o sistema calcula VGV, margem, ROI, TIR (por Newton) e payback, mas o VPL não é exposto como indicador de saída; ele só existe internamente dentro de `_calc_irr` (`src/viability.py:500-517`, NPV na linha 505). Reposicionar o VPL como base conceitual da TIR mantém o referencial teórico honesto sem prometer um indicador que a interface não entrega. Alternativa, se quiser manter o VPL na lista: expô-lo como saída no `viability.py`.

> ORIGINAL (§2, L39): "Entretanto, uma análise de viabilidade mais robusta não deve considerar apenas o custo atual, mas também a possibilidade de variação de preços ao longo do tempo, diferenças regionais e impactos sobre a margem do empreendimento."
> SUGESTÃO: "Entretanto, uma análise de viabilidade consistente não deve considerar apenas o custo atual, mas também a sensibilidade da margem a variações de custo. Neste trabalho, os custos são calibrados contra a base SINAPI e contra três projetos reais da BM3, e a simulação inclui análise de sensibilidade do custo de construção."
> POR QUÊ: registro ("mais robusta" → "consistente", evita o termo que a auditoria flagou como overclaim) e força — cita a calibração com dados primários reais (`src/viability.py:27-41`) e a sensibilidade já existente (SINAPI ±10%), pontos fortes subnotificados.

> ORIGINAL (§3, L49): "Para isso, o sistema busca transformar dados públicos dispersos em informações organizadas, permitindo avaliar se determinado terreno possui potencial para um empreendimento habitacional popular."
> SUGESTÃO: "Para isso, o sistema organiza dados públicos dispersos em uma base consultável, permitindo avaliar o potencial de um terreno para empreendimento habitacional popular."
> POR QUÊ: redundância — "transformar dados públicos dispersos em informações" já aparece em §1 (L17) e reaparece aqui; enxugar e remover "busca". É a repetição que a persona aponta como maior problema do texto.

> ORIGINAL (§3, L51): "Os canais de entrega incluem dashboard web, relatórios de viabilidade, alertas automatizados e bot de mensagens."
> SUGESTÃO: "Os canais de entrega incluem um painel web (dashboard), relatórios de viabilidade, alertas automatizados e um bot de mensagens com comandos para consulta de oportunidades, viabilidade e indicadores de mercado."
> POR QUÊ: precisão e força — todos verificados (`dashboard/`, `src/alerts.py:46-70`, `src/telegram_bot.py:167-194` com 12+ comandos). Detalhar o bot ancora a afirmação em evidência concreta.

> ORIGINAL (§3, L61): "...bancos de dados relacionais com extensão geoespacial, APIs públicas, ferramentas de visualização web e serviços de Inteligência Artificial em nuvem."
> SUGESTÃO: "...bancos de dados relacionais com extensão geoespacial (PostGIS), APIs públicas, ferramentas de visualização web e serviços de Inteligência Artificial em nuvem, empregados tanto na extração de dados (por exemplo, leitura do zoneamento do Plano Diretor a partir do PDF) quanto na geração de embeddings para indexação semântica."
> POR QUÊ: força ancorada em fato — zoning via Gemini + pdfplumber (`src/collectors/zoning_marilia.py:153`) e embeddings em produção (`src/embedder.py:62-71`). Sobre o RAG, ver a nota abaixo: descrever como infraestrutura, nunca como busca semântica disponível ao usuário.

> NOTA SOBRE RAG/BUSCA SEMÂNTICA (não há trecho a corrigir, mas evite introduzir): se for mencionar embeddings em qualquer ponto, use o fraseado: "infraestrutura de embeddings (text-embedding-004, 768 dimensões, pgvector) em produção, indexando anúncios e documentos municipais; a busca semântica está implementada como serviço, com integração à interface em andamento."
> POR QUÊ: a geração de embeddings roda em produção, mas `search_similar_listings` e `search_documents` (`src/embedder.py:244, 260`) não têm consumidor — recuperação não conectada. Anunciar "busca semântica" como recurso de produto convida a banca a pedir demonstração.

> ORIGINAL (§3, L65): "Como critérios de avaliação, poderão ser considerados a precisão dos modelos de estimativa, a qualidade dos dados coletados, a utilidade das recomendações geradas, a comparação entre análises tradicionais e análises apoiadas pela plataforma, além da validação por meio de casos reais da BM3."
> SUGESTÃO: "Como critérios de avaliação, serão considerados: o erro do modelo de estimativa (MAE, MAPE e RMSE do quantil central) e a cobertura observada dos intervalos de quantis frente ao valor nominal; a qualidade e a cobertura dos dados coletados; a comparação entre a análise tradicional do gestor e a análise apoiada pela plataforma; e a validação prospectiva com casos reais da BM3, cruzando as estimativas com os desfechos efetivamente realizados."
> POR QUÊ: precisão e rigor — substitui "precisão dos modelos" (vago) por métricas nomeadas. O código já calcula MAE e cobertura P25–P75 (`src/price_model.py:545-556`), e o loop de validação prospectiva existe (`feedback_loop.run_calibration`). Importante: o metodólogo recomenda gerar e tabular MAE/MAPE/cobertura atuais antes da defesa, pois hoje só são logados, não persistidos como tabela reportável.

### Glossário de termos a padronizar (sigla + extenso na 1ª ocorrência)
- AVM (Automated Valuation Model) — já definido em §2 L31; manter em itálico o termo em inglês.
- VGV (Valor Geral de Vendas) — definir na 1ª ocorrência (§2 L37).
- TIR (Taxa Interna de Retorno) — definir na 1ª ocorrência (§2 L37).
- VPL (Valor Presente Líquido) — definir na 1ª ocorrência; reposicionar como base da TIR, não como indicador de saída.
- SHAP (SHapley Additive exPlanations) — definir na 1ª ocorrência (§2 L35).
- SINAPI (Sistema Nacional de Pesquisa de Custos e Índices da Construção Civil) — definir na 1ª ocorrência (§2 L39).
- MCMV (Minha Casa Minha Vida) — usar a sigla após a 1ª menção por extenso (§1 L11).
- payback (prazo de retorno) — padronizar; em itálico por ser estrangeirismo.
- Estrangeirismos em itálico: *Automated Valuation Model*, *proptech*, *Big Data*, *dashboard*, *fallback*, *payback*, *quantile crossing*, *embeddings*, *pgvector*.

### Erros de ortografia/gramática encontrados
- Não foram encontrados erros de acentuação, crase ou concordância no draft atual. As aspas em "caixa-preta" (§2 L35) estão corretas; recomenda-se padronizar aspas tipográficas ("...") em todo o documento.
- Padronizar tempo verbal: o texto oscila entre "a solução proposta busca" (presente, tom de proposta) e descrição do que já foi construído. Recomendação: adotar voz impessoal e o presente para o artefato existente ("o sistema integra", "a plataforma estima"), reservando o futuro apenas para a avaliação ("serão considerados").

---
Observação de escopo (fora de redação, mas load-bearing para a defesa): o TCC não possui seção de Metodologia, apontada pelo metodólogo como a lacuna nº 1. Nenhuma reescrita acima a supre — é necessário redigir a seção (enquadramento DSR + estudo de caso, protocolo de avaliação com os dois experimentos propostos). Arquivo do TCC: `/Users/matheus.rezende/Documents/BM3/inteligencia-imobiliaria/docs/TCC_draft.md`.
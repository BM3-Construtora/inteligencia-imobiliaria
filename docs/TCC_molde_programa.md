# Molde do Programa MBA IA & Big Data (ICMC/USP) — Engenharia Reversa de 4 TCCs Aprovados

> Base: perfis estruturados de Camurça (SMS/BERT), Improta (TabNet), Favaro (Estoque/LSTM-SARIMA) e Faria (DeepVaR).
> Alvo: alinhar o rascunho do Matheus (`docs/TCC_draft.md` — MaríliaBot, IA imobiliária para viabilidade MCMV) ao padrão aprovado.

---

## 1. Molde do programa

Os quatro trabalhos vêm do mesmo programa (MBA em IA e Big Data, ICMC/USP São Carlos, todos 2023, todos abnTeX2/classe USPSC) e convergem para um **molde de "pesquisa aplicada experimental"** muito estável. Não é tese teórica nem plano de negócios: é a construção/avaliação de um artefato de ML com rigor metodológico declarado e honestidade nos resultados.

### 1.1 Estrutura e ordem das seções (padrão consolidado)

A ordem é praticamente idêntica nos quatro. O esqueleto canônico, com extensão típica:

| # | Seção | Função | Extensão típica |
|---|---|---|---|
| — | **Pré-textuais** (capa, folha de rosto, ficha catalográfica, dedicatória/agradecimentos, **Resumo**, **Abstract**, listas de figuras/tabelas, sumário) | Identificação institucional + ABNT | numeração romana; gerado pelo template |
| 1 | **Introdução** (contextualização / problema / inovação-proposta de solução / objetivos / organização do trabalho) | Abre o fio condutor: contexto → problema → solução → objetivo | 2–4 páginas |
| 2 | **Fundamentação Teórica / Revisão Bibliográfica** | Teoria dividida em eixos que **mapeiam 1:1 os componentes da solução** | 6–12 páginas (a maior seção) |
| 3 | **Panorama de mercado / Método / Desenvolvimento** (varia o rótulo — ver §2) | O elo teoria→prática: ora análise de negócio, ora descrição do método | 3–10 páginas |
| 4 | **Método / Avaliação Experimental / Resultados** | Execução com dados reais: pipeline instanciado + experimentos | 3–15 páginas (núcleo do mérito) |
| 5 | **Discussão e Análise de Resultados** (às vezes fundida em 4) | Tabela comparativa de métricas + leitura honesta | 1–3 páginas |
| 6 | **Conclusões** | Síntese, limitações assumidas, trabalhos futuros | 1–2 páginas |
| — | **Referências** (NBR 6023) | Pós-textual, sem número | 1–4 páginas (13 a 41 refs) |

Há duas "famílias" de organização interna dos capítulos 3–5 (ambas aprovadas):

- **Família A — "Construção de MVP / Método explícito"** (Camurça): Cap. 2 define a teoria do pipeline → Cap. 5 reinstancia *a mesma ordem* sobre dados reais → Cap. 6 discute resultados. Camurça insere ainda um capítulo de negócio (Canvas/Benchmark/SWOT) **antes** do método.
- **Família B — "Método separado de Resultados"** (Favaro, Improta, Faria): um capítulo descreve o método/pipeline ("como será feito", sem dados) e o capítulo seguinte é Resultados/Avaliação Experimental ("o que aconteceu, com dados"). Favaro é o exemplo mais limpo: Cap. 3 Desenvolvimento (método) ≠ Cap. 4 Resultados (execução).

> **O invariante por trás das duas famílias:** sempre existe **separação clara entre o "como" (método) e o "o quê aconteceu" (resultados medidos)**, e a metodologia abre com uma **figura-síntese do pipeline completo** (Improta Fig. 4; Favaro Figs. 1 e 4; Faria Algoritmo 1).

### 1.2 Normas ABNT efetivamente usadas

- **Citação (NBR 10520):** sistema **autor-data**. Duas variantes coexistindo no mesmo texto:
  - Parentética: `(SOBRENOME, ANO)` com sobrenome em **CAIXA ALTA** — `(DEVLIN et al., 2018)`, `(PARMEZAN; BATISTA, 2016)`. Múltiplos autores separados por **ponto-e-vírgula**; `et al.` para 4+ autores.
  - Narrativa: `Fama (1970) argumenta...` — sobrenome em caixa baixa, ano entre parênteses.
  - Citação longa (>3 linhas) em **bloco recuado**, fonte menor, fechando com `(SOBRENOME, ANO)`.
- **Referências (NBR 6023):** lista única `REFERÊNCIAS`, título centralizado, **ordem alfabética por sobrenome**, sem numeração. SOBRENOME maiúsculo + iniciais; **título da obra em negrito**; periódico/editora; URLs entre `<...>` com `Disponível em:` / `Acesso em:` (ou `Available at` / `Access at`). Geração automática por abnTeX2.
- **Numeração de seções (NBR 6024):** progressiva, até 3 níveis. Primários em **CAIXA ALTA e negrito** (`1 INTRODUÇÃO`); secundários em negrito (`2.3 Modelo TabNet`); terciários sem negrito (`3.1.1 Série temporal`). Pós-textuais sem número.
- **Figuras/Tabelas:** legenda **acima**, formato `Figura N – Descrição` (travessão), centralizada; **Fonte abaixo** — `Fonte: Autor` / `Fonte: Elaborado pelo autor (ano)` para autorais, `Fonte: (AUTOR, ANO)` para reproduzidas. ABNT distingue **Figura** (ilustração), **Tabela** (dados numéricos, bordas abertas/booktabs) e **Quadro** (texto/comparação qualitativa) — Favaro separa as três com listas independentes. **Equações numeradas à direita** `(2.1)`, `(2.2)`. **Listas de ilustrações pré-textuais** obrigatórias.
- **Resumo/Abstract:** RESUMO (PT) + ABSTRACT (EN) em páginas separadas, cada um abrindo com a **auto-referência bibliográfica do próprio trabalho** (`SOBRENOME, Iniciais. Título. ANO. Np. Monografia...`), parágrafo único (~10–25 linhas), **Palavras-chave/Keywords** ao final (4–8 termos; separador `.` ou `;`; em ordem alfabética).

### 1.3 Quantidade e tipo de referências

- **Faixa:** 13 a ~41 referências. O *centro de gravidade é 20–26*; só Camurça chega a ~40. **Quantidade não é critério de aprovação** — Faria aprovou com 13.
- **Composição:** forte predominância de **literatura técnica seminal em inglês** (papers, preprints arXiv, livros-texto clássicos com ISBN) + **fontes de mercado/documentação técnica web datadas** (`Disponível em` / `Acesso em` — blogs, McKinsey, docs de libs como scikit-learn, Hugging Face, colah.github.io). Poucas referências em português (1 a 5). Aceita-se `[S.l.: s.n.]` quando local/editora não identificados.
- **Padrão de ouro:** ancorar a teoria em **fontes primárias seminais** (Fama 1970, Vaswani 2017, Hochreiter 1997, Devlin 2018) e a motivação prática em **fontes de mercado recentes**.

### 1.4 Tom e voz

- **Impessoal e científico**, 3ª pessoa, voz passiva sintética: *"foi utilizada a API"*, *"optou-se por"*, *"foram treinados"*. Evita 1ª pessoa do singular; quando precisa referir o autor, usa `o executor do projeto`/`o autor`. (Improta e Faria deslizam pontualmente para 1ª pessoa do plural — *"abordamos", "nossos resultados"* — é tolerado mas inconsistente; evitar.)
- **Tempos verbais:** presente para teoria/definições (*"o BERT representa..."*); passado para método e resultados (*"foi aplicada a técnica SMOTE"*); futuro para anúncio de estrutura (*"neste capítulo será apresentado..."*).
- **Termos técnicos em inglês em itálico** (*fine-tuning, embeddings, stopwords, trade-off*); na primeira menção, **glosa entre parênteses** (Favaro: *"outliers (valor atípico)"*) — torna o texto legível para banca não-especialista.
- **Postura intelectual:** sobriedade nos achados. Os quatro **assumem limitações e resultados negativos/parciais** ancorados em literatura. Improta refuta a própria hipótese; Faria e Favaro reportam onde o modelo NÃO ganhou. **Honestidade > resultado bonito** é o traço mais premiado pela banca.

---

## 2. Variações aceitáveis vs. invariantes

### 2.1 Invariantes (norma rígida — todos seguem)

1. **Esqueleto Introdução → Fundamentação → Método → Resultados → Conclusão → Referências**, nessa ordem.
2. **Separação método (como) × resultados (o quê aconteceu, medido).**
3. **Pipeline/metodologia em etapas numeradas, aberto por uma figura-síntese autoral.**
4. **Comparação contra baseline(s) com métricas quantitativas fixas e tabeladas** (mesmo split, mesmas métricas para todos os cenários/modelos).
5. **Honestidade sobre limitações e resultados negativos**, ancorada em literatura.
6. ABNT: autor-data (10520), referências (6023), numeração progressiva (6024), figuras com fonte, equações numeradas.
7. **Resumo + Abstract** com auto-referência bibliográfica e palavras-chave.
8. **Tom impessoal**; presente p/ teoria, passado p/ método/resultados.
9. **Fundamentação teórica em eixos que mapeiam 1:1 os componentes da solução** (sem teoria solta).
10. **Quantificação/rastreabilidade dos dados** em cada etapa (volume coletado → após limpeza → cobertura %).

### 2.2 Variações aceitáveis (escolha do autor)

| Dimensão | Variação observada |
|---|---|
| **Rótulo do capítulo de método** | "Método de Pesquisa – Construção do MVP" (Camurça) · "Metodologia" (Improta, Faria) · "Desenvolvimento" (Favaro) |
| **Família organizacional** | A (teoria→reinstanciação, Camurça) vs. B (método≠resultados, os outros 3) |
| **Capítulo de negócio** | Camurça insere Canvas+Benchmark+SWOT como capítulo próprio; os outros 3 **não têm** análise de mercado formal |
| **Extensão total** | 20 (Faria) a 31 (Camurça) páginas de conteúdo — tudo aprovado |
| **Nº de referências** | 13 a ~41 |
| **Figura vs. Tabela vs. Quadro** | Improta usa **só figuras** (prints de DataFrame como figura); Favaro separa rigorosamente Figura/Tabela/Quadro; Faria separa Tabela/Gráfico/Algoritmo |
| **Framework metodológico nomeado** | Favaro nomeia KDD (Rezende 2003); os outros 3 **não nomeiam** framework, só descrevem etapas |
| **Formalização** | Faria usa **pseudocódigo (Algoritmo 1)** + equações; Camurça/Improta não |
| **Pequenas inconsistências ABNT** | toleradas (Faria: ponto irregular após número de capítulo; "33f." vs "52f."; Improta/Faria 1ª pessoa plural) — **não bloqueiam aprovação** |

> **Leitura para o Matheus:** o capítulo de mercado (Canvas/Benchmark/SWOT) é **opcional** no programa — só Camurça o tem. Mas como o rascunho do Matheus já o tem e é um MBA, mantê-lo é uma escolha legítima **desde que subordinado aos Resultados, não como espinha dorsal** (alinhado ao parecer do orientador na revisão v1).

---

## 3. O TCC do Improta (TabNet) como espelho

Improta é o espelho mais próximo do Matheus: **ML aplicado a um domínio econômico-financeiro, combinando fontes de dados heterogêneas (série temporal estruturada + texto/sentimento), com rotulagem via LLM (GPT-3.5) e comparação de cenários**. É o molde a copiar.

### 3.1 Como Improta estrutura a METODOLOGIA (Cap. 3) — copiar

Abre com **uma figura-síntese** (`Figura 4 – Representação gráfica da metodologia proposta`) que dá o mapa inteiro antes de detalhar. Depois, **4 etapas processuais numeradas**:

1. **3.1 Obtenção e pré-processamento dos dados** — subdividido por fonte: `3.1.1 Série temporal` (coleta B3, 7.174.800 registros → recorte 5 ativos), `3.1.2 Notícias` (scraping Infomoney via Selenium, 1001 registros, rotulagem de sentimento via GPT-3.5).
2. **3.2 Junção dos dados** — normalização para variáveis derivadas (`tendencia_st` 0/1, `sentimento_news` -1/0/1), reorganização em janela deslizante de 5 dias.
3. **3.3 Preenchimento dos dados ausentes** (a etapa que justifica a arquitetura escolhida — TabNet para imputação).
4. **3.4 Treinamento e utilização do modelo.**

**Cada transformação de dado é mostrada com print real (DataFrame) legendado como figura** (Figs. 5–18), com numeração sequencial e fonte abaixo. E **quantifica a perda/cobertura em cada passo** (1001 → 642 → 598 notícias; 63,7% dos pregões com notícia; 341 ausentes preenchidos).

### 3.2 Como Improta estrutura os RESULTADOS (Cap. 4) — copiar

**Avaliação Experimental** desenhada como **comparação controlada de cenários**:

- **4.1 Conjuntos de Dados** — dataset final exato (939 registros de série + 598 notícias VALE3).
- **4.2 Configuração Experimental** — `4.2.1 Cenário 1` (só série temporal) vs. `4.2.2 Cenário 2` (série + sentimento). **Mesmo split 80/20 (747 treino/187 teste), mesmos 6 regressores, mesmas 4 métricas (MSE, RMSE, MAE, R²)** nos dois cenários.
- **4.3 Resultados e Discussões** — tabela/figura comparando a variação percentual entre cenários, concluindo (honestamente) que **o sentimento NÃO melhora a predição** — e ancorando o resultado negativo em literatura seminal (Fama 1970, Das & Chen 2007, Tetlock 2007).

### 3.3 O que o Matheus deve copiar de Improta — checklist direto

1. **Abrir a Metodologia com uma figura-síntese autoral** do pipeline completo do MaríliaBot: `Coleta (habite-se / obras públicas / parcelamento de solo / ITBI / IBGE) → normalização+deduplicação → AVM quantílico + SHAP → simulação VGV/TIR → recomendação no Telegram` — legendada `Figura N – Representação gráfica da metodologia proposta. Fonte: Autor`.
2. **Quebrar a Metodologia em etapas numeradas** com subseções por fonte de dado (espelhando 3.1.1/3.1.2 de Improta → uma subseção por coletor).
3. **Mostrar cada transformação com print/tabela real** legendada como figura/tabela, com numeração sequencial.
4. **Quantificar cobertura e perdas em cada etapa** (ex.: `X imóveis coletados → Y após dedupe → Z% com CEP/geocoding → W com transação ITBI`) — é o que dá credibilidade e auditabilidade, exatamente como os 63,7% de Improta.
5. **Desenhar a avaliação como comparação de cenários/baselines com métricas fixas:** Cenário 1 = baseline (preço médio por m² do setor IBGE) vs. Cenário 2 = AVM completo — **mesmas métricas (MAE, MAPE, RMSE) sobre o mesmo conjunto-teste** (no caso, transações ITBI como *ground truth*).
6. **Assumir o resultado negativo/parcial** onde a IA não ganha, ancorado em literatura — postura que aprovou Improta mesmo com hipótese refutada.

---

## 4. Tabela comparativa: rascunho do Matheus × molde

Rascunho atual (`TCC_draft.md`): seção 1 Introdução · seção 2 Fundamentação Teórica e Estado da Arte · seção 3 Panorama de Mercado, Investimentos e Resultados Esperados. **Não há Metodologia nem Resultados medidos.** É essencialmente a "primeira metade" do molde (Introdução + Fundamentação + Negócio), no formato de Camurça mas parando antes do método.

| Seção do molde | O que o Matheus tem | O que falta | Ação concreta |
|---|---|---|---|
| **Pré-textuais (Resumo/Abstract, listas, sumário, ficha)** | Nada | Tudo | Gerar via template abnTeX2/USPSC. Escrever Resumo+Abstract com auto-referência e 5–7 palavras-chave (ex.: *Inteligência Artificial; AVM; Dados Imobiliários; Habitação Popular; Marília-SP; Viabilidade*). |
| **1 Introdução** | Forte: contexto (construção civil/MCMV) → problema (incerteza na escolha de terreno, dados fragmentados, *anúncio ≠ transação*) → motivação (BM3) → inovação (MaríliaBot) → objetivo geral | (a) **objetivos específicos mensuráveis** em bullets (como os 4 objetivos de Improta); (b) **pergunta de pesquisa** explícita; (c) subseção **1.x Organização do trabalho** | Adicionar `1.4 Objetivos` (geral + 3–5 específicos) e `1.5 Organização do trabalho`. Trocar "desenvolver **e analisar**" por objetivo com critério de avaliação. |
| **2 Fundamentação Teórica** | Madura e bate com o código: Construção 4.0, AVM, algoritmos (RF/XGBoost/LightGBM), regressão quantílica, SHAP, viabilidade (VGV/VPL/TIR), SINAPI, estado da arte proptech | (a) **eixos numerados** mapeando 1:1 os componentes; (b) **citações autor-data** (hoje zero citações no texto); (c) **trabalhos relacionados** + tabela comparativa de lacuna (estilo Favaro Tabela 1); (d) seção dedicada justificando a **escolha da arquitetura** (estilo 2.3 TabNet) | Reestruturar em `2.1 Construção 4.0 e decisão de investimento` · `2.2 AVM e modelos de precificação (RF/GBM/quantílica)` · `2.3 Explicabilidade (SHAP)` · `2.4 Viabilidade econômico-financeira (VGV/TIR/VPL)` · `2.5 Engenharia de custos (SINAPI)` · `2.6 Trabalhos relacionados + Tabela comparativa`. **Inserir (SOBRENOME, ANO) em cada afirmação teórica.** |
| **3 Panorama de mercado / Negócio** | Completo: proposta de valor, Canvas, benchmarking (Urbit/DataZap/Hiperdados/Locates), SWOT, MVP, investimentos | Está bem para o estilo Camurça, mas hoje **ocupa o lugar de Resultados** e mistura "resultados **esperados**" | Manter como capítulo de negócio **subordinado**, renomear para remover "Resultados Esperados". Transformar benchmarking em **tabela comparativa** com colunas (`usa dados públicos municipais?`, `hiperlocal?`, `AVM com viés controlado?`, `simula viabilidade MCMV?`). |
| **4 Metodologia** | **Ausente** | Todo o capítulo — o item que a banca usa para classificar o trabalho | **Escrever do zero (P0).** Abrir com figura-síntese do pipeline; etapas numeradas: `4.1 Coleta (subseção por coletor)` · `4.2 Normalização e deduplicação` · `4.3 Geocoding e centroides econômicos` · `4.4 AVM quantílico (com ITBI ground truth peso 2.0)` · `4.5 SHAP` · `4.6 Simulação de viabilidade (VGV/TIR por Newton)`. Quantificar cobertura por etapa. |
| **5 Resultados / Avaliação Experimental** | **Ausente** (só "resultados esperados") | Todo o capítulo com **números reais** | **Escrever do zero (P0).** Experimento A: backtest do AVM contra ITBI, baseline = preço médio/m² do setor IBGE, métricas MAE/MAPE/RMSE em tabela. Experimento B (escala reduzida e honesta): reprodução *ex-post* do caso Casa 1 BM3 (margem real 24%) + 2 casas paradas como contra-exemplo, rotulado como evidência de caso. |
| **5/6 Discussão honesta** | Parcial (SWOT cobre forças/fraquezas, mas sem dados) | Leitura honesta de limitações **medidas** | Discutir leakage residual (`neigh_avg`), N=1, conflito de interesse (autor é da BM3), gaps de dados (CMDU, Plano Diretor 2026) — como Favaro discutiu o R²<40%. |
| **6 Conclusões** | **Ausente** | Síntese + limitações + trabalhos futuros | Escrever fechando o fio condutor problema→objetivo→resultado; assumir trade-offs (orçamento R$500k, solução pragmática). |
| **Referências** | **Ausente** (zero) | 20–30 referências NBR 6023 | Compilar: seminais (AVM, gradient boosting/XGBoost, SHAP-Lundberg 2017, regressão quantílica-Koenker), SINAPI/Caixa, normas (Plano Diretor Marília, LGPD), docs de libs (LightGBM, pgvector, LangChain) com `Disponível em`/`Acesso em`. |
| **Tom/voz/ABNT** | Texto corrido, impessoal, sem citações, sem figuras | Citações, figuras com fonte, equações numeradas, glosa de termos | Inserir citações; adicionar figuras autorais `Fonte: Autor`; formalizar AVM/TIR em equações numeradas; glosar termos (*embeddings, AVM, pgvector*) na 1ª menção. |

**Diagnóstico de uma linha:** o rascunho tem Introdução + Fundamentação + Negócio fortes (a metade "fácil" do molde) e **falta exatamente o núcleo que dá mérito acadêmico** — Metodologia, Resultados medidos e Conclusões — que no caso do Matheus **já existem no código e só precisam ser transpostos para o texto** (consistente com o parecer da revisão v1).

---

## 5. Esqueleto-alvo do TCC do Matheus

Sumário proposto no formato do programa (Família B — método separado de resultados, espelhando Improta/Favaro, com o capítulo de negócio de Camurça subordinado). Alvo total: **~28–32 páginas de conteúdo** (dentro da faixa aprovada de 20–31).

```
ELEMENTOS PRÉ-TEXTUAIS
  Capa · Folha de rosto · Ficha catalográfica · Dedicatória/Agradecimentos
  RESUMO (PT) + palavras-chave        — 1 p.
  ABSTRACT (EN) + keywords            — 1 p.
  Listas de Figuras / Tabelas / Quadros / Siglas · Sumário

1  INTRODUÇÃO                                                    [3–4 p.]
   1.1 Contextualização (construção civil, déficit habitacional, MCMV)
   1.2 Problema de pesquisa (incerteza na escolha do terreno; anúncio ≠ transação)
   1.3 Inovação e proposta de solução (MaríliaBot)
   1.4 Objetivos (geral + 4 específicos mensuráveis, em bullets)
   1.5 Organização do trabalho

2  FUNDAMENTAÇÃO TEÓRICA E ESTADO DA ARTE                        [8–10 p.]
   2.1 Construção 4.0 e decisão de investimento imobiliário
   2.2 Avaliação automatizada de imóveis — AVM e modelos de precificação
       2.2.1 Modelos de árvore (Random Forest, Gradient Boosting, XGBoost/LightGBM)
       2.2.2 Regressão por quantis e intervalos de incerteza
   2.3 Explicabilidade de modelos (SHAP)
   2.4 Viabilidade econômico-financeira (VGV, VPL, TIR) no contexto MCMV
   2.5 Engenharia de custos e bases de referência (SINAPI)
   2.6 Trabalhos relacionados e posicionamento (Tabela comparativa de lacuna)

3  PANORAMA DE MERCADO E PROPOSTA DE VALOR                       [3–4 p.]
   3.1 Mercado-alvo e proposta de valor (PME incorporadoras, cidades médias)
   3.2 Business Model Canvas
   3.3 Benchmarking tecnológico (Tabela: Urbit/DataZap/Hiperdados/Locates × MaríliaBot)
   3.4 Análise SWOT da aplicação de IA/Big Data

4  METODOLOGIA — CONSTRUÇÃO DA PLATAFORMA MARÍLIABOT             [7–9 p.]
   [abre com Figura N – Representação gráfica da metodologia proposta. Fonte: Autor]
   4.1 Visão geral do pipeline (figura-síntese)
   4.2 Coleta de dados públicos
       4.2.1 Habite-se / obras públicas / parcelamento de solo (Marília)
       4.2.2 Transações (ITBI) como ground truth
       4.2.3 Dados urbanísticos e socioeconômicos (IBGE, setores censitários)
   4.3 Normalização, deduplicação e geocoding (+ 5 centroides econômicos)
   4.4 Modelo de avaliação (AVM quantílico; ITBI peso 2.0; target-encoding sem leakage)
   4.5 Explicabilidade com SHAP
   4.6 Simulação de viabilidade (VGV / TIR por Newton / score MCMV Caixa)
       [formalizar em equações numeradas + pseudocódigo, estilo Faria Algoritmo 1]
   4.7 Entrega da decisão (interface MaríliaBot / Telegram)

5  AVALIAÇÃO EXPERIMENTAL E RESULTADOS                           [5–7 p.]
   5.1 Conjunto de dados (volumes, cobertura por etapa, % com ITBI)
   5.2 Configuração experimental
       5.2.1 Cenário 1 — baseline (preço médio/m² do setor IBGE)
       5.2.2 Cenário 2 — AVM completo do MaríliaBot
   5.3 Resultados (Tabela: MAE/MAPE/RMSE por cenário) e validação de caso BM3
   5.4 Discussão (leakage residual, N=1, conflito de interesse, gaps de dados — honesta)

6  CONCLUSÕES                                                    [1–2 p.]
   Síntese problema→objetivo→resultado · limitações assumidas · trabalhos futuros
   (CMDU, Plano Diretor 2026, validação prospectiva, LGPD)

REFERÊNCIAS  (NBR 6023, alfabética, ~20–30 entradas)            [2–3 p.]
```

### Notas de execução do esqueleto

- **Família B escolhida** porque o Matheus precisa de Metodologia e Resultados *separados* — exatamente onde o rascunho está vazio — e porque Improta (o espelho mais fiel) usa essa família.
- **Capítulo 3 (negócio) mantido mas subordinado:** vem *antes* do método (como em Camurça), porém o eixo do mérito é Cap. 4–5. Remover "Resultados Esperados" do título — resultados agora são reais e ficam no Cap. 5.
- **Prioridade de escrita:** P0 = Caps. 4, 5, 6 + objetivos específicos (1.4) + Referências. P1 = citações na Fundamentação, figuras autorais, equações, Resumo/Abstract. O Cap. 3 já está praticamente escrito no rascunho.
- **Meta de páginas conservadora:** densidade técnica + honestidade > volume. Faria aprovou com 20 páginas; não inflar.
```

---

## 6. Três espelhos próximos (turmas 2023–2024) — lições específicas

Análise de mais 3 TCCs aprovados do mesmo programa, escolhidos por proximidade ao caso do Matheus. Cada um cobre uma lacuna que os 4 primeiros não cobriam. **Importante:** os três são tecnicamente mais simples que o MaríliaBot — servem como *piso aprovável* e como molde retórico, não como teto técnico. O Cérebro V2 está naturalmente acima desse piso; a tarefa é escrever com o mesmo rigor narrativo e a mesma honestidade.

### 6.1 Barazetti — *árvores de decisão para score de crédito* → GÊMEO METODOLÓGICO DO AVM

Experimento comparativo de modelos de árvore (Decision Tree, Random Forest, XGBoost) em dados tabulares, balanceado/desbalanceado, tuning, métricas comparadas. É o template direto do capítulo do AVM.

1. **Metodologia = pipeline em subseções numeradas**, na ordem real de execução: Ferramentas → Dataset → EDA/pré-processamento → Seleção de features → Validação cruzada → Balanceamento → Hiperparâmetros → Treino. Figura-síntese (fluxograma) consolidando o fluxo, `Fonte: O Autor`.
2. **Resultados separam APRESENTAÇÃO de INTERPRETAÇÃO**: primeiro as tabelas de números, depois uma seção dedicada de análise, fatiada por cenário experimental.
3. **Tabela comparativa Modelo × métrica × condição, com baseline explícito** (vírgula decimal, 4 casas). Para o AVM: LightGBM quantílico vs. baseline (preço médio/m² do setor) na mesma tabela, mesmas métricas (MAE, RMSE, **pinball loss por quantil**, cobertura dos intervalos).
4. **Declarar split + CV ancorado em citação** (ele cita Hastie para k=5) e dizer que transformações dependentes de dado são ajustadas só no treino (anti-leakage) — exatamente o ponto frágil do `neigh_avg` apontado na revisão v1.
5. **Reportar os hiperparâmetros SELECIONADOS, não só o espaço de busca** (corrige a falha dele).
6. **Honestidade sobre resultado contraintuitivo** (no caso dele, SMOTE piorou — e ele reporta e explica).
7. **Ângulo competitivo do SHAP:** este gênero PROMETE interpretabilidade e quase nunca entrega (Barazetti prometeu e não mostrou feature importance nem regras). O SHAP do Matheus é a entrega concreta — posicionar como "da interpretabilidade prometida à explicabilidade demonstrada".

### 6.2 Armando — *previsão de faturamento de franquia (estudo de caso)* → ENQUADRAMENTO DO N=1 (BM3)

Estudo de caso de empresa única com aplicação de negócio — exatamente o enquadramento que protege a BM3.

1. **Cravar "estudo de caso" no título e repetir no objetivo** ("Este estudo de caso tem como objetivo…").
2. **Declarar tipo e método em quadros-ficha-técnica**: Tipo (abordagem mista; procedimento = pesquisa bibliográfica + estudo de caso) e Método (hipotético-dedutivo; procedimento monográfico). Forma limpa e à prova de banca, sem precisar de jargão de Yin.
3. **Neutralizar o N=1 rebaixando a promessa**: "não pretende um modelo universal/perfeito; o propósito é orientar os tomadores de decisão da BM3". Contribuição declarada como decisória/local + limitação assumida na Conclusão.
4. **Dados privados — tripé**: confidencialidade declarada + janela temporal/contagem precisa + **código público** (repo/Colab) sem expor a base bruta.
5. **Critério de sucesso de negócio definido a priori** e resultado julgado contra ele (ele: "MAE 8,7%, dentro dos 10% aceitos pela empresa"). Converte métrica técnica em valor validado pelo cliente — combinar com a Casa 1 da BM3.
6. **Contexto da empresa como subseção de abertura** amarrando empresa→problema. (Mas ir mais fundo que ele: a conexão negócio↔técnica é o núcleo do Matheus.)
- *Anti-padrões a evitar dele:* 4 referências (quase todas blog); Resultados de 1 parágrafo; sem baseline comparativo.

### 6.3 Antelo — *identificação de oportunidades B2B* → ESPELHO DO HUNTER (scoring de oportunidades)

1. **Nomear explicitamente o tipo de problema de ML.** Ele = classificação multinomial; o hunter do Matheus = **scoring/ranking multicritério** — declarar e justificar (já o posiciona acima).
2. **Decompor o pipeline em fases nomeadas (A→B→C):** coleta dos dados de terrenos → engenharia dos ~10 critérios → cálculo do score → ranking/decisão.
3. **Documentar a origem dos critérios via conhecimento de especialista** (literatura imobiliária + experiência BM3) e pôr a **tabela de critérios com pesos em apêndice**.
4. **Ancorar resultados em KPIs de negócio + baseline + funil quantificado** (ele: 3500→900→271→3→1, +75% vs. manual). Para o hunter: nº de terrenos triados → top-N que viram análise → aderência validada pela família BM3.
5. **Validação human-in-the-loop em cadeia** (score do modelo → revisão do especialista → rótulo final). Resolve a ausência de ground-truth.
6. **Tratar a coleta (collectors municipais) como objeto acadêmico** — fundamentar scraping com referências, nomear ferramentas, documentar limites de cobertura/frequência honestamente.
7. **Usar métricas de ranking que ele não usou (diferencial):** precision@k / hit-rate dos top-N terrenos, validados por especialista.

### 6.4 Síntese dos espelhos — onde o Matheus já está acima do piso aprovável

| Componente | Piso aprovado pelos espelhos | Onde o Matheus supera |
|---|---|---|
| AVM | árvores + métricas simples (acurácia) | LightGBM quantílico, intervalos, **ITBI ground truth peso 2.0**, baseline de bairro, pinball loss |
| Explicabilidade | prometida, não entregue (Barazetti) | **SHAP efetivamente demonstrado** por feature/caso |
| Estudo de caso | declaração funcional + N=1 rebaixado (Armando) | dados primários reais (Casa 1, casas paradas) + critério de aceite |
| Scoring | classificação + acurácia 58% (Antelo) | scoring multicritério + ranking + KPIs de negócio |

A lição transversal: **o programa aprova trabalhos aplicados com baseline modesto, desde que bem narrados e honestos sobre limites.** O sistema do Matheus é mais forte tecnicamente — o risco nunca foi a substância, é a transposição para o texto no rigor e na honestidade desses espelhos.

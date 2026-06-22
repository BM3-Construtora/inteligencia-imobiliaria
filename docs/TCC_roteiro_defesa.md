# Roteiro de Defesa — TCC MaríliaBot (MBA IA & Big Data, ICMC/USP)

> Preparação para a arguição. Baseado no estado honesto atual do trabalho
> (AVM real avaliado, ITBI=0 declarado, Exp B qualitativo). Estude as respostas
> em voz alta — o objetivo é entrar sabendo exatamente onde o trabalho é forte e
> onde é vulnerável, sem ser pego de surpresa.

---

## 1. Postura geral (4 regras)

1. **Honestidade é o seu trunfo, não a sua fraqueza.** Improta foi aprovado refutando a própria hipótese. Nunca esconda um número ruim — apresente-o antes que perguntem e explique o porquê. A banca pune quem disfarça, não quem assume.
2. **Separe sempre "ganho relativo" de "nível absoluto".** Seu resultado robusto é *o AVM bate o baseline*. O número absoluto (MAPE ~82%) é honestamente modesto — sempre que ele aparecer, reposicione: "o que demonstro é viabilidade arquitetural e ganho sobre o baseline, não precisão de avaliação profissional".
3. **Você construiu um sistema real, em produção.** A maioria dos TCCs aprovados são protótipos. Lembre a banca disso quando couber: "isto roda diariamente há meses".
4. **Não invente.** Se não souber um número, diga "não tenho esse dado consolidado, está no rol de trabalhos futuros". É melhor que chutar e ser desmentido.

---

## 2. Abertura (30 segundos — decore)

> "Pequenas incorporadoras de habitação popular decidem onde comprar terreno e o
> que construir com base em intuição e em preço de anúncio — que não é o preço de
> venda. No caso da BM3, isso resultou em duas casas paradas. Construí o MaríliaBot:
> uma plataforma que coleta dados públicos dispersos, estima o valor do terreno com
> intervalo de incerteza explicável, e simula a viabilidade do empreendimento sob o
> MCMV — transformando uma decisão de centenas de milhares de reais, hoje intuitiva,
> em um processo auditável e reproduzível."

## 3. Estrutura da apresentação (~10 min)

| Tempo | Bloco | Mensagem-chave |
|---|---|---|
| 0–1 min | Problema | Anúncio ≠ transação; a viabilidade se decide *antes* da obra; caso BM3 |
| 1–2 min | Objetivo | Reduzir incerteza na decisão de terreno MCMV, comprovando na BM3 |
| 2–4 min | Fundamentação | Construção 4.0, AVM, regressão quantílica, SHAP, viabilidade — e a lacuna hiperlocal |
| 4–7 min | Metodologia | Estudo de caso (Yin); **mostrar a Figura 1** (pipeline); destacar ITBI como ground truth de projeto e a explicabilidade SHAP |
| 7–9 min | Resultados | Tabela AVM × baseline (MAPE 81,7% vs 129,6%); **assumir** as limitações de frente |
| 9–10 min | Conclusão | Viabilidade arquitetural comprovada + ganho relativo; trabalhos futuros |

**Dica:** gaste mais tempo em Metodologia e Resultados (é onde o mérito é avaliado), menos em mercado/Canvas (é o que parece "plano de negócios").

---

## 4. Banco de perguntas e respostas

Formato: **P** (pergunta) · *sondando* · **R** (resposta falável) · ⚠️ (evite).

### Bloco A — Validação e acurácia (o mais provável)

**P: "Qual o erro do seu AVM e contra o que você comparou?"**
*Sondando: se há métrica e baseline.*
**R:** "MAPE de 81,7%, média de cinco divisões treino-teste, contra um baseline de preço médio por metro quadrado do bairro, que dá 129,6%. O AVM reduz o erro pela metade, e o MAE cai de R$ 1,99 milhão para R$ 502 mil. Reporto média e desvio, não um split único, justamente para mostrar a variância."
⚠️ Não diga que o modelo "é preciso". Diga que "supera consistentemente o baseline".

**P: "MAPE de 82% é altíssimo. Você compraria um terreno com base nisso?"** *(a mais dura)*
*Sondando: se você confunde ganho relativo com utilidade decisória.*
**R:** "Sozinho, não — e o trabalho não afirma isso. O AVM não entrega um número de compra: entrega uma *faixa* P25–P75 e um *argumento* via SHAP, para apoiar um decisor humano. O valor da plataforma não está só no AVM, está em três camadas: triar terrenos e sinais off-market que ninguém cruza, comunicar a incerteza honestamente, e encadear até a viabilidade. O número absoluto reflete a dificuldade real do problema — terreno tem preço por metro quadrado muito heterogêneo — e a amostra pequena. O que demonstro é o ganho relativo e a viabilidade da arquitetura, não precisão de avaliação profissional, que assumo como fronteira a vencer com mais dados."
⚠️ Não fique na defensiva nem minimize o 82%. Assuma e reposicione.

**P: "n=41 no teste, cobertura 43%. Isso é estatisticamente significativo ou é ruído?"**
*Sondando: maturidade estatística.*
**R:** "Com 41 terrenos, as métricas são instáveis — e o desvio que reporto (±25 pontos no MAPE) é, ele próprio, um resultado: mostra a instabilidade. Por isso a conclusão robusta é o ganho *relativo* sobre o baseline, consistente nas cinco divisões, e não o valor absoluto. A amostra é pequena porque terrenos anunciados são escassos: 205 de quase 20 mil imóveis — o que é o próprio argumento da opacidade do mercado que o trabalho ataca."

### Bloco B — O ITBI (vão perguntar)

**P: "Você fala em ITBI como verdade-fundamento, mas a Tabela 1 mostra zero. Treina em quê?"**
*Sondando: coerência entre método e dado.*
**R:** "Treino em preços de oferta — e declaro isso explicitamente na Tabela 1 e nas seções 1.3 e 4.3.1. O ITBI é a verdade-fundamento *de arquitetura*: o coletor e a ponderação com peso dobrado já estão implementados; o que falta é o *acesso*, que em Marília depende de solicitação via Lei de Acesso à Informação. É uma limitação de dado, não de método — quando o ITBI entrar, a calibração ativa sem mudar o pipeline. Preferi declarar isso abertamente a fingir que o dado existe."
⚠️ Nunca diga que o modelo "é calibrado com ITBI" no presente. É "projetado para".

### Bloco C — Estudo de caso, N=1 e conflito de interesse

**P: "Uma cidade, uma empresa — e você é dela. Isso é ciência ou consultoria interna?"**
*Sondando: se o viés foi tratado.*
**R:** "É um estudo de caso aplicado, no sentido de Yin — enquadramento legítimo para construção e avaliação de um artefato, e declarado na seção 4.1. O vínculo com a BM3 é assumido explicitamente; a mitigação é objetiva, não baseada na minha percepção: avalio o modelo contra um baseline fixo e adversarial e por métricas de erro absolutas. O objetivo declarado não é validade universal, é reduzir a incerteza na BM3. O que se transfere a outras cidades é o *método*, não os dados."

**P: "Como você generaliza a partir de um caso?"**
**R:** "Não generalizo os resultados — generalizo o método. O pipeline é replicável a qualquer cidade média; a calibração é local. Trato a validade externa limitada como limitação explícita, não a escondo."

**P: "A BM3 definiu o critério de aceite do Experimento B. Não é a régua ajustada para passar?"**
**R:** "O critério de negócio é definido *antes* de ver o resultado e o baseline é fixo, não escolhido para favorecer o modelo. Reconheço que isso precisa estar documentado — e o Experimento B completo, com os números das três casas, está no rol de trabalho imediato; nesta versão ele é qualitativo, e eu o apresento como tal."

### Bloco D — Originalidade e mercado

**P: "Já existem Urbit, DataZap, Hiperdados. O que você fez de novo?"**
*Sondando: contribuição.*
**R:** "Não é o algoritmo — LightGBM e SHAP são commodity. É a combinação que nenhum concorrente cobre junto: coleta hiperlocal incluindo sinais *off-market* (alvará, EIV, IPTU, inventário), que um player nacional não compensa raspar para uma cidade do interior; viabilidade MCMV calibrada com dados reais; e intervalo de preço com explicação em português. A barreira de entrada é a economia de atenção do incumbente, não a tecnologia — os grandes ignoram o nicho porque, para eles, o custo de cobrir Marília supera a receita."

**P: "Isso é um TCC ou o pitch de um produto?"**
**R:** "O eixo do trabalho é o artefato e sua avaliação metodológica — Metodologia e Resultados são o centro. A análise de mercado entra subordinada, como aplicação gerencial, não como espinha dorsal."

### Bloco E — Dados, legalidade e técnica

**P: "Você raspa devedores de IPTU e inventários — dados pessoais. Qual a base legal sob a LGPD?"**
*Sondando: responsabilidade jurídica.*
**R:** "Seção 4.9. São dados de origem pública e oficial — diário oficial e portais de transparência. A base legal é o legítimo interesse, com minimização, pseudonimização por hash, registro de auditoria, e acordo de tratamento de dados no processamento por modelo de linguagem. Reconheço que o uso de sinal de dívida ou inventário exige um teste de proporcionalidade documentado, que está nos cuidados do projeto."
⚠️ Não banalize ("é tudo público"). Mostre que conhece a exigência do teste de proporcionalidade.

**P: "Split aleatório em dado com dimensão temporal não infla as métricas?"**
**R:** "Pode inflar, e declaro isso na seção 5.4. Já corrigi o vazamento do preço médio de bairro — na avaliação ele é calculado só sobre o treino. O que falta é a divisão por data, o backtesting, que está como trabalho futuro. Mas como o baseline sofre o mesmo viés, o ganho relativo entre eles é mais confiável que o nível absoluto."

**P: "Uma plataforma inteira para precificar 205 terrenos? Um corretor experiente conhece esses de cabeça."**
**R:** "O valor não está só nos 205 que estão anunciados hoje — está em antecipar os que ainda não foram. Um alvará ou EIV aparece no diário oficial 18 a 36 meses antes do imóvel chegar ao mercado. O sistema cruza o que nenhum corretor cruza e enxerga o terreno antes do anúncio."

**P: "A calibração financeira da TIR vem de quantos projetos?"**
**R:** "Três, e declaro isso como premissa de especialista, não estimativa estatística, na seção 4.7. São parâmetros versionados e auditáveis — BDI, buffer de retrabalho, custo de capital —, não um modelo aprendido. É transparência paramétrica, não generalização."

### Bloco F — Método (perguntas de enquadramento)

**P: "Qual é a sua metodologia?"**
**R:** "Pesquisa aplicada, abordagem quali-quantitativa, conduzida como estudo de caso único da BM3, com construção e avaliação de um artefato. O tipo e o método estão nos Quadros 3 e 4. A unidade de análise é o terreno ou oportunidade de empreendimento MCMV em Marília. A avaliação se dá por dois experimentos: o A, backtest do AVM contra baseline; o B, reprodução de casos reais da BM3."

**P: "Por que LightGBM e não rede neural / outro modelo?"**
**R:** "Dados tabulares de tamanho pequeno a médio, com mistura de variáveis numéricas, categóricas e espaciais — cenário em que gradient boosting domina e supera redes neurais, conforme a literatura. E o LightGBM, com regressão por quantis, entrega o intervalo de incerteza, que é central para a decisão. Tenho fallback para Random Forest."

---

## 5. Frases-âncora (repita quando encurralado)

- "O resultado robusto é o ganho relativo sobre o baseline, não o nível absoluto."
- "Declaro essa limitação explicitamente na seção X."
- "É uma limitação de dado, não de método."
- "O que se transfere é o método, não os dados."
- "Isto roda em produção há meses, não é um protótipo."

## 6. As 3 que mais doem — tenha a resposta na ponta da língua

1. **"MAPE 82% serve para decidir?"** → faixa + argumento + decisor humano; ganho relativo; uma camada, não o oráculo.
2. **"ITBI é zero — então o ground truth não existe."** → de arquitetura, pronto, falta acesso (LAI); declarado.
3. **"Experimento B não tem números."** → qualitativo nesta versão, assumido; reprodução completa é trabalho imediato; tenho a margem real da Casa 1 (24%) e o contra-exemplo das paradas.

## 7. Checklist na véspera

- [ ] Preencher orientador, ficha catalográfica e nome completo
- [ ] Atualizar o Sumário no Word
- [ ] Reler as seções 4.3.1, 5.2, 5.4 (onde estão as limitações — é de lá que vêm as perguntas)
- [ ] Decorar a abertura de 30 segundos e os números: 81,7% vs 129,6%, 205 terrenos, 5 divisões
- [ ] Ensaiar as 3 perguntas que mais doem em voz alta

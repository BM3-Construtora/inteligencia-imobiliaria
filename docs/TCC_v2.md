# TCC v2 — texto integral (extraído de docs/TCC_modelo_negocio.docx)

UNIVERSIDADE DE SÃO PAULO

INSTITUTO DE CIÊNCIAS MATEMÁTICAS E DE COMPUTAÇÃO

MBA EM INTELIGÊNCIA ARTIFICIAL E BIG DATA

Matheus Rezende

Plataforma de Inteligência Imobiliária com Inteligência Artificial para Análise de Viabilidade de Empreendimentos de Habitação Popular (MCMV): um estudo de caso

São Carlos

2026

Matheus Rezende

Plataforma de Inteligência Imobiliária com Inteligência Artificial para Análise de Viabilidade de Empreendimentos de Habitação Popular (MCMV): um estudo de caso

Trabalho de Conclusão de Curso apresentado ao Instituto de Ciências Matemáticas e de Computação da Universidade de São Paulo – ICMC/USP, como parte dos requisitos para obtenção do título de Especialista em Inteligência Artificial e Big Data.

Área de concentração: Inteligência Artificial

Orientador(a): [PREENCHER: Prof. Dr. Nome do Orientador]

São Carlos

2026

[PREENCHER: ficha catalográfica elaborada pela Biblioteca Prof. Achille Bassi, ICMC/USP, com os dados fornecidos pelo autor.]

RESUMO

REZENDE, M. Plataforma de Inteligência Imobiliária com Inteligência Artificial para Análise de Viabilidade de Empreendimentos de Habitação Popular (MCMV): um estudo de caso. 2026. Monografia (MBA em Inteligência Artificial e Big Data) – Instituto de Ciências Matemáticas e de Computação, Universidade de São Paulo, São Carlos, 2026.

A decisão de aquisição de terrenos para empreendimentos de habitação popular do programa Minha Casa Minha Vida (MCMV) é tomada, em pequenas e médias incorporadoras, sob forte incerteza e com base em informação dispersa e em preços de anúncio, que divergem dos valores efetivamente transacionados. Este trabalho apresenta o MaríliaBot, uma plataforma de inteligência imobiliária que integra dados públicos imobiliários, urbanísticos e construtivos para apoiar a análise de viabilidade de terrenos em Marília-SP. Adotando a abordagem de estudo de caso aplicado à construtora BM3, o sistema coleta dados de múltiplas fontes públicas, estima o valor de mercado por meio de um modelo de avaliação automatizada (AVM) baseado em regressão por quantis (LightGBM), tendo as transações de ITBI como verdade-fundamento de projeto, explica suas previsões com valores SHAP e simula a viabilidade econômico-financeira (VGV, TIR e payback) sob as faixas do MCMV. Os resultados, avaliados contra um baseline de preço médio por metro quadrado, indicam que o AVM supera consistentemente o baseline e que a plataforma torna o processo de avaliação auditável e reproduzível, a custo operacional marginal, demonstrando a aplicabilidade da Construção 4.0 fora dos grandes centros urbanos, ainda que a precisão absoluta permaneça limitada pelo tamanho da amostra e pela indisponibilidade atual de transações.

Palavras-chave: Inteligência Artificial. Avaliação Automatizada de Imóveis. Habitação Popular. Viabilidade Econômico-Financeira. Dados Públicos.

ABSTRACT

In small and medium real estate developers, the decision to acquire land for affordable housing projects under the Minha Casa Minha Vida (MCMV) program is made under strong uncertainty, based on scattered information and on listing prices that diverge from actual transaction values. This work presents MaríliaBot, a real estate intelligence platform that integrates public real estate, urban and construction data to support land feasibility analysis in Marília, Brazil. Adopting a case study approach applied to the BM3 construction company, the system collects data from multiple public sources, estimates market value through an Automated Valuation Model (AVM) based on quantile regression (LightGBM), designed to use property transfer tax (ITBI) transactions as ground truth, explains its predictions using SHAP values, and simulates the economic and financial feasibility (gross sales value, IRR and payback) under the MCMV income brackets. The results, evaluated against a price-per-square-meter baseline, indicate that the AVM consistently outperforms the baseline and that the platform makes the valuation process auditable and reproducible at marginal operating cost, demonstrating the applicability of Construction 4.0 beyond major urban centers.

Keywords: Artificial Intelligence. Automated Valuation Model. Affordable Housing. Economic-Financial Feasibility. Public Data.

SUMÁRIO

Atualize o sumário no Word: clique com o botão direito > Atualizar campo.


## 1 INTRODUÇÃO


### 1.1 Contextualização e problema

A construção civil é um dos pilares da economia brasileira, responsável por parcela relevante do PIB e por geração massiva de empregos. Paradoxalmente, é também um dos setores menos digitalizados e mais expostos a incertezas de custo, prazo e decisão de investimento. No segmento de habitação popular — em especial nos empreendimentos vinculados ao programa Minha Casa Minha Vida (MCMV), relançado pela Lei nº 14.620/2023 (BRASIL, 2023) — essas incertezas deixam de ser um incômodo gerencial e passam a ameaçar a própria viabilidade do negócio: as margens são comprimidas por tetos de venda definidos por portaria governamental, e qualquer erro de estimativa consome diretamente o lucro do empreendedor.

O problema, porém, antecede a obra. Antes de orçar um custo de construção, o pequeno e médio incorporador precisa responder a três perguntas que hoje são respondidas pela intuição: onde comprar o terreno, o que construir nele e quando lançar. Erra-se em qualquer uma delas e o resultado é o que motivou este trabalho — o caso concreto da construtora BM3, em Marília-SP, que manteve duas casas paradas aguardando comprador. O diagnóstico não foi falta de capacidade construtiva, e sim desalinhamento entre produto e mercado, somado a uma decisão de investimento tomada sem dados.

Esse desalinhamento tem raiz informacional. O mercado imobiliário local é, por natureza, opaco. O preço que importa — o de venda efetivamente fechada — não é público: os portais anunciam preço pedido, que costuma divergir do realizado. Informações de zoneamento, alvarás, loteamentos em aprovação, inventários e dívidas que pressionam vendedores existem, mas estão dispersas em diários oficiais, cartórios e sistemas municipais que ninguém cruza. Soma-se a isso a dependência da orçamentação tradicional — planilhas estáticas e composições fixas — que fotografa o custo no presente e ignora a inflação setorial que ocorrerá ao longo dos meses de execução.

Dados oficiais confirmam a materialidade do risco. O Índice Nacional de Custo da Construção (INCC/FGV) acumulou, em períodos recentes, variações superiores à inflação geral (FUNDAÇÃO GETULIO VARGAS, 2024), pressionando orçamentos previamente fechados. O Sistema Nacional de Pesquisa de Custos e Índices da Construção Civil (SINAPI), mantido por Caixa Econômica Federal e IBGE, evidencia diferenças expressivas de preço de insumos e serviços entre estados e municípios (CAIXA ECONÔMICA FEDERAL, 2024), o que inviabiliza generalizar estimativas. Para um incorporador de uma única cidade do interior, com capital de giro limitado, essa volatilidade não é abstração macroeconômica — é a diferença entre um empreendimento que fecha no azul e outro que trava capital.


### 1.2 Justificativa

A relevância do tema decorre da combinação entre o peso socioeconômico da habitação popular e a escassez de instrumentos analíticos acessíveis a incorporadoras de menor porte. Enquanto grandes incorporadoras de capitais contam com áreas de inteligência de mercado, o incorporador do interior decide sobre ativos de centenas de milhares de reais com base em experiência e planilhas. Reduzir essa assimetria com dados públicos e Inteligência Artificial tem, portanto, impacto direto sobre a eficiência da alocação de capital e sobre a oferta de moradia. Academicamente, o trabalho contribui ao demonstrar, em um caso real, a aplicação integrada de avaliação automatizada, explicabilidade e simulação de viabilidade a um mercado hiperlocal — recorte pouco explorado pela literatura, concentrada em grandes centros.


### 1.3 Proposta de solução

A inovação deste trabalho não está em inventar um novo algoritmo de aprendizado de máquina, e sim em aplicar a Construção 4.0 ao processo decisório do incorporador hiperlocal, construindo um ativo que o mercado não oferece: uma base de dados proprietária, cumulativa e cruzada, que transforma dados públicos dispersos em vantagem informacional para quem decide. A solução é o MaríliaBot, uma plataforma de inteligência imobiliária já em operação — não um protótipo conceitual. Diariamente, um pipeline automatizado coleta as fontes, normaliza e deduplica os imóveis, enriquece os dados com IA, pontua oportunidades, simula a viabilidade de cada terreno sob as faixas do MCMV e entrega o resultado por um dashboard interativo e por um bot de mensagens.

Três características diferenciam a proposta das soluções existentes. Primeiro, a coleta própria e off-market: em vez de comprar dados de terceiros, o sistema coleta diretamente de dezenas de fontes — portais imobiliários, mas também sinais que antecedem o mercado, como alvarás de construção e Estudos de Impacto de Vizinhança publicados no Diário Oficial Municipal. Segundo, a verdade-fundamento real: o modelo de avaliação é projetado para se calibrar com transações de ITBI — preço registrado em cartório —, corrigindo o viés de sobrevivência de treinar uma IA apenas em anúncios; registra-se que, na base atual, tais transações ainda não estão disponíveis (Seção 5.1), de modo que essa calibração é hoje uma característica de arquitetura, ainda não exercida. Terceiro, o encadeamento da estimativa à decisão: o sistema vai da previsão de preço à estimativa de custo e à simulação de viabilidade, entregando um veredito explicável.


### 1.4 Objetivos

O objetivo geral deste trabalho é desenvolver e avaliar uma plataforma de inteligência imobiliária baseada em Inteligência Artificial para apoiar a decisão de investimento em empreendimentos de habitação popular, comparando a recomendação do sistema com abordagens tradicionais em casos reais da construtora BM3, em Marília-SP. Como objetivos específicos, o trabalho se propõe a:

- Estruturar um pipeline de coleta e integração de dados públicos imobiliários, urbanísticos e de transações (ITBI) para o município de Marília-SP;
- Desenvolver um modelo de avaliação automatizada de imóveis (AVM) por regressão de quantis, calibrado com transações reais, e avaliá-lo contra um baseline por meio de métricas de erro e de cobertura dos intervalos de incerteza;
- Prover explicabilidade às estimativas por meio de valores SHAP, traduzindo cada previsão em fatores compreensíveis ao decisor;
- Implementar e parametrizar um simulador de viabilidade econômico-financeira (VGV, TIR e payback) aderente às faixas do MCMV;
- Validar a utilidade decisória da plataforma reproduzindo casos reais da BM3 e discutindo limitações e condições de transferibilidade do método.

### 1.5 Estrutura do trabalho

Além desta introdução, o trabalho está organizado em cinco capítulos. O Capítulo 2 apresenta a fundamentação teórica e o estado da arte. O Capítulo 3 discute o panorama de mercado e a proposta de valor. O Capítulo 4 descreve a metodologia, detalhando o enquadramento da pesquisa e a construção da plataforma. O Capítulo 5 apresenta os resultados e a discussão. O Capítulo 6 traz as conclusões, limitações e trabalhos futuros.


## 2 FUNDAMENTAÇÃO TEÓRICA E ESTADO DA ARTE

Este capítulo apresenta os fundamentos que sustentam a proposta e o estado da arte — na literatura acadêmica e nas soluções comerciais — situando o MaríliaBot frente ao que já se faz.


### 2.1 Construção 4.0 e a digitalização do setor

O conceito de Indústria 4.0 designa a quarta revolução industrial, caracterizada pela integração de sistemas ciberfísicos, Internet das Coisas, computação em nuvem, Big Data e Inteligência Artificial, com o objetivo de criar fábricas inteligentes capazes de automação avançada e decisão descentralizada. Setores como a manufatura adotaram esses paradigmas rapidamente; a construção civil, ao contrário, manteve-se historicamente lenta na digitalização, convivendo com produtividade estagnada e desperdício (OESTERREICH; TEUTEBERG, 2016). A transição para a chamada Construção 4.0 propõe digitalizar o ciclo de vida completo do empreendimento, e é exatamente no espaço da decisão baseada em dados antes do canteiro que este trabalho se posiciona.


### 2.2 Os limites do método tradicional

Na engenharia de custos, a orçamentação tradicional baseia-se em uma abordagem paramétrica e estática: multiplicam-se os quantitativos do projeto pelas composições de custo unitário, tendo o SINAPI como referência — cujo uso é exigido pelo Decreto nº 7.983/2013 para obras com recursos federais (BRASIL, 2013). O método é consagrado, mas estritamente determinístico: projeta o custo sobre preços do presente e ignora a dinâmica inflacionária do período de execução. O mesmo problema de fotografia estática afeta a avaliação do imóvel: o método tradicional de avaliação por comparação (ABNT, 2011) depende de comparáveis escassos e, sobretudo, de preços pedidos, não realizados. A consequência é dupla — subestima-se a incerteza e ignora-se o viés de sobrevivência embutido nos anúncios.


### 2.3 Aprendizado de máquina aplicado à precificação

O aprendizado de máquina (Machine Learning) emprega algoritmos que aprendem padrões a partir de dados históricos, permitindo prever valores em dados novos. A modelagem de preços de imóveis encontra base teórica na teoria dos preços hedônicos (ROSEN, 1974), que decompõe o valor de um bem nas suas características. Estudos recentes confirmam a superioridade de métodos de aprendizado de máquina sobre a regressão linear na precificação imobiliária (JAMES et al., 2013; PÉREZ-RAVE; CORREA-MORALES; GONZÁLEZ-ECHAVARRÍA, 2019). Para problemas de regressão, as arquiteturas mais relevantes para este trabalho são:

- Árvores de decisão e Random Forest, técnica de ensemble que agrega múltiplas árvores independentes, reduzindo o sobreajuste (BREIMAN, 2001);
- Gradient Boosting, em que árvores são treinadas sequencialmente para corrigir os resíduos das anteriores, com as implementações XGBoost (CHEN; GUESTRIN, 2016) e LightGBM (KE et al., 2017), esta última o algoritmo central deste trabalho;
- Regressão por quantis (KOENKER; BASSETT, 1978), que, em vez de um único valor, estima percentis (P10, P25, P50, P75, P90), entregando ao incorporador um intervalo de incerteza, e não um número de falsa precisão.

### 2.4 Explicabilidade de modelos

Um ponto que distingue uma ferramenta acadêmica de uma ferramenta de decisão real é a explicabilidade. Modelos de ensemble são, por padrão, caixas-pretas. Para que um incorporador confie a ponto de investir capital, a recomendação precisa ser auditável — exigência da literatura de aprendizado de máquina interpretável (MOLNAR, 2022). A técnica SHAP (SHapley Additive exPlanations), derivada da teoria dos jogos cooperativos, decompõe cada previsão na contribuição individual de cada variável (LUNDBERG; LEE, 2017) — permitindo afirmar, por exemplo, que um terreno está abaixo do esperado porque está próximo de escola e em bairro com obra pública recente, apesar da topografia em aclive. A previsão deixa de ser oráculo e passa a ser argumento.


### 2.5 Dados públicos e o problema do ground truth

A disponibilidade crescente de dados abertos governamentais — séries do SINAPI, microdados do IBGE, portais municipais de transparência — cria um ecossistema favorável à ciência de dados aplicada (INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA, 2023), sem necessidade de dados proprietários caros. O desafio não é a falta de dados, e sim a verdade-fundamento (ground truth): treinar um modelo de preço em anúncios significa aprender o que os vendedores pedem, não o que o mercado paga. A literatura de avaliação automatizada reconhece o uso de registros de transação como padrão-ouro para corrigir esse viés (KOK; KOPONEN; MARTÍNEZ-BARBOSA, 2017). No Brasil, a fonte equivalente é o ITBI, cujo valor declarado aproxima o preço real de venda — adotado neste trabalho como alvo de calibração ponderado.


### 2.6 Viabilidade econômico-financeira

A ponte entre a previsão e a decisão é a análise de viabilidade. Os indicadores consagrados são o Valor Presente Líquido (VPL) — soma dos fluxos de caixa descontados a uma taxa mínima de atratividade — e a Taxa Interna de Retorno (TIR), taxa que zera o VPL, complementados por margem líquida, payback e Valor Geral de Vendas (VGV). Em habitação popular, esses indicadores precisam respeitar os tetos de venda e as faixas de renda do MCMV (BRASIL, 2023), o que torna a simulação multicenário parte integrante da decisão, e não um anexo.


### 2.7 Métricas de validação

A confiabilidade de um modelo preditivo depende de validação estatística rigorosa. Adotam-se métricas consagradas (HASTIE; TIBSHIRANI; FRIEDMAN, 2009): o MAPE (erro percentual absoluto médio), de fácil interpretação gerencial; o RMSE (raiz do erro quadrático médio), que penaliza erros de grande magnitude; e o R² (coeficiente de determinação). Para a regressão por quantis, acrescentam-se a perda pinball, métrica própria de cada quantil, e a cobertura do intervalo — proporção de casos reais que caem dentro da faixa prevista —, que afere se a incerteza declarada é honesta.


### 2.8 Estado da arte: soluções existentes

Comercialmente, o mercado brasileiro de proptech para análise de terrenos e viabilidade já conta com players relevantes, cada um com forças e lacunas claras frente à proposta hiperlocal deste trabalho.

Quadro 1 – Comparativo de soluções de proptech frente ao MaríliaBot

Fonte: Elaborado pelo autor (2026).

O quadro revela uma posição de mercado rara: nenhum concorrente cruza, simultaneamente, dados on-market, off-market, leilão, IPTU, inventário e alvará municipal de forma nativa para uma cidade do interior paulista. A vantagem não é tecnológica de ruptura — é de posicionamento e profundidade de dados em um nicho que os grandes ignoram por baixa atratividade econômica unitária.


## 3 PANORAMA DE MERCADO E PROPOSTA DE VALOR


### 3.1 Análise de mercado

O mercado endereçável precisa ser lido em camadas. O mercado total (TAM) é o conjunto de incorporadoras e investidores imobiliários do Brasil que tomam decisões de aquisição de terreno — dezenas de milhares de empresas. O mercado servível (SAM) é o recorte de pequenos e médios incorporadores de habitação popular em cidades do interior, historicamente desatendidos pelas proptechs enterprise, que priorizam capitais. O mercado obtível inicial (SOM) é Marília-SP e municípios vizinhos de porte semelhante, onde a profundidade de dados hiperlocais constitui barreira de entrada. O déficit habitacional brasileiro, estimado em milhões de moradias pela Fundação João Pinheiro (2023), sustenta estruturalmente a demanda por empreendimentos do MCMV.

O insight estratégico é que a opacidade do mercado — usualmente vista como problema — é a fonte de valor. Em mercados opacos, quem detém mais informação captura mais valor, e esse ativo se acumula com o tempo. O alvo não é competir com os grandes players nas capitais, mas dominar nichos que eles nunca atenderão porque, para eles, o custo de cobertura supera a receita potencial unitária da cidade.


### 3.2 Business Model Canvas

Quadro 2 – Business Model Canvas da plataforma

Fonte: Elaborado pelo autor (2026).

O ponto notável do Canvas é a assimetria entre custo e valor: a estrutura de custos é de ordem de dezenas de reais por mês, enquanto cada decisão correta apoiada pela ferramenta movimenta centenas de milhares de reais em um único empreendimento.


### 3.3 Análise SWOT

Forças. Base de dados proprietária e cumulativa (vantagem temporal); coleta off-market que nenhum concorrente replica no nicho; custo operacional baixíssimo; explicabilidade (SHAP) que gera confiança para decisão de capital; produto já em produção, validado em caso real.

Fraquezas. Dependência de fontes públicas sujeitas a mudança de formato ou bloqueio; calibração ainda em maturação; volume de transações reais ainda limitado, dependente da liberação de ITBI via Lei de Acesso à Informação.

Oportunidades. Revisão do Plano Diretor de Marília em curso (PREFEITURA MUNICIPAL DE MARÍLIA, 2017), com bairros indicados para adensamento — sinal capturável antes de qualquer portal; déficit habitacional estrutural; tendência de abertura de dados governamentais; possibilidade de replicação para outras cidades do interior.

Ameaças. Risco regulatório quanto ao uso de dados pessoais, mitigado por conformidade com a LGPD (BRASIL, 2018); entrada de um grande player no interior (improvável pela economia unitária); mudança nas regras do MCMV, mitigada por premissas versionadas em banco de dados.


## 4 METODOLOGIA

Este capítulo descreve a metodologia do trabalho. A primeira seção caracteriza a pesquisa; as seguintes detalham a construção da plataforma, organizada como um pipeline de etapas, e o protocolo de avaliação.


### 4.1 Caracterização da pesquisa

Quanto à natureza, esta é uma pesquisa aplicada; quanto à abordagem, quali-quantitativa; quanto aos fins, exploratória e descritiva; e quanto aos meios, conduzida como estudo de caso único (YIN, 2015) aplicado à construtora BM3, em Marília-SP, com elementos de pesquisa de desenvolvimento, uma vez que o trabalho constrói e avalia um artefato computacional. Os quadros a seguir sintetizam o enquadramento metodológico.

Quadro 3 – Tipo de pesquisa

Fonte: Elaborado pelo autor (2026).

Quadro 4 – Método de pesquisa

Fonte: Elaborado pelo autor (2026).

Declara-se que o autor atua na construtora BM3, objeto do estudo de caso. Tal vínculo, característico de pesquisas aplicadas e de pesquisa-ação, é assumido explicitamente como condição do estudo; a mitigação do viés decorrente dá-se pela avaliação do artefato contra critérios objetivos (métricas de erro e baseline) e por dados de transação independentes (ITBI), e não apenas pela percepção do autor. O trabalho não pretende um modelo de validade universal; seu propósito é reduzir a incerteza e apoiar a decisão no contexto da BM3, discutindo, ao final, as condições de transferibilidade do método a outros municípios.


### 4.2 Visão geral do pipeline

A plataforma é estruturada como um pipeline automatizado, executado diariamente, que parte da coleta de dados públicos e termina na entrega de uma recomendação explicável. A Figura 1 sintetiza o fluxo completo, detalhado nas seções seguintes.

Figura 1 – Representação gráfica da metodologia proposta (pipeline do MaríliaBot)

Fonte: Elaborado pelo autor (2026).


### 4.3 Coleta de dados públicos

A coleta é realizada por componentes especializados (coletores), que herdam uma estrutura comum e gravam os registros em uma base relacional. As fontes distribuem-se em três grupos, conforme o Quadro 5.

Quadro 5 – Fontes de dados por grupo

Fonte: Elaborado pelo autor (2026).


#### 4.3.1 Transações (ITBI) como verdade-fundamento

As transações de ITBI são a verdade-fundamento prevista para o modelo: por refletirem o preço efetivamente registrado em cartório, devem ser ponderadas com peso superior ao das listagens de oferta no treinamento, mitigando o viés de sobrevivência. Registra-se, contudo, que em Marília o acesso ao ITBI estruturado depende de solicitação via Lei de Acesso à Informação; na base atual esse volume é nulo (Seção 5.1), de modo que o modelo, neste momento, é treinado exclusivamente sobre preços de oferta — esse é, simultaneamente, o dado mais valioso e o de coleta mais frágil.


### 4.4 Normalização, deduplicação e geocodificação

Os registros brutos passam por normalização (padronização de campos, unidades e endereços) e por deduplicação cross-portal, que identifica o mesmo imóvel anunciado em fontes distintas por meio de impressão digital sensível a atributos de terreno. Em seguida, cada imóvel é geocodificado e enriquecido com variáveis espaciais, entre elas a distância a cinco centroides econômicos de Marília (comercial, saúde, educação, industrial e histórico) e um escore de acessibilidade aos critérios do MCMV.


### 4.5 Modelo de avaliação automatizada (AVM)

O AVM é um modelo de regressão por quantis implementado com LightGBM, treinado de forma independente para os quantis 0,10, 0,25, 0,50, 0,75 e 0,90, com Random Forest como alternativa de contingência. O conjunto de atributos combina área, preço médio do bairro, distâncias aos centroides econômicos, escore de acessibilidade MCMV, indicadores de demanda e sinais de obras públicas e loteamentos no entorno. A codificação por alvo (target encoding) do bairro é ajustada exclusivamente sobre o conjunto de treino, para evitar vazamento de informação. O conjunto é dividido em treino e teste na proporção de 80% e 20%; discute-se, no Capítulo 5, a limitação do uso de divisão aleatória em dados com dimensão temporal.

Cada quantilizador é otimizado pela perda pinball, definida na Equação 1, em que y é o valor observado, ŷ a previsão e τ o quantil-alvo:

L_τ(y, ŷ) = max[ τ (y − ŷ), (τ − 1)(y − ŷ) ]		(1)

A combinação dos quantis fornece, para cada imóvel, uma faixa de valor (por exemplo, P25 a P75) em vez de um número único, comunicando a incerteza ao decisor.


### 4.6 Explicabilidade com SHAP

Sobre o quantil central (P50), aplicam-se valores SHAP (LUNDBERG; LEE, 2017) para decompor cada previsão na contribuição de cada atributo. As cinco variáveis de maior contribuição são traduzidas em linguagem natural e apresentadas ao usuário, convertendo a estimativa em um argumento auditável. Na ausência da biblioteca de cálculo, o sistema recorre à importância global de atributos como alternativa.


### 4.7 Simulação de viabilidade econômico-financeira

A partir da estimativa de preço e do custo de construção (derivado do SINAPI), o simulador calcula, para cada faixa do MCMV, o VGV, a margem, o ROI, a Taxa Interna de Retorno e o payback. A TIR é obtida numericamente pelo método de Newton, como a taxa que anula o Valor Presente Líquido do fluxo de caixa (Equação 2), em que CF_t é o fluxo no período t e r a taxa:

VPL = Σ_t  CF_t / (1 + r)^t  = 0		(2)

Os parâmetros do simulador (BDI, fator de eficiência construtiva, buffer de retrabalho, custo de capital de giro) foram calibrados a partir de três projetos reais da BM3 — um ciclo completo e duas obras paradas. Trata-se de uma calibração baseada em conhecimento de especialista com amostra pequena, e não de estimativa estatística, condição assumida como limitação.


### 4.8 Protocolo de avaliação

A avaliação do artefato segue dois experimentos. O Experimento A mede o desempenho preditivo do AVM: o modelo é comparado a um baseline ingênuo (preço médio por metro quadrado do setor) sobre o mesmo conjunto de teste, reportando MAE, MAPE, RMSE, perda pinball por quantil e cobertura dos intervalos. O Experimento B avalia a utilidade decisória reproduzindo, de forma retrospectiva, casos reais da BM3 — comparando a recomendação que o sistema teria emitido com o desfecho efetivamente observado. Define-se, com a BM3, um critério de aceitação de negócio (erro máximo tolerado pela empresa) contra o qual o resultado é julgado.


### 4.9 Aspectos éticos e conformidade com a LGPD

Parte das fontes contém dados pessoais (por exemplo, devedores de IPTU e inventariados). O tratamento observa a Lei Geral de Proteção de Dados (BRASIL, 2018): distingue-se dado aberto de dado pessoal, adota-se a hipótese de legítimo interesse, aplicam-se minimização e pseudonimização (hash de identificadores) e registro de auditoria, e respeitam-se os termos de uso das fontes. O processamento de dados pessoais por modelos de linguagem é feito em ambiente com acordo de tratamento de dados, evitando exposição desnecessária.


## 5 RESULTADOS E DISCUSSÃO

Este capítulo apresenta os resultados dos dois experimentos e a discussão crítica das limitações. Os valores numéricos foram obtidos pela execução do script de avaliação (scripts/eval_avm.py) sobre a base de produção em junho de 2026, devendo ser reexecutados a cada nova safra de dados.


### 5.1 Conjunto de dados

Após a execução do pipeline, o conjunto consolidado é descrito por seus volumes em cada etapa, evidenciando a cobertura e as perdas do processo, conforme a Tabela 1.

Tabela 1 – Cobertura do conjunto de dados (base de produção, jun. 2026)

Fonte: Elaborado pelo autor (2026).

Embora a base reúna 19.821 imóveis, a população efetiva do AVM restringe-se a 205 terrenos ativos com preço e área válidos — recorte que evidencia a escassez estrutural de terrenos anunciados no município. Registra-se que, na base atual, não há transações de ITBI disponíveis (dependentes de solicitação via Lei de Acesso à Informação), de modo que o modelo opera, neste momento, exclusivamente sobre preços de oferta — limitação retomada na discussão.


### 5.2 Desempenho do modelo de avaliação (Experimento A)

A Tabela 2 compara o AVM por quantis ao baseline de preço médio por metro quadrado, sobre o mesmo conjunto de teste. Reportam-se as métricas de erro do quantil central e a cobertura observada dos intervalos.

Tabela 2 – Desempenho do AVM frente ao baseline (média ± desvio em 5 divisões; n_teste ≈ 41)

Fonte: Elaborado pelo autor (2026), via scripts/eval_avm.py (preço médio do bairro ajustado só no treino).

Discussão. Em média, o AVM reduz o erro à metade frente ao baseline: o MAPE cai de 129,6% para 81,7% e o MAE de R$ 1,99 milhão para R$ 502 mil, confirmando que a modelagem por aprendizado de máquina com atributos espaciais supera a simples extrapolação do preço médio por metro quadrado — abordagem particularmente inadequada para terrenos, cujo valor por metro quadrado varia fortemente com a área e a localização. Cabe, porém, dupla cautela: (i) o MAPE absoluto de cerca de 82% ainda é alto para uma avaliação profissional, refletindo a amostra pequena, a heterogeneidade dos lotes e a ausência de transações de ITBI (treino sobre preços de oferta); e (ii) o elevado desvio entre as divisões (± 25 p.p. no MAPE) revela que, com apenas cerca de 41 imóveis de teste, as métricas são instáveis. Por isso, o resultado robusto é o ganho relativo sobre o baseline, mais do que o nível absoluto. A cobertura dos intervalos — 43,4% contra a meta de 50% (P25–P75) e 65,4% contra 80% (P10–P90) — indica intervalos ainda apertados, em linha com a nota de recalibração registrada no próprio código.


### 5.3 Utilidade decisória: casos da BM3 (Experimento B)

A avaliação da utilidade decisória apoia-se em três casos reais da BM3: a primeira casa (Santa Antonieta), concluída e vendida com margem real de aproximadamente 24%, e duas casas (Santa Clara) que permaneceram paradas por desalinhamento entre produto e mercado. Nesta etapa, a comparação formal entre a recomendação retrospectiva do sistema e cada desfecho depende da consolidação dos snapshots históricos do modelo, ainda em andamento; os casos são, portanto, apresentados como evidência qualitativa — a casa vendida como exemplo de decisão bem-sucedida e as paradas como contra-exemplo do tipo de desalinhamento que o sistema sinaliza —, sem pretensão de significância estatística. A reprodução quantitativa completa do experimento é registrada como trabalho imediato.


### 5.4 Discussão geral e limitações

Os resultados sustentam que o AVM supera consistentemente o baseline e que a plataforma torna o processo de avaliação auditável, mas algumas limitações devem ser explicitadas. Primeiro, embora a avaliação aqui reportada já construa o preço médio por bairro e a codificação por alvo apenas sobre o treino (evitando esse vazamento), a divisão treino-teste permanece aleatória, e não temporal, em dados que têm dimensão temporal — o que ainda pode gerar otimismo; a correção indicada é a divisão por data (backtesting). Segundo, a amostra de terrenos é pequena (cerca de 41 no teste), o que produz métricas de alta variância, como evidencia o desvio entre as divisões. Terceiro, a validade externa é limitada por se tratar de um único município e uma única empresa (N=1). Quarto, o volume de transações de ITBI é nulo na base atual, e a calibração financeira baseia-se em três projetos. Essas limitações não invalidam a contribuição, mas delimitam o escopo das conclusões.


## 6 CONCLUSÕES

Este trabalho desenvolveu e avaliou o MaríliaBot, uma plataforma de inteligência imobiliária que integra coleta de dados públicos, avaliação automatizada por regressão de quantis, explicabilidade por valores SHAP e simulação de viabilidade econômico-financeira para o contexto da habitação popular em Marília-SP. Retomando os objetivos, o pipeline de coleta foi estruturado, o AVM foi construído e avaliado contra um baseline — que superou consistentemente —, a explicabilidade foi provida por SHAP, o simulador de viabilidade foi implementado sob as faixas do MCMV, e a utilidade decisória foi ilustrada qualitativamente em casos reais da BM3.

A principal contribuição é demonstrar, em um caso concreto de cidade do interior, que a Construção 4.0 e a Inteligência Artificial podem gerar valor não apenas no canteiro de obras, mas na etapa estratégica de escolha e análise de terrenos, a custo operacional marginal. O diferencial não reside no algoritmo, mas na integração de fontes públicas hiperlocais — incluindo sinais off-market — e na concepção que adota transações reais (ITBI) como verdade-fundamento, combinação ausente nas soluções comerciais existentes, ainda que, nesta etapa, o ITBI não esteja disponível na base. Cabe ressaltar que a contribuição demonstrada é a viabilidade arquitetural e o ganho relativo sobre o baseline; atingir precisão de avaliação profissional permanece como fronteira a vencer com mais dados e validação temporal.

Como limitações, reiteram-se a validade externa restrita a um caso, o vazamento residual na avaliação do modelo, a dependência do acesso ao ITBI e a calibração financeira de pequena amostra. Como trabalhos futuros, indicam-se: a adoção de divisão temporal e backtesting do modelo; a ampliação da base de transações; a integração de um grafo de relacionamentos entre proprietários; a busca semântica sobre os documentos municipais; o monitoramento das mudanças do Plano Diretor de Marília; e a avaliação prospectiva da plataforma em novas decisões da BM3.

REFERÊNCIAS

ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. NBR 14653-2: avaliação de bens – parte 2: imóveis urbanos. Rio de Janeiro: ABNT, 2011.

BRASIL. Decreto nº 7.983, de 8 de abril de 2013. Estabelece regras e critérios para elaboração do orçamento de referência de obras e serviços de engenharia. Diário Oficial da União, Brasília, DF, 2013.

BRASIL. Lei nº 13.709, de 14 de agosto de 2018. Lei Geral de Proteção de Dados Pessoais (LGPD). Brasília, DF, 2018.

BRASIL. Lei nº 14.620, de 13 de julho de 2023. Dispõe sobre o Programa Minha Casa, Minha Vida. Brasília, DF, 2023.

BREIMAN, L. Random forests. Machine Learning, v. 45, n. 1, p. 5–32, 2001.

CAIXA ECONÔMICA FEDERAL. SINAPI: metodologia e conceitos. Brasília: Caixa Econômica Federal, 2024. Disponível em: https://www.caixa.gov.br. Acesso em: 22 jun. 2026.

CHEN, T.; GUESTRIN, C. XGBoost: a scalable tree boosting system. In: Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining. New York: ACM, 2016. p. 785–794.

FUNDAÇÃO GETULIO VARGAS. Índice Nacional de Custo da Construção (INCC). Rio de Janeiro: FGV IBRE, 2024. Disponível em: https://portalibre.fgv.br. Acesso em: 22 jun. 2026.

FUNDAÇÃO JOÃO PINHEIRO. Déficit habitacional no Brasil. Belo Horizonte: FJP, 2023. Disponível em: http://www.fjp.mg.gov.br. Acesso em: 22 jun. 2026.

HASTIE, T.; TIBSHIRANI, R.; FRIEDMAN, J. The elements of statistical learning: data mining, inference, and prediction. 2. ed. New York: Springer, 2009.

INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA (IBGE). Censo Demográfico 2022. Rio de Janeiro: IBGE, 2023. Disponível em: https://www.ibge.gov.br. Acesso em: 22 jun. 2026.

JAMES, G. et al. An introduction to statistical learning: with applications in R. New York: Springer, 2013.

KE, G. et al. LightGBM: a highly efficient gradient boosting decision tree. In: Advances in Neural Information Processing Systems (NeurIPS). [S.l.: s.n.], 2017. v. 30, p. 3146–3154.

KOENKER, R.; BASSETT, G. Regression quantiles. Econometrica, v. 46, n. 1, p. 33–50, 1978.

KOK, N.; KOPONEN, E.-L.; MARTÍNEZ-BARBOSA, C. A. Big data in real estate? From manual appraisal to automated valuation. The Journal of Portfolio Management, v. 43, n. 6, p. 202–211, 2017.

LUNDBERG, S. M.; LEE, S.-I. A unified approach to interpreting model predictions. In: Advances in Neural Information Processing Systems (NeurIPS). [S.l.: s.n.], 2017. v. 30, p. 4765–4774.

MOLNAR, C. Interpretable machine learning: a guide for making black box models explainable. 2. ed. [S.l.: s.n.], 2022. Disponível em: https://christophm.github.io/interpretable-ml-book. Acesso em: 22 jun. 2026.

OESTERREICH, T. D.; TEUTEBERG, F. Understanding the implications of digitisation and automation in the context of Industry 4.0: a triangulation approach and elements of a research agenda for the construction industry. Computers in Industry, v. 83, p. 121–139, 2016.

PÉREZ-RAVE, J. I.; CORREA-MORALES, J. C.; GONZÁLEZ-ECHAVARRÍA, F. A machine learning approach to big data regression analysis of real estate prices for inferential and predictive purposes. Journal of Property Research, v. 36, n. 1, p. 59–96, 2019.

PREFEITURA MUNICIPAL DE MARÍLIA. Lei Complementar nº 753, de 2017: parcelamento, uso e ocupação do solo. Marília: Prefeitura Municipal de Marília, 2017.

ROSEN, S. Hedonic prices and implicit markets: product differentiation in pure competition. Journal of Political Economy, v. 82, n. 1, p. 34–55, 1974.

YIN, R. K. Estudo de caso: planejamento e métodos. 5. ed. Porto Alegre: Bookman, 2015.


## Tabelas/Quadros


**1**
| Solução | Força principal | Lacuna frente ao MaríliaBot |
| Urbit | AVM e camada geoespacial profunda em SP/BH | Não cobre Marília; sem off-market, sem SINAPI |
| Oferta Terreno | IA com múltiplos inputs; TIR/VPL; foco MCMV | Sem coleta própria (input manual); sem off-market |
| Hiperdados | ERP 360° (landbank a contábil); 120+ cidades | Enterprise; sem coleta nem discovery |
| Locates | GIS + IA; viabilidade urbanística automática | Foco no Sul; não cobre o interior de SP |
| DataZap (OLX) | Maior base de dados do país | Vende dado, não plataforma de decisão |

**2**
| Bloco | Conteúdo |
| Proposta de valor | Reduzir a incerteza da decisão de investimento (onde/o que/quando construir) com previsão de preço, custo e viabilidade explicáveis, baseadas em dados públicos cruzados e em sinais off-market antecipados |
| Segmentos de cliente | (1) Uso interno: BM3. (2) Pequenos/médios incorporadores do interior. (3) Investidores em terreno. (4) Corretores |
| Canais | Dashboard web; bot de Telegram; laudos e relatórios |
| Relacionamento | Self-service no dashboard; alertas proativos; consultoria sob demanda |
| Fontes de receita | Laudo de viabilidade; radar por assinatura; comissão sobre lead curado; futura licença por cidade |
| Recursos-chave | Base de dados proprietária e cumulativa; pipeline de coleta; modelos calibrados; conhecimento de domínio |
| Atividades-chave | Coleta e curadoria; treino e calibração; manutenção do pipeline; geração de inteligência |
| Parcerias-chave | Fontes públicas (Prefeitura, IBGE, Caixa); provedores de nuvem/IA; cartórios; corretores |
| Estrutura de custos | Infraestrutura e IA na ordem de dezenas de reais/mês; consultas pagas a cartório/ITBI; tempo de desenvolvimento |

**3**
| Dimensão | Classificação |
| Natureza | Pesquisa aplicada |
| Abordagem | Quali-quantitativa |
| Objetivos | Exploratória e descritiva |
| Procedimentos | Pesquisa bibliográfica e estudo de caso |

**4**
| Dimensão | Classificação |
| Método de abordagem | Hipotético-dedutivo |
| Método de procedimento | Monográfico (estudo de caso) |
| Unidade de análise | Terreno/oportunidade de empreendimento MCMV em Marília-SP |
| Coleta de dados | Documentação indireta (dados públicos) e dados primários da BM3 |

**5**
| Grupo | Fontes | Natureza |
| On-market | Viva Real, ZAP, Chaves na Mão, União, Toca | Preço de oferta |
| Off-market | Leilão, alvará, EIV, IPTU em dívida, inventário, CMDU | Sinal antecedente |
| Institucional | ITBI, SINAPI, IBGE (setores censitários), OpenStreetMap | Transação e contexto |

**6**
| Etapa | Registros | Observação |
| Imóveis coletados (base total) | 19.821 | Todas as categorias e fontes |
| Terrenos ativos com preço e área | 205 | População efetiva do AVM (tipo: terreno) |
| Geocodificados | 205 (100%) | Com coordenadas válidas |
| Transações ITBI disponíveis | 0 | Dependente de solicitação via LAI |

**7**
| Métrica | Cenário 1 (baseline) | Cenário 2 (AVM) |
| MAE (R$) | 1.991.769 ± 2.087.023 | 502.337 ± 441.843 |
| MAPE (%) | 129,6 ± 64,0 | 81,7 ± 25,2 |
| RMSE (R$) | 9.233.770 ± 10.024.308 | 1.939.979 ± 2.112.809 |
| Cobertura P25–P75 (alvo 50%) | — | 43,4% ± 6,5 |
| Cobertura P10–P90 (alvo 80%) | — | 65,4% ± 7,8 |
# Roteiro de defesa — MaríliaBot (versão reframada)

> Alinhado ao TCC após o reframe honesto (paridade em acurácia + CQR + explicabilidade).
> Supera o `TCC_roteiro_defesa.md` anterior, que se baseava nos números antigos (superioridade do AVM).
> Princípio-mestre: **rebaixar toda afirmação ao que os dados sustentam.** A banca perdoa escopo modesto e honesto; não perdoa afirmação forte sem lastro.

## Cola de números (decorar)

| Item | Valor |
|---|---|
| Coorte congelado | 177 terrenos (mar–mai/2026); 162 no segmento residencial (≤ 1.000 m²) |
| MAPE AVM (P50) vs baseline | 54,6% vs 50,7% (**empate**) |
| Wilcoxon pareado (AVM < baseline) | p = 0,98 (**sem superioridade**) |
| Estrato < R$ 300k | baseline melhor (53,6% vs 62,0%) |
| Cobertura P10–P90 (quantis diretos) | 50,3% (subcobre o alvo de 80%) |
| Cobertura P10–P90 com **CQR** | **80,0% exato** |
| ITBI (ground truth) | 0 (arquitetura pronta, dado pendente de LAI) |
| Validação cruzada | hold-out repetido 80/20, 5 divisões |
| Reprodutibilidade | `docs/avm_snapshot.json` + `scripts/eval_avm.py` |

## Abertura (60–90s, se pedirem)

"O MaríliaBot ataca a decisão mais cara e menos apoiada por dados do pequeno incorporador: comprar ou não um terreno para MCMV. A contribuição não é acertar o preço melhor que o mercado, é dar uma decisão auditável: uma faixa de valor com incerteza calibrada, explicada em linguagem natural, acoplada à simulação de viabilidade sob as regras do MCMV. No estudo de caso da BM3, isso reproduz o desfecho real dos empreendimentos. Sou sócio da BM3, o que declaro abertamente, e por isso submeti tudo a métrica neutra e a um baseline forte."

---

## As perguntas letais e as respostas ensaiadas

### 1. "Você não tem ground truth. Treina e valida no preço de anúncio que o próprio Cap. 2.6 diz ser enviesado. Onde há UMA observação de valor real?"
**Resposta:** "Correto, e é uma limitação que declaro no resumo, na Tabela 1 e nas conclusões. O ITBI é parte da arquitetura (o código já atribui peso maior à transação que ao anúncio), mas o dado depende de processo de LAI ainda pendente. Nesta versão o trabalho não valida acurácia de mercado, valida **consistência preditiva sobre a oferta** e entrega o pipeline pronto para calibrar quando o ITBI chegar. Por isso não afirmo em nenhum lugar que 'acerto o preço real'."
**Se insistirem:** "A literatura que cito quantifica o gap anúncio-transação em 5% a 25%; é o viés sistemático conhecido que herdo e sinalizo, não escondo."

### 2. "Se o erro do AVM é da ordem de dezenas de milhares e a decisão da Casa 2 depende de R$ 24 mil, o instrumento não mede o que precisa medir."
**Resposta:** "De acordo, e por isso não leio o P50 como preço exato, e sim como faixa. O que sustenta o NO-GO das Casas 2 e 3 não é o ponto, é o preço pago ter ficado **acima do intervalo de referência** combinado ao teto do MCMV. O Experimento B é ilustrativo (N=3), não teste estatístico, e está rotulado assim."

### 3. "No caso da Casa 2, o NO-GO vem do teto do MCMV, um `if`. Onde o AVM quantílico, o SHAP e o Newton-Raphson mudaram a decisão?"
**Resposta:** "Nesse caso específico o teto domina, admito. O valor do AVM aparece antes: na etapa de aquisição da terra, evitar pagar ágio sobre a faixa de mercado, e na explicação do porquê via SHAP. Reconheço que, com N=3, o teto foi o fator dominante; casos em que o terreno é o fiel da balança são exatamente o que a validação prospectiva deve cobrir."

### 4. "Você validou nos próprios 3 projetos, sabendo o desfecho. Que resultado teria refutado a hipótese?"
**Resposta:** "Nenhum, e é por isso que rebaixei o Experimento B a estudo de caso ilustrativo (Yin), não a teste de hipótese. Declaro o conflito de interesse. A mitigação real é validação prospectiva cega, registrar o veredito GO/NO-GO antes de conhecer o desfecho, que proponho como trabalho futuro com protocolo."
**Sobre leakage:** "Os casos BM3 são aquisições próprias passadas (tabela `bm3_deals`), não anúncios ativos; o treino usa só `listings` on-market. São out-of-sample por construção."

### 5. "Seus intervalos de incerteza não cobrem: 50% no alvo de 80%. A QP1 promete intervalo confiável."
**Resposta:** "Os quantis diretos de fato subcobrem, 50,3% no alvo de 80%, e reporto isso na Tabela 2. A solução está no próprio trabalho: apliquei Conformalized Quantile Regression, que **calibra a cobertura para 80,0% exatos**. É o diferencial técnico central: o baseline de preço/m² dá um ponto sem confiança; o AVM dá uma faixa com garantia de cobertura." (Este é o seu ponto mais forte, puxe a conversa pra cá.)

### 6. "Você disse 'significância estatística' sem teste."
**Resposta:** "Corrigi isso. Rodei Wilcoxon pareado sobre os erros por terreno. O resultado é honesto e talvez surpreenda: p=0,98, ou seja, **o AVM não é estatisticamente superior ao baseline em acurácia pontual**. Reporto empate, não vitória. Preferi a verdade a uma palavra sem lastro."

### 7. "Seu baseline de 129% era um espantalho. Contra um baseline forte, seu ganho some."
**Resposta:** "Concordo com a crítica ao número antigo, por isso refiz tudo. O baseline aqui é a mediana de preço/m² por bairro, exatamente a heurística que a PME usa, e mostrou-se **forte**: empata ou supera o AVM no segmento residencial. Não escondo isso, reporto. Não há espantalho porque o baseline venceu em parte."

### 8. "Off-market é o pilar da sua originalidade, mas os 412 registros não entram no modelo e você não mostra uma oportunidade descoberta."
**Resposta:** "Verdade. A coleta off-market está operacional (os 412 registros comprovam o pipeline) e alimenta o **radar de oportunidades**, não o modelo de preço, o que deixo explícito no texto. A integração ao AVM e a métrica de descoberta são trabalho futuro. Rebaixei as afirmações do Canvas de 'descobre antes da concorrência' para 'arquitetura preparada para'."

### 9. "TAM/SAM/SOM: de onde vêm os números? E por que um terço do trabalho é plano de negócio num MBA de IA?"
**Resposta:** "São estimativas próprias, agora com método explícito: contagem de empresas por CNAE (RAIS/CBIC, IBGE Cidades) e tíquete médio derivado das fontes de receita. Corrigi o SOM, que antes supunha 100% de captura; agora usa penetração de 10–20%, R$ 180–360 mil/ano. O capítulo de mercado se justifica pelo enquadramento de pesquisa aplicada/desenvolvimento de produto, mas o núcleo avaliativo do trabalho é técnico."

### 10. "Por que o N caiu de 205 para 177? E como sei que não há vazamento no split?"
**Resposta:** "O banco é vivo e evoluiu; para garantir reprodutibilidade congelei o coorte usado (177 terrenos) num arquivo versionado, então qualquer um roda o `eval_avm.py` e reproduz a tabela. O preço médio do bairro e o target-encoding são ajustados só no treino de cada divisão (sem vazamento), e o script inclusive corrige um viés que a produção tinha. O split é aleatório repetido; o temporal fica como limitação declarada."

### 11 (a nova pergunta-chave). "Se o AVM não vence o baseline, por que existe?"
**Resposta:** "Porque acurácia pontual não é o produto. Um preço/m² por bairro te dá um número, sem dizer o quão confiável é nem por quê. O MaríliaBot entrega três coisas que o baseline não tem: **incerteza calibrada** (faixa com cobertura garantida via CQR), **explicabilidade** (SHAP em linguagem natural, auditável) e **integração à viabilidade MCMV** (GO/NO-GO). Para uma decisão de capital sob teto regulado, decidir bem vale mais que estimar o ponto com um dígito a mais de precisão."

---

## Armadilhas — o que NÃO dizer

- Não diga "significância estatística" (não há; é empate).
- Não diga que o AVM "é mais preciso" ou "supera" o baseline. Diga **paridade**.
- Não venda off-market como entregue no modelo. É radar/arquitetura.
- Não trate o Experimento B como prova. É ilustração (N=3, retrospectivo, autor).
- Não chame os intervalos crus de "confiáveis". O confiável é o **CQR**.
- Não defenda o ITBI como implementado. É projetado, pendente de LAI.

## Encerramento (se couber)
"O trabalho entrega uma plataforma funcional, auditável e reprodutível a custo marginal, com uma contribuição honesta: não substituir o avaliador com mais precisão, mas dar ao pequeno incorporador uma decisão com incerteza calibrada, explicável e integrada às regras do MCMV, algo que hoje ele não tem."

# Pedido LAI — Alvarás de aprovação de projeto e habite-se (Marília-SP)

> Desbloqueador do sinal "alvará 18-36 meses antes" (radar de concorrência e
> rating de construtoras). Confirmado que o DOM-MAR dados-abertos NÃO publica
> esses registros estruturados; a via pública é a Lei de Acesso à Informação
> (Lei 12.527/2011). Texto pronto para submeter no e-SIC de Marília.

## Onde enviar

Portal da Transparência de Marília → Serviço de Informação ao Cidadão (e-SIC).
Órgão-alvo: **Secretaria Municipal de Planejamento Urbano / Urbanismo** (aprovação
de projetos) e **Fiscalização de Obras** (habite-se).

## Texto do pedido

Assunto: Solicitação de dados de alvarás de aprovação de projeto e habite-se

Com base na Lei nº 12.527/2011 (Lei de Acesso à Informação), solicito o
fornecimento, em **formato aberto e estruturado** (CSV, XLSX ou JSON — não PDF
escaneado), dos seguintes dados relativos a licenciamento de obras particulares
no município de Marília, referentes aos **últimos 36 meses**:

**1. Alvarás de aprovação de projeto / licença de construção**, contendo por registro:
- número do alvará e número do processo administrativo
- data de emissão
- requerente (nome/razão social) e CNPJ/CPF
- endereço da obra e bairro
- área do terreno e área construída (m²)
- número de unidades e de pavimentos
- uso (residencial, comercial, industrial, misto)

**2. Habite-se (certificado de conclusão)**, contendo por registro:
- número e data de emissão
- número do processo administrativo (para cruzamento com o alvará)
- endereço e bairro
- área construída regularizada

Solicito, se possível, **atualização periódica** (mensal ou trimestral) do mesmo
conjunto, ou a indicação de um endpoint/base já existente de onde esses dados
possam ser obtidos de forma recorrente.

Justificativa: pesquisa de mercado imobiliário local (dados públicos agregados),
sem tratamento de dado pessoal sensível além do estritamente necessário à
identificação do empreendedor responsável pela obra.

## Notas de LGPD

- Requerente PJ (CNPJ) é dado público de empresa; requerente PF (CPF) é dado
  pessoal — pedir CPF apenas se necessário e tratar com base em legítimo
  interesse, minimizando/anonimizando em qualquer publicação ou relatório.
- Alinhar com o tratamento já dado ao ITBI no TCC: dado obtido por via oficial,
  uso interno/agregado, sem redistribuição do dado bruto.

## Depois de obter os dados

- Popular `alvaras_marilia` e `habite_se_records` via um coletor de import
  (CSV/XLSX → upsert), reaproveitando o schema já aplicado (sql/044, sql/032).
- Aí sim `rating-construtoras` produz rating real (alvará × habite-se → prazo/
  entrega) e o `/radar`/`/construtora` acendem com dado de verdade.

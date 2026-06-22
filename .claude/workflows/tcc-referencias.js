export const meta = {
  name: 'tcc-referencias',
  description: 'Analisa 4 TCCs aprovados (PDFs) para extrair o molde do programa: estrutura, ABNT, referências, tom. Sintetiza num modelo de referência e compara com o rascunho atual.',
  phases: [
    { title: 'Leitura', detail: '1 agente lê cada TCC de referência e extrai perfil estruturado' },
    { title: 'Síntese', detail: 'consolida o molde do programa e compara com docs/TCC_draft.md' },
  ],
}

const REFS = [
  { label: 'Camurça', path: '/Users/matheus.rezende/Downloads/David_Camurça_MBA_TCC_REVISADO_POS_DEFESA - David Camurça.pdf', pages: 54, nota: '' },
  { label: 'Improta-TabNet', path: '/Users/matheus.rezende/Downloads/Incorporando_Análise_de_Sentimentos_na_Predição_em_Séries_Temporais_Financeiras_por_meio_de_Modelos_TabNet - Alexandre Improta.pdf', pages: 50, nota: 'MATCH MAIS PRÓXIMO: ML aplicado / séries temporais / predição. Detalhe ao máximo Metodologia e Resultados.' },
  { label: 'Favaro', path: '/Users/matheus.rezende/Downloads/TCC_CarlosEduardoFavaro - Carlos Eduardo Favaro.pdf', pages: 62, nota: '' },
  { label: 'Faria', path: '/Users/matheus.rezende/Downloads/TCC_Final Revisado - Víctor de Souza Faria.pdf', pages: 35, nota: '' },
]

const PROFILE_SCHEMA = {
  type: 'object',
  required: ['titulo', 'enquadramento_metodologico', 'estrutura', 'formatacao_abnt', 'referencias', 'tom_voz', 'pontos_fortes', 'transferivel_para_o_caso'],
  properties: {
    titulo: { type: 'string' },
    autor: { type: 'string' },
    paginas_conteudo: { type: 'string', description: 'nº de páginas só do conteúdo (sem capa/pré-textual)' },
    enquadramento_metodologico: { type: 'string', description: 'tipo de pesquisa, método declarado (estudo de caso, DSR, survey, experimento, etc.), como validaram' },
    estrutura: {
      type: 'array', description: 'capítulos/seções na ordem em que aparecem',
      items: {
        type: 'object', required: ['secao', 'paginas_aprox', 'conteudo'],
        properties: {
          secao: { type: 'string' },
          paginas_aprox: { type: 'string' },
          conteudo: { type: 'string', description: 'o que essa seção contém, em 1 frase' },
        },
      },
    },
    formatacao_abnt: {
      type: 'object',
      required: ['citacao', 'referencias_estilo', 'numeracao_secoes', 'resumo_abstract', 'figuras_tabelas'],
      properties: {
        citacao: { type: 'string', description: 'autor-data (NBR 10520) ou numérico; exemplo real do texto' },
        referencias_estilo: { type: 'string', description: 'formato da lista de referências (NBR 6023), ordenação' },
        numeracao_secoes: { type: 'string', description: 'numeração progressiva (NBR 6024)? 1, 1.1, 1.1.1?' },
        resumo_abstract: { type: 'string', description: 'tem resumo+abstract+palavras-chave? extensão?' },
        figuras_tabelas: { type: 'string', description: 'como numeram/legendam figuras, tabelas, quadros' },
      },
    },
    referencias: {
      type: 'object', required: ['quantidade_aprox', 'tipos'],
      properties: {
        quantidade_aprox: { type: 'string' },
        tipos: { type: 'string', description: 'artigos/livros/web/normas; proporção; idioma (PT/EN)' },
      },
    },
    tom_voz: { type: 'string', description: 'impessoal? 1ª pessoa plural? presente/passado?' },
    pontos_fortes: { type: 'array', items: { type: 'string' }, description: 'o que torna este TCC forte/aprovável' },
    transferivel_para_o_caso: { type: 'array', items: { type: 'string' }, description: 'o que o Matheus (IA imobiliária aplicada, MaríliaBot) deve imitar deste TCC especificamente' },
  },
}

const readInstr = (r) =>
  `Você é um analista de TCCs. Leia o PDF em "${r.path}" (${r.pages} páginas) INTEIRO, em blocos de até 20 páginas (Read com pages="1-20", depois "21-40", etc., até cobrir tudo). ` +
  `IGNORE elementos pré-textuais decorativos (capa, folha de rosto, ficha catalográfica, dedicatória, agradecimentos) — foque em conteúdo, formatação, ABNT e referências. ` +
  (r.nota ? `NOTA: ${r.nota} ` : '') +
  `Extraia um perfil estruturado completo deste TCC aprovado, preenchendo todos os campos do schema com evidência concreta (cite exemplos reais do texto, ex: como uma citação aparece, como uma tabela é legendada).`

// ─── Fase 1: leitura paralela ──────────────────────────────────────────
phase('Leitura')
const profiles = await parallel(REFS.map((r) => () =>
  agent(readInstr(r), { label: r.label, phase: 'Leitura', schema: PROFILE_SCHEMA })
))

const validos = profiles.filter(Boolean)

// ─── Fase 2: síntese do molde + comparação com o rascunho ──────────────
phase('Síntese')
const dossie = validos.map((p, i) =>
  `### TCC ${i + 1}: ${p.titulo} (${REFS[i] ? REFS[i].label : ''})\n` + JSON.stringify(p, null, 2)
).join('\n\n')

const molde = await agent(
  `Leia o rascunho do TCC do Matheus em docs/TCC_draft.md (sistema MaríliaBot — IA imobiliária para viabilidade de habitação popular MCMV). ` +
  `Abaixo estão os perfis estruturados de ${validos.length} TCCs APROVADOS do mesmo programa (MBA USP). ` +
  `Produza um documento em Markdown com:\n` +
  `1. **Molde do programa** — o padrão comum aos TCCs aprovados: estrutura/seções obrigatórias na ordem certa, com extensão típica por seção; normas ABNT efetivamente usadas (citação, referências, numeração, figuras/tabelas, resumo/abstract); quantidade e tipo de referências esperadas; tom/voz.\n` +
  `2. **Variações aceitáveis vs. invariantes** — o que todos seguem (norma rígida) vs. o que varia por autor (escolha).\n` +
  `3. **O TCC do Improta (TabNet) como espelho** — por ser ML aplicado, detalhe como ele estrutura Metodologia e Resultados, e o que o Matheus deve copiar dessa estrutura.\n` +
  `4. **Tabela comparativa: rascunho do Matheus × molde** — seção a seção, o que ele tem, o que falta, e a ação concreta para alinhar.\n` +
  `5. **Esqueleto-alvo do TCC do Matheus** — sumário proposto, capítulo a capítulo, com extensão-alvo em páginas, já no formato do programa.\n\n` +
  `PERFIS DOS TCCS APROVADOS:\n\n` + dossie,
  { label: 'molde', phase: 'Síntese' }
)

return { molde, profiles: validos }

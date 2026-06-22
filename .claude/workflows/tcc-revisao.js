export const meta = {
  name: 'tcc-revisao',
  description: 'Revisão multi-agente do TCC MBA: 4 lentes analisam o texto+código, banca e redator reagem aos pareceres, orientador consolida em plano de ação priorizado.',
  phases: [
    { title: 'Análise', detail: 'orientador, técnico, metodólogo e mercado analisam em paralelo' },
    { title: 'Debate', detail: 'banca ataca e redator reescreve, reagindo aos pareceres' },
    { title: 'Síntese', detail: 'orientador consolida tudo num plano priorizado' },
  ],
}

const DRAFT = 'docs/TCC_draft.md'
const base = `Leia o texto do TCC em ${DRAFT} e o código do repositório quando relevante. `

// Cada agente lê seu próprio arquivo de persona em .claude/agents/ e o adota.
// Isso reusa as definições persistentes como única fonte de verdade e dispensa
// que os agentes estejam registrados na sessão atual.
const persona = (slug) =>
  `Leia integralmente o arquivo .claude/agents/${slug}.md e adote a persona, as prioridades e o FORMATO DE SAÍDA ali definidos como suas instruções de sistema. Depois execute a tarefa abaixo, respondendo no formato indicado.\n\n`

// ─── Fase 1: quatro lentes independentes ───────────────────────────────
phase('Análise')
const [orient, tecnico, metodo, mercado] = await parallel([
  () => agent(persona('tcc-orientador') + base + 'Produza seu parecer de orientador sobre estrutura, fio condutor e prontidão para defesa.',
    { label: 'orientador', phase: 'Análise' }),
  () => agent(persona('tcc-tecnico') + base + 'Audite cada afirmação técnica do TCC contra o código real (src/, sql/, .github/). Confirme com arquivo:linha.',
    { label: 'técnico', phase: 'Análise' }),
  () => agent(persona('tcc-metodologo') + base + 'Produza o parecer metodológico: enquadramento de pesquisa, esqueleto da Metodologia que falta, e rigor de ML/estatística (validação do AVM, leakage, viés).',
    { label: 'metodólogo', phase: 'Análise' }),
  () => agent(persona('tcc-mercado') + base + 'Produza o parecer de mercado: proposta de valor, matriz de benchmarking, Canvas/SWOT e modelo de receita.',
    { label: 'mercado', phase: 'Análise' }),
])

// ─── Fase 2: conversa — banca e redator reagem aos pareceres ───────────
phase('Debate')
const dossie = [
  '### PARECER DO ORIENTADOR\n' + orient,
  '### AUDITORIA TÉCNICA\n' + tecnico,
  '### PARECER METODOLÓGICO\n' + metodo,
  '### PARECER DE MERCADO\n' + mercado,
].join('\n\n---\n\n')

const [banca, redator] = await parallel([
  () => agent(persona('tcc-banca') + base +
    'Estes são os pareceres dos outros avaliadores. Use as fraquezas que eles apontaram como munição e formule as perguntas de banca mais difíceis, indicando quais o trabalho NÃO consegue responder hoje.\n\n' + dossie,
    { label: 'banca', phase: 'Debate' }),
  () => agent(persona('tcc-redator') + base +
    'A auditoria técnica e o parecer metodológico abaixo apontam afirmações imprecisas ou exageradas. Reescreva os trechos problemáticos do TCC para um fraseado defensável (sem inflar), e liste reescritas trecho a trecho.\n\n' +
    '### AUDITORIA TÉCNICA\n' + tecnico + '\n\n### PARECER METODOLÓGICO\n' + metodo,
    { label: 'redator', phase: 'Debate' }),
])

// ─── Fase 3: síntese — orientador consolida ────────────────────────────
phase('Síntese')
const tudo = dossie + '\n\n---\n\n### SIMULAÇÃO DE BANCA\n' + banca + '\n\n---\n\n### REVISÃO DE REDAÇÃO\n' + redator
const sintese = await agent(persona('tcc-orientador') + base +
  'Você já deu seu parecer inicial. Agora consolide TODOS os pareceres abaixo num único plano de ação priorizado (P0 bloqueadores → P1 importantes → P2 melhorias), resolvendo conflitos entre eles. Termine com um cronograma sugerido até a entrega.\n\n' + tudo,
  { label: 'síntese', phase: 'Síntese' })

return {
  sintese,
  pareceres: { orientador: orient, tecnico, metodologo: metodo, mercado, banca, redator },
}

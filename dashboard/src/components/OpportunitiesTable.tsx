import { useCallback, useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { useOpportunities, useViabilityStudies } from '../hooks/useSupabase'
import { supabase } from '../lib/supabase'
import type { Listing } from '../types'

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
}

function fmtArea(n: number | null | undefined): string {
  if (n == null) return '-'
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })} m²`
}

function scoreBadge(score: number): string {
  if (score >= 80) return 'bg-green-900/50 text-green-300 border-green-700'
  if (score >= 60) return 'bg-yellow-900/50 text-yellow-300 border-yellow-700'
  if (score >= 40) return 'bg-orange-900/50 text-orange-300 border-orange-700'
  return 'bg-slate-800 text-slate-400 border-slate-600'
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-400'
  if (score >= 60) return 'text-yellow-400'
  if (score >= 40) return 'text-orange-400'
  return 'text-slate-400'
}

const BREAKDOWN_LABELS: Record<string, { label: string; max: number; color: string }> = {
  price: { label: 'Preco', max: 25, color: '#10b981' },
  price_m2: { label: 'Preco/m²', max: 20, color: '#059669' },
  area: { label: 'Area', max: 15, color: '#3b82f6' },
  mcmv: { label: 'MCMV', max: 10, color: '#f59e0b' },
  location: { label: 'Localizacao', max: 10, color: '#8b5cf6' },
  data_quality: { label: 'Dados', max: 10, color: '#6366f1' },
  source: { label: 'Fonte', max: 10, color: '#64748b' },
  enriched: { label: 'Enriquecido', max: 10, color: '#14b8a6' },
  stale: { label: 'Tempo no mercado', max: 5, color: '#ec4899' },
}

const DECISIONS = [
  { value: 'interested', label: 'Interessado', tone: 'bg-sky-900/40 text-sky-300 border-sky-700/40' },
  { value: 'visited', label: 'Visitar', tone: 'bg-indigo-900/40 text-indigo-300 border-indigo-700/40' },
  { value: 'offered', label: 'Ofereci', tone: 'bg-amber-900/40 text-amber-300 border-amber-700/40' },
  { value: 'rejected', label: 'Rejeitei', tone: 'bg-rose-900/40 text-rose-300 border-rose-700/40' },
  { value: 'acquired', label: 'Adquiri', tone: 'bg-emerald-900/40 text-emerald-300 border-emerald-700/40' },
  { value: 'won_by_other', label: 'Perdemos', tone: 'bg-slate-700 text-slate-300 border-slate-600' },
]

const DECISION_TONE: Record<string, string> = Object.fromEntries(DECISIONS.map(d => [d.value, d.tone]))
const DECISION_LABEL: Record<string, string> = Object.fromEntries(DECISIONS.map(d => [d.value, d.label]))

function ScoreBreakdown({ breakdown }: { breakdown: Record<string, number> }) {
  const entries = Object.entries(breakdown)
    .filter(([key]) => key in BREAKDOWN_LABELS)
    .sort(([, a], [, b]) => b - a)

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-2 p-4">
      {entries.map(([key, value]) => {
        const config = BREAKDOWN_LABELS[key]
        if (!config) return null
        const pct = Math.min(100, (value / config.max) * 100)
        return (
          <div key={key} className="bg-slate-700/50 rounded-lg p-2.5">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs text-slate-400">{config.label}</span>
              <span className="text-xs font-mono font-bold text-white">{value}/{config.max}</span>
            </div>
            <div className="h-1.5 bg-slate-600 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct}%`, backgroundColor: config.color }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ViabilityBadges({ studies }: { studies: any[] }) {
  if (!studies?.length) return null
  const viable = studies.filter(s => s.is_viable)
  const best = viable.sort((a, b) => (b.outputs?.margem_liquida_pct || 0) - (a.outputs?.margem_liquida_pct || 0))[0]

  return (
    <div className="mt-3 px-4 border-t border-slate-700 pt-3">
      <p className="text-xs text-slate-400 mb-2">Viabilidade (calculada pelo pipeline)</p>
      <div className="flex flex-wrap gap-2">
        {studies.map((s, i) => {
          const margin = s.outputs?.margem_liquida_pct || 0
          const vgv = s.outputs?.vgv || 0
          const units = s.outputs?.unidades || 0
          const isBest = s === best
          return (
            <div key={i} className={`text-xs rounded-lg px-3 py-2 border ${
              s.is_viable
                ? isBest ? 'bg-green-900/40 border-green-700 text-green-300' : 'bg-green-900/20 border-green-800 text-green-400'
                : 'bg-red-900/20 border-red-800 text-red-400'
            }`}>
              <span className="font-semibold">{s.scenario}</span>
              <span className="ml-2">{units} un.</span>
              <span className="ml-2">margem {margin.toFixed(1)}%</span>
              <span className="ml-2">VGV R${(vgv/1000).toFixed(0)}k</span>
              {isBest && <span className="ml-1 text-[10px]">MELHOR</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface DecisionFormState {
  decision: string
  offered_price: string
  actual_price: string
  reason: string
  notes: string
}

function DecisionModal({
  listingId,
  opportunityId,
  initialDecision,
  onClose,
  onSaved,
}: {
  listingId: number
  opportunityId: number
  initialDecision: string
  onClose: () => void
  onSaved: (decision: string) => void
}) {
  const [form, setForm] = useState<DecisionFormState>({
    decision: initialDecision,
    offered_price: '',
    actual_price: '',
    reason: '',
    notes: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function update<K extends keyof DecisionFormState>(k: K, v: DecisionFormState[K]) {
    setForm(f => ({ ...f, [k]: v }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload: Record<string, unknown> = {
        listing_id: listingId,
        opportunity_id: opportunityId,
        decision: form.decision,
      }
      if (form.offered_price) payload.offered_price = parseFloat(form.offered_price)
      if (form.actual_price && form.decision === 'acquired') payload.actual_price = parseFloat(form.actual_price)
      if (form.reason.trim()) payload.reason = form.reason.trim()
      if (form.notes.trim()) payload.notes = form.notes.trim()

      const { error: err } = await supabase.from('opportunity_decisions').insert(payload)
      if (err) throw err
      onSaved(form.decision)
      onClose()
    } catch (e: any) {
      setError(e.message || 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[2000] bg-black/60 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto">
      <div className="bg-slate-900 rounded-xl border border-slate-700 w-full max-w-lg my-8">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h2 className="text-base font-semibold text-white">Registrar decisao</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={submit} className="p-4 space-y-3">
          {error && (
            <div className="bg-rose-900/30 border border-rose-700/50 text-rose-300 text-xs rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 mb-1 block">Decisao</span>
            <select
              value={form.decision}
              onChange={e => update('decision', e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm"
            >
              {DECISIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 mb-1 block">Preco ofertado (R$)</span>
              <input
                type="number"
                step="0.01"
                value={form.offered_price}
                onChange={e => update('offered_price', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm"
              />
            </label>
            {form.decision === 'acquired' && (
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider text-slate-400 mb-1 block">Preco pago (R$)</span>
                <input
                  type="number"
                  step="0.01"
                  value={form.actual_price}
                  onChange={e => update('actual_price', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm"
                />
              </label>
            )}
          </div>

          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 mb-1 block">Motivo</span>
            <textarea
              value={form.reason}
              onChange={e => update('reason', e.target.value)}
              rows={2}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm resize-none"
            />
          </label>

          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 mb-1 block">Notas</span>
            <textarea
              value={form.notes}
              onChange={e => update('notes', e.target.value)}
              rows={3}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm resize-none"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50"
            >
              {saving ? 'Salvando...' : 'Salvar decisao'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function OpportunitiesTable() {
  const { opportunities, loading } = useOpportunities(50)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [decisions, setDecisions] = useState<Record<number, string>>({})
  const [modalState, setModalState] = useState<{ listingId: number; opportunityId: number; initial: string } | null>(null)

  const listingIds = opportunities.map(o => o.listing_id)
  const { studies: viabilityMap } = useViabilityStudies(listingIds)

  const loadDecisions = useCallback(async (ids: number[]) => {
    if (!ids.length) return
    const { data } = await supabase
      .from('opportunity_decisions')
      .select('listing_id, decision, created_at')
      .in('listing_id', ids)
      .order('created_at', { ascending: false })

    const latest: Record<number, string> = {}
    data?.forEach(d => {
      if (!(d.listing_id in latest)) latest[d.listing_id] = d.decision
    })
    setDecisions(latest)
  }, [])

  useEffect(() => {
    if (listingIds.length) loadDecisions(listingIds)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listingIds.join(',')])

  if (loading) {
    return <div className="text-slate-400 py-8 text-center">Carregando oportunidades...</div>
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="p-5 border-b border-slate-700">
        <h2 className="text-lg font-semibold text-white">Top Oportunidades de Terrenos</h2>
        <p className="text-sm text-slate-400 mt-1">{opportunities.length} terrenos pontuados — clique para ver detalhes</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-left border-b border-slate-700">
              <th className="px-5 py-3 font-medium">Score</th>
              <th className="px-5 py-3 font-medium">Bairro</th>
              <th className="px-5 py-3 font-medium text-right">Preco</th>
              <th className="px-5 py-3 font-medium text-right">Area</th>
              <th className="px-5 py-3 font-medium text-right">R$/m²</th>
              <th className="px-5 py-3 font-medium">MCMV</th>
              <th className="px-5 py-3 font-medium">Fonte</th>
              <th className="px-5 py-3 font-medium">Decisao</th>
            </tr>
          </thead>
          <tbody>
            {opportunities.map((opp) => {
              const l = (Array.isArray(opp.listing) ? opp.listing[0] : opp.listing) as Listing | undefined
              const isExpanded = expandedId === opp.id
              const currentDecision = decisions[opp.listing_id]
              return (
                <>
                  <tr
                    key={opp.id}
                    onClick={() => setExpandedId(isExpanded ? null : opp.id)}
                    className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer"
                  >
                    <td className="px-5 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded border text-xs font-mono font-bold ${scoreBadge(opp.score)}`}>
                        {opp.score}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-white">
                      {l?.neighborhood || '-'}
                    </td>
                    <td className={`px-5 py-3 text-right font-mono ${scoreColor(opp.score)}`}>
                      {fmt(l?.sale_price)}
                    </td>
                    <td className="px-5 py-3 text-right text-slate-300 font-mono">
                      {fmtArea(l?.total_area)}
                    </td>
                    <td className="px-5 py-3 text-right text-slate-300 font-mono">
                      {l?.price_per_m2 ? fmt(l.price_per_m2) : '-'}
                    </td>
                    <td className="px-5 py-3">
                      {l?.is_mcmv ? (
                        <span className="text-green-400 text-xs font-medium">Sim</span>
                      ) : (
                        <span className="text-slate-500 text-xs">-</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-xs text-slate-400 bg-slate-700 px-2 py-0.5 rounded">
                        {l?.source}
                      </span>
                    </td>
                    <td className="px-5 py-3" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center gap-2">
                        {currentDecision && (
                          <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${DECISION_TONE[currentDecision] || 'bg-slate-700 text-slate-300 border-slate-600'}`}>
                            {DECISION_LABEL[currentDecision] || currentDecision}
                          </span>
                        )}
                        <select
                          value=""
                          onChange={e => {
                            if (!e.target.value) return
                            setModalState({
                              listingId: opp.listing_id,
                              opportunityId: opp.id,
                              initial: e.target.value,
                            })
                          }}
                          className="bg-slate-900 border border-slate-700 rounded text-xs text-slate-300 px-2 py-1"
                        >
                          <option value="">+ Acao</option>
                          {DECISIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                        </select>
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr key={`${opp.id}-detail`} className="border-b border-slate-700/50 bg-slate-900/50">
                      <td colSpan={8}>
                        <div className="px-5 py-3">
                          <div className="flex items-center gap-4 mb-2">
                            <span className="text-xs text-slate-400">Score Breakdown</span>
                            {opp.reason && (
                              <span className="text-xs text-slate-500 italic">{opp.reason}</span>
                            )}
                          </div>
                          <ScoreBreakdown breakdown={opp.score_breakdown || {}} />
                          {viabilityMap[opp.listing_id] && (
                            <ViabilityBadges studies={viabilityMap[opp.listing_id]} />
                          )}
                          {l?.url && (
                            <div className="mt-2 px-4">
                              <a
                                href={l.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-indigo-400 hover:text-indigo-300 underline"
                              >
                                Ver anuncio original
                              </a>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      </div>

      {modalState && (
        <DecisionModal
          listingId={modalState.listingId}
          opportunityId={modalState.opportunityId}
          initialDecision={modalState.initial}
          onClose={() => setModalState(null)}
          onSaved={(decision) => {
            setDecisions(prev => ({ ...prev, [modalState.listingId]: decision }))
          }}
        />
      )}
    </div>
  )
}

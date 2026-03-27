import { useState } from 'react'
import { useOpportunities, useViabilityStudies } from '../hooks/useSupabase'
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

export function OpportunitiesTable() {
  const { opportunities, loading } = useOpportunities(50)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  // Fetch viability for all opportunity listing IDs
  const listingIds = opportunities.map(o => o.listing_id)
  const { studies: viabilityMap } = useViabilityStudies(listingIds)

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
            </tr>
          </thead>
          <tbody>
            {opportunities.map((opp) => {
              const l = (Array.isArray(opp.listing) ? opp.listing[0] : opp.listing) as Listing | undefined
              const isExpanded = expandedId === opp.id
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
                  </tr>
                  {isExpanded && (
                    <tr key={`${opp.id}-detail`} className="border-b border-slate-700/50 bg-slate-900/50">
                      <td colSpan={7}>
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
    </div>
  )
}

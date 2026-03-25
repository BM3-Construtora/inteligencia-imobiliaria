import { useOpportunities } from '../hooks/useSupabase'
import type { Listing } from '../types'

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
}

function fmtArea(n: number | null | undefined): string {
  if (n == null) return '-'
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })} m²`
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-400'
  if (score >= 60) return 'text-yellow-400'
  if (score >= 40) return 'text-orange-400'
  return 'text-slate-400'
}

function scoreBadge(score: number): string {
  if (score >= 80) return 'bg-green-900/50 text-green-300 border-green-700'
  if (score >= 60) return 'bg-yellow-900/50 text-yellow-300 border-yellow-700'
  if (score >= 40) return 'bg-orange-900/50 text-orange-300 border-orange-700'
  return 'bg-slate-800 text-slate-400 border-slate-600'
}

export function OpportunitiesTable() {
  const { opportunities, loading } = useOpportunities(50)

  if (loading) {
    return <div className="text-slate-400 py-8 text-center">Carregando oportunidades...</div>
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="p-5 border-b border-slate-700">
        <h2 className="text-lg font-semibold text-white">Top Oportunidades de Terrenos</h2>
        <p className="text-sm text-slate-400 mt-1">{opportunities.length} terrenos pontuados</p>
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
              return (
                <tr key={opp.id} className="border-b border-slate-700/50 hover:bg-slate-750 hover:bg-slate-700/30">
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
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

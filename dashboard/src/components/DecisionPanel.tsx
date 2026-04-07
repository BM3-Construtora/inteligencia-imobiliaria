import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { Neighborhood } from '../types'

interface MarketIndex {
  metric_name: string
  metric_value: number
  metadata: Record<string, any>
}

function Signal({ label, value, good, unit }: {
  label: string; value: number | null; good: string; unit?: string
}) {
  if (value == null) return (
    <div className="bg-slate-700/50 rounded-lg p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-sm text-slate-500">Sem dados</p>
    </div>
  )

  let color = 'text-yellow-400'
  let bg = 'bg-yellow-900/30 border-yellow-700/50'
  let status = 'Neutro'

  // Parse thresholds from good/bad strings
  if (good === 'high' && value > 5) { color = 'text-green-400'; bg = 'bg-green-900/30 border-green-700/50'; status = 'Bom' }
  else if (good === 'high' && value < 2) { color = 'text-red-400'; bg = 'bg-red-900/30 border-red-700/50'; status = 'Ruim' }
  else if (good === 'low' && value < 6) { color = 'text-green-400'; bg = 'bg-green-900/30 border-green-700/50'; status = 'Bom' }
  else if (good === 'low' && value > 12) { color = 'text-red-400'; bg = 'bg-red-900/30 border-red-700/50'; status = 'Ruim' }

  return (
    <div className={`rounded-lg p-3 border ${bg}`}>
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{value.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}{unit || ''}</p>
      <p className="text-[10px] text-slate-500">{status} — {good === 'high' ? 'quanto maior melhor' : 'quanto menor melhor'}</p>
    </div>
  )
}

export function DecisionPanel() {
  const [neighborhoods, setNeighborhoods] = useState<Neighborhood[]>([])
  const [selected, setSelected] = useState<string>('')
  const [indices, setIndices] = useState<MarketIndex[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const [{ data: neighs }, { data: idxs }] = await Promise.all([
        supabase
          .from('neighborhoods')
          .select('*')
          .gt('total_listings', 3)
          .order('total_listings', { ascending: false })
          .limit(50),
        supabase
          .from('market_indices')
          .select('metric_name, metric_value, metadata')
          .eq('region', 'marilia'),
      ])
      setNeighborhoods(neighs || [])
      setIndices(idxs || [])
      if (neighs?.length) setSelected(neighs[0].name)
      setLoading(false)
    }
    fetch()
  }, [])

  if (loading) return <div className="text-slate-400 py-8 text-center">Carregando painel de decisao...</div>

  const n = neighborhoods.find(x => x.name === selected)
  const sinapi = indices.find(i => i.metric_name === 'sinapi_custo_m2')
  const demandaF2 = indices.find(i => i.metric_name === 'demanda_mcmv_faixa2_anual')
  const deficit = indices.find(i => i.metric_name === 'deficit_habitacional_estimado')
  const rendaMedia = indices.find(i => i.metric_name === 'renda_media_domiciliar')

  // Decision score
  let score = 0
  const reasons: string[] = []
  if (n) {
    if ((n.absorption_rate ?? 0) > 5) { score += 25; reasons.push('Boa absorção') }
    if ((n.months_of_inventory ?? 99) < 12) { score += 25; reasons.push('Estoque baixo') }
    if ((n.avg_price_m2_land ?? 0) > 0 && (n.avg_price_m2_land ?? 0) < 800) { score += 20; reasons.push('Terreno acessível') }
    if ((n.total_listings ?? 0) > 20) { score += 15; reasons.push('Mercado ativo') }
    if ((n.avg_risk_score ?? 5) < 3) { score += 15; reasons.push('Risco baixo') }
  }

  const verdict = score >= 70 ? 'GO' : score >= 40 ? 'AVALIAR' : 'NO-GO'
  const verdictColor = score >= 70 ? 'text-green-400' : score >= 40 ? 'text-yellow-400' : 'text-red-400'
  const verdictBg = score >= 70 ? 'bg-green-900/30 border-green-700' : score >= 40 ? 'bg-yellow-900/30 border-yellow-700' : 'bg-red-900/30 border-red-700'

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-white font-semibold">Painel de Decisao — Devo construir aqui?</h3>
          <p className="text-xs text-slate-400">Selecione um bairro para analise completa</p>
        </div>
        <select
          value={selected}
          onChange={e => setSelected(e.target.value)}
          className="bg-slate-700 text-white text-sm px-3 py-1.5 rounded-md border border-slate-600 focus:border-indigo-500 focus:outline-none"
        >
          {neighborhoods.map(n => (
            <option key={n.name} value={n.name}>{n.name} ({n.total_listings})</option>
          ))}
        </select>
      </div>

      {n && (
        <>
          {/* Verdict */}
          <div className={`rounded-lg border p-4 mb-4 ${verdictBg}`}>
            <div className="flex items-center justify-between">
              <div>
                <p className={`text-2xl font-bold ${verdictColor}`}>{verdict}</p>
                <p className="text-xs text-slate-400 mt-1">Score: {score}/100</p>
              </div>
              <div className="text-right">
                {reasons.map((r, i) => (
                  <p key={i} className="text-xs text-slate-300">{r}</p>
                ))}
              </div>
            </div>
          </div>

          {/* Metrics grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <Signal label="Absorção (%/mês)" value={n.absorption_rate ?? null} good="high" unit="%" />
            <Signal label="Meses de estoque" value={n.months_of_inventory ?? null} good="low" unit=" m" />
            <Signal label="Novos (30d)" value={n.new_last_30d ?? null} good="high" />
            <Signal label="Removidos (30d)" value={n.removed_last_30d ?? null} good="high" />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">Preco/m² terreno</p>
              <p className="text-lg font-bold text-white">
                {n.avg_price_m2_land ? `R$ ${n.avg_price_m2_land.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '-'}
              </p>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">Preco/m² casa</p>
              <p className="text-lg font-bold text-white">
                {n.avg_price_m2_house ? `R$ ${n.avg_price_m2_house.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '-'}
              </p>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">Total imoveis</p>
              <p className="text-lg font-bold text-white">{n.total_listings}</p>
              <p className="text-[10px] text-slate-500">{n.total_land} terrenos | {n.total_houses} casas</p>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">Risco medio</p>
              <p className={`text-lg font-bold ${(n.avg_risk_score ?? 0) >= 3 ? 'text-red-400' : 'text-green-400'}`}>
                {n.avg_risk_score != null ? `${n.avg_risk_score.toFixed(1)}/5` : '-'}
              </p>
            </div>
          </div>

          {/* Macro context */}
          <div className="border-t border-slate-700 pt-3">
            <p className="text-xs text-slate-400 font-medium mb-2">Contexto Macro — Marilia</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-slate-700/30 rounded p-2">
                <p className="text-[10px] text-slate-500">SINAPI/m²</p>
                <p className="text-sm font-bold text-white">{sinapi ? `R$ ${sinapi.metric_value.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '-'}</p>
              </div>
              <div className="bg-slate-700/30 rounded p-2">
                <p className="text-[10px] text-slate-500">Demanda MCMV F2/ano</p>
                <p className="text-sm font-bold text-white">{demandaF2 ? `${demandaF2.metric_value.toLocaleString('pt-BR')} un.` : '-'}</p>
              </div>
              <div className="bg-slate-700/30 rounded p-2">
                <p className="text-[10px] text-slate-500">Deficit habitacional</p>
                <p className="text-sm font-bold text-white">{deficit ? `${deficit.metric_value.toLocaleString('pt-BR')} un.` : '-'}</p>
              </div>
              <div className="bg-slate-700/30 rounded p-2">
                <p className="text-[10px] text-slate-500">Renda media domiciliar</p>
                <p className="text-sm font-bold text-white">{rendaMedia ? `R$ ${rendaMedia.metric_value.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '-'}</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

interface MarketIndex {
  id: number
  source: string
  region: string
  period: string
  metric_name: string
  metric_value: number
  metadata: Record<string, any>
}

const METRIC_LABELS: Record<string, string> = {
  preco_mediano_m2_terreno: 'Preco Mediano/m² Terreno',
  preco_mediano_m2_casa: 'Preco Mediano/m² Casa',
  preco_mediano_m2_apartamento: 'Preco Mediano/m² Apto',
  volume_vendas_mensal: 'Volume Vendas/Mes',
  tempo_medio_venda_dias: 'Tempo Medio Venda',
  variacao_preco_anual_pct: 'Variacao Anual',
  taxa_vacancia_pct: 'Taxa Vacancia',
  lancamentos_novos: 'Lancamentos Novos',
  median_price_m2_land: 'Preco Mediano/m² Terreno',
  median_price_m2_house: 'Preco Mediano/m² Casa',
  sales_volume: 'Volume de Vendas',
  avg_days_on_market: 'Dias no Mercado',
}

function formatValue(metric: MarketIndex): string {
  const unit = metric.metadata?.unit || ''
  const val = metric.metric_value

  if (unit.includes('%') || metric.metric_name.includes('pct')) {
    return `${val.toFixed(1)}%`
  }
  if (unit.includes('R$') || metric.metric_name.includes('preco')) {
    return `R$ ${val.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
  }
  if (unit.includes('dias') || metric.metric_name.includes('dias')) {
    return `${val.toFixed(0)} dias`
  }
  return val.toLocaleString('pt-BR', { maximumFractionDigits: 0 })
}

export function MarketBenchmarks() {
  const [indices, setIndices] = useState<MarketIndex[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const { data } = await supabase
        .from('market_indices')
        .select('*')
        .eq('region', 'marilia')
        .order('period', { ascending: false })
        .limit(20)

      setIndices(data || [])
      setLoading(false)
    }
    fetch()
  }, [])

  if (loading) {
    return <div className="text-slate-400 py-4 text-center">Carregando benchmarks...</div>
  }

  if (indices.length === 0) {
    return null
  }

  // Group by period
  const byPeriod = new Map<string, MarketIndex[]>()
  indices.forEach(i => {
    const list = byPeriod.get(i.period) || []
    list.push(i)
    byPeriod.set(i.period, list)
  })

  const latestPeriod = Array.from(byPeriod.keys())[0]
  const latestMetrics = byPeriod.get(latestPeriod) || []

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-white font-semibold">Benchmarks de Mercado — CRECI-SP</h3>
          <p className="text-xs text-slate-400">
            Periodo: {latestPeriod} | Fonte: CRECI-SP
            {latestMetrics[0]?.metadata?.estimated && (
              <span className="ml-2 text-amber-400">(estimativa)</span>
            )}
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {latestMetrics.map(m => (
          <div key={m.id} className="bg-slate-700/50 rounded-lg p-3">
            <p className="text-xs text-slate-400 mb-1">
              {METRIC_LABELS[m.metric_name] || m.metric_name.replace(/_/g, ' ')}
            </p>
            <p className="text-lg font-bold text-white">{formatValue(m)}</p>
            {m.metadata?.context && (
              <p className="text-[10px] text-slate-500 mt-0.5">{m.metadata.context}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts'
import { supabase } from '../lib/supabase'

interface TrendPoint {
  date: string
  [neighborhood: string]: string | number | null
}

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#ef4444', '#6366f1']

export function PriceTrend() {
  const [data, setData] = useState<TrendPoint[]>([])
  const [neighborhoods, setNeighborhoods] = useState<string[]>([])
  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<string[]>([])
  const [propertyType, setPropertyType] = useState<string>('land')
  const [loading, setLoading] = useState(true)

  // Fetch available neighborhoods
  useEffect(() => {
    supabase
      .from('neighborhoods')
      .select('name, total_listings')
      .gt('total_listings', 5)
      .order('total_listings', { ascending: false })
      .limit(30)
      .then(({ data }) => {
        const names = data?.map(r => r.name) || []
        setNeighborhoods(names)
        setSelectedNeighborhoods(names.slice(0, 3))
      })
  }, [])

  // Fetch time series data
  useEffect(() => {
    if (selectedNeighborhoods.length === 0) return
    setLoading(true)

    async function fetch() {
      const { data: snapshots } = await supabase
        .from('market_snapshots')
        .select('snapshot_date, neighborhood, avg_price_m2')
        .eq('property_type', propertyType)
        .in('neighborhood', selectedNeighborhoods)
        .not('avg_price_m2', 'is', null)
        .order('snapshot_date', { ascending: true })

      if (!snapshots) { setLoading(false); return }

      // Pivot: date → { neighborhood: price }
      const dateMap = new Map<string, TrendPoint>()
      snapshots.forEach(s => {
        if (!s.neighborhood || !s.avg_price_m2) return
        let point = dateMap.get(s.snapshot_date)
        if (!point) {
          point = { date: s.snapshot_date }
          dateMap.set(s.snapshot_date, point)
        }
        point[s.neighborhood] = Math.round(s.avg_price_m2)
      })

      setData(Array.from(dateMap.values()))
      setLoading(false)
    }
    fetch()
  }, [selectedNeighborhoods, propertyType])

  const toggleNeighborhood = (name: string) => {
    setSelectedNeighborhoods(prev =>
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name].slice(0, 6)
    )
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-white font-semibold">Tendencia de Preco/m² por Bairro</h3>
          <p className="text-xs text-slate-400">Evolucao temporal — selecione ate 6 bairros</p>
        </div>
        <div className="flex gap-1">
          {[['land', 'Terrenos'], ['house', 'Casas'], ['apartment', 'Aptos']].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setPropertyType(key)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${
                propertyType === key
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Neighborhood selector */}
      <div className="flex flex-wrap gap-1 mb-4 max-h-16 overflow-y-auto">
        {neighborhoods.map((n, i) => (
          <button
            key={n}
            onClick={() => toggleNeighborhood(n)}
            className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
              selectedNeighborhoods.includes(n)
                ? 'text-white font-medium'
                : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
            style={selectedNeighborhoods.includes(n)
              ? { backgroundColor: COLORS[selectedNeighborhoods.indexOf(n) % COLORS.length] }
              : undefined}
          >
            {n.length > 18 ? n.slice(0, 16) + '..' : n}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-slate-400 py-8 text-center">Carregando tendencias...</div>
      ) : data.length === 0 ? (
        <div className="text-slate-400 py-8 text-center text-sm">Sem dados historicos para os bairros selecionados.</div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ left: 10, right: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              tickFormatter={d => d.slice(5)}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              tickFormatter={v => `R$${v}`}
            />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
              formatter={(value: number) => [`R$ ${value.toLocaleString('pt-BR')}/m²`, '']}
            />
            <Legend />
            {selectedNeighborhoods.map((n, i) => (
              <Line
                key={n}
                type="monotone"
                dataKey={n}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

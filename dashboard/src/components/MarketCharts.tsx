import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import { useMarketSnapshots, useNeighborhoods } from '../hooks/useSupabase'

const TYPE_LABELS: Record<string, string> = {
  house: 'Casas',
  apartment: 'Aptos',
  land: 'Terrenos',
  condo_house: 'Cond.',
  commercial: 'Comercial',
  farm: 'Chácara',
  rural: 'Rural',
}

const TYPE_COLORS: Record<string, string> = {
  house: '#3b82f6',
  apartment: '#8b5cf6',
  land: '#10b981',
  condo_house: '#6366f1',
  commercial: '#f59e0b',
  farm: '#84cc16',
  rural: '#14b8a6',
}

function fmt(n: number | null): string {
  if (n == null) return '-'
  return `R$ ${(n / 1000).toFixed(0)}k`
}

export function MarketCharts() {
  const { snapshots, loading: loadingSnap } = useMarketSnapshots()
  const { neighborhoods, loading: loadingNeigh } = useNeighborhoods()

  if (loadingSnap || loadingNeigh) {
    return <div className="text-slate-400 py-8 text-center">Carregando métricas...</div>
  }

  const typeData = snapshots
    .filter(s => s.property_type && s.total_listings > 0)
    .map(s => ({
      name: TYPE_LABELS[s.property_type!] || s.property_type,
      type: s.property_type!,
      total: s.total_listings,
      avgPrice: s.avg_price,
      medianPrice: s.median_price,
      avgPriceM2: s.avg_price_m2,
    }))
    .sort((a, b) => b.total - a.total)

  const neighData = neighborhoods
    .filter(n => n.avg_price_m2_land != null && n.avg_price_m2_land > 0)
    .slice(0, 15)
    .map(n => ({
      name: n.name.length > 18 ? n.name.slice(0, 16) + '...' : n.name,
      fullName: n.name,
      priceM2: n.avg_price_m2_land,
      count: n.total_land,
    }))
    .sort((a, b) => (a.priceM2 ?? 0) - (b.priceM2 ?? 0))

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Listings by Type */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <h3 className="text-white font-semibold mb-4">Listings por Tipo</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={typeData} layout="vertical" margin={{ left: 10, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} />
            <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} width={80} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(value: any) => [Number(value).toLocaleString('pt-BR'), 'Listings']}
            />
            <Bar dataKey="total" radius={[0, 4, 4, 0]}>
              {typeData.map((entry) => (
                <Cell key={entry.type} fill={TYPE_COLORS[entry.type] || '#64748b'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Avg Price by Type */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <h3 className="text-white font-semibold mb-4">Preco Médio por Tipo</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={typeData} layout="vertical" margin={{ left: 10, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              type="number"
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              tickFormatter={(v) => fmt(v)}
            />
            <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} width={80} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(value: any) => [`R$ ${Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`, 'Preço Médio']}
            />
            <Bar dataKey="medianPrice" radius={[0, 4, 4, 0]}>
              {typeData.map((entry) => (
                <Cell key={entry.type} fill={TYPE_COLORS[entry.type] || '#64748b'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Neighborhoods price/m2 for land */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5 lg:col-span-2">
        <h3 className="text-white font-semibold mb-1">Preco/m² de Terrenos por Bairro</h3>
        <p className="text-xs text-slate-400 mb-4">Top 15 bairros com terrenos (ordenado por preco/m²)</p>
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={neighData} margin={{ left: 10, right: 20, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="name"
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              angle={-35}
              textAnchor="end"
              height={60}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              tickFormatter={(v) => `R$${v}`}
            />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(value: any) => [`R$ ${Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}/m²`, 'Preço']}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              labelFormatter={(label: any) => {
                const item = neighData.find(n => n.name === label)
                return item?.fullName || label
              }}
            />
            <Bar dataKey="priceM2" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

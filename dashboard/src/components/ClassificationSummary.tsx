import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'

const TIER_CONFIG: Record<string, { label: string; color: string; order: number }> = {
  terreno_economico: { label: 'Terreno Econ.', color: '#10b981', order: 1 },
  terreno_medio: { label: 'Terreno Med.', color: '#059669', order: 2 },
  terreno_alto: { label: 'Terreno Alto', color: '#047857', order: 3 },
  terreno_grande: { label: 'Terreno Grande', color: '#065f46', order: 4 },
  casa_mcmv: { label: 'Casa MCMV', color: '#f59e0b', order: 5 },
  casa_baixo_padrao: { label: 'Casa Baixo', color: '#3b82f6', order: 6 },
  casa_medio_padrao: { label: 'Casa Medio', color: '#6366f1', order: 7 },
  casa_alto_padrao: { label: 'Casa Alto', color: '#8b5cf6', order: 8 },
  apto_economico: { label: 'Apto Econ.', color: '#ec4899', order: 9 },
  apto_medio: { label: 'Apto Med.', color: '#db2777', order: 10 },
  apto_alto: { label: 'Apto Alto', color: '#be185d', order: 11 },
}

interface Props {
  tiers: Record<string, number>
  loading: boolean
}

export function ClassificationSummary({ tiers, loading }: Props) {
  if (loading) {
    return <div className="text-slate-400 py-4 text-center">Carregando classificacao...</div>
  }

  const total = Object.values(tiers).reduce((a, b) => a + b, 0)
  if (total === 0) {
    return null
  }

  const data = Object.entries(tiers)
    .map(([tier, count]) => ({
      tier,
      label: TIER_CONFIG[tier]?.label || tier,
      count,
      color: TIER_CONFIG[tier]?.color || '#64748b',
      order: TIER_CONFIG[tier]?.order || 99,
    }))
    .sort((a, b) => a.order - b.order)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-white font-semibold">Classificacao por Padrao</h3>
          <p className="text-xs text-slate-400">{total.toLocaleString('pt-BR')} imoveis classificados</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ left: 10, right: 20, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="label"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            angle={-35}
            textAnchor="end"
            height={60}
          />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
          <Tooltip
            contentStyle={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 8,
              color: '#e2e8f0',
            }}
            formatter={(value) => [
              typeof value === 'number' ? value.toLocaleString('pt-BR') : String(value ?? ''),
              'Imoveis',
            ]}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map(entry => (
              <Cell key={entry.tier} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

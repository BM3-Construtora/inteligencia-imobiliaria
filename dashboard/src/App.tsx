import { StatCard } from './components/StatCard'
import { OpportunitiesTable } from './components/OpportunitiesTable'
import { MarketCharts } from './components/MarketCharts'
import { useStats } from './hooks/useSupabase'

function fmt(n: number): string {
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
}

const SOURCE_LABELS: Record<string, string> = {
  uniao: 'União',
  toca: 'Toca',
  vivareal: 'VivaReal',
  chavesnamao: 'Chaves na Mão',
  imovelweb: 'Imovelweb',
}

function App() {
  const { stats, loading } = useStats()

  return (
    <div className="min-h-screen bg-slate-900">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">MariliaBot</h1>
            <p className="text-xs text-slate-400">Inteligência Imobiliária — Marília/SP</p>
          </div>
          <div className="flex gap-2 flex-wrap justify-end">
            {Object.entries(stats.sources).map(([source, count]) => (
              <span key={source} className="text-xs bg-slate-800 text-slate-300 px-2 py-1 rounded border border-slate-700">
                {SOURCE_LABELS[source] || source}: {count}
              </span>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {loading ? (
          <div className="text-slate-400 text-center py-8">Carregando...</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Total Imóveis"
              value={stats.totalListings.toLocaleString('pt-BR')}
              sub={`${Object.keys(stats.sources).length} fontes`}
            />
            <StatCard
              label="Terrenos"
              value={stats.totalLand.toLocaleString('pt-BR')}
              sub={`${((stats.totalLand / stats.totalListings) * 100).toFixed(1)}% do total`}
            />
            <StatCard
              label="Oportunidades"
              value={stats.totalOpportunities.toLocaleString('pt-BR')}
              sub="score >= 30"
            />
            <StatCard
              label="Preço Médio/m² (Terrenos)"
              value={fmt(stats.avgPriceM2Land)}
              sub="terrenos ativos"
            />
          </div>
        )}

        <MarketCharts />

        <OpportunitiesTable />
      </main>

      <footer className="border-t border-slate-800 py-6 text-center text-xs text-slate-500">
        MariliaBot — Pipeline: collect → normalize → analyze → hunt
      </footer>
    </div>
  )
}

export default App

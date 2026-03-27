import { StatCard } from './components/StatCard'
import { OpportunitiesTable } from './components/OpportunitiesTable'
import { MarketCharts } from './components/MarketCharts'
import { ClassificationSummary } from './components/ClassificationSummary'
import { PropertyMap } from './components/PropertyMap'
import { FilterBar } from './components/FilterBar'
import { MarketBenchmarks } from './components/MarketBenchmarks'
import { PriceTrend } from './components/PriceTrend'
import { DecisionPanel } from './components/DecisionPanel'
import { FilterProvider, useFilters } from './contexts/FilterContext'
import { useFilteredStats } from './hooks/useFilteredData'

function fmt(n: number): string {
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
}

const SOURCE_LABELS: Record<string, string> = {
  uniao: 'Uniao',
  toca: 'Toca',
  vivareal: 'VivaReal',
  chavesnamao: 'Chaves na Mao',
  imovelweb: 'Imovelweb',
  zapimoveis: 'ZAP',
}

function Dashboard() {
  const { data: stats, loading } = useFilteredStats()
  const { activeFilterCount } = useFilters()

  return (
    <div className="min-h-screen bg-slate-900">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-[1001]">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">MariliaBot</h1>
            <p className="text-xs text-slate-400">
              Inteligencia Imobiliaria — Marilia/SP
              {activeFilterCount > 0 && (
                <span className="ml-2 text-indigo-400">({activeFilterCount} filtro{activeFilterCount > 1 ? 's' : ''} ativo{activeFilterCount > 1 ? 's' : ''})</span>
              )}
            </p>
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

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        <FilterBar />

        {loading ? (
          <div className="text-slate-400 text-center py-8">Carregando...</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <StatCard
              label="Total Imoveis"
              value={stats.totalListings.toLocaleString('pt-BR')}
              sub={`${Object.keys(stats.sources).length} fontes`}
            />
            <StatCard
              label="Terrenos"
              value={stats.totalLand.toLocaleString('pt-BR')}
              sub={stats.totalListings > 0 ? `${((stats.totalLand / stats.totalListings) * 100).toFixed(1)}% do total` : '-'}
            />
            <StatCard
              label="Casas"
              value={stats.totalHouses.toLocaleString('pt-BR')}
              sub={stats.totalListings > 0 ? `${((stats.totalHouses / stats.totalListings) * 100).toFixed(1)}% do total` : '-'}
            />
            <StatCard
              label="Oportunidades"
              value={stats.totalOpportunities.toLocaleString('pt-BR')}
              sub="score >= 30"
            />
            <StatCard
              label="Preco Medio/m² (Terrenos)"
              value={stats.avgPriceM2Land > 0 ? fmt(stats.avgPriceM2Land) : '-'}
              sub="terrenos ativos"
            />
          </div>
        )}

        <DecisionPanel />

        <ClassificationSummary tiers={stats.tiers} loading={loading} />

        <PropertyMap />

        <PriceTrend />

        <MarketBenchmarks />

        <MarketCharts />

        <OpportunitiesTable />
      </main>

      <footer className="border-t border-slate-800 py-6 text-center text-xs text-slate-500">
        MariliaBot — Pipeline: collect → normalize → classify → analyze → hunt
      </footer>
    </div>
  )
}

function App() {
  return (
    <FilterProvider>
      <Dashboard />
    </FilterProvider>
  )
}

export default App

import { useState } from 'react'
import { Building, Home, Landmark, Trophy, DollarSign } from 'lucide-react'
import { StatCard } from './components/StatCard'
import { OpportunitiesTable } from './components/OpportunitiesTable'
import { MarketCharts } from './components/MarketCharts'
import { ClassificationSummary } from './components/ClassificationSummary'
import { PropertyMap } from './components/PropertyMap'
import { FilterBar } from './components/FilterBar'
import { MarketBenchmarks } from './components/MarketBenchmarks'
import { PriceTrend } from './components/PriceTrend'
import { DecisionPanel } from './components/DecisionPanel'
import { ViabilityCalculator } from './components/ViabilityCalculator'
import { Sidebar, type Page } from './components/Sidebar'
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

const PAGE_TITLES: Record<Page, { title: string; subtitle: string }> = {
  overview: { title: 'Visao Geral', subtitle: 'Resumo do mercado imobiliario de Marilia/SP' },
  map: { title: 'Mapa de Bairros', subtitle: 'Visualizacao geografica dos bairros e precos' },
  decision: { title: 'Painel de Decisao', subtitle: 'Analise se vale construir em determinado bairro' },
  viability: { title: 'Calculadora de Viabilidade', subtitle: 'Simule projetos e calcule retorno' },
  market: { title: 'Analise de Mercado', subtitle: 'Graficos, tendencias e benchmarks' },
  opportunities: { title: 'Oportunidades', subtitle: 'Melhores terrenos ranqueados por score' },
}

function Dashboard() {
  const { data: stats, loading } = useFilteredStats()
  const { activeFilterCount } = useFilters()
  const [activePage, setActivePage] = useState<Page>('overview')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const pageInfo = PAGE_TITLES[activePage]

  return (
    <div className="min-h-screen bg-slate-950">
      <Sidebar
        activePage={activePage}
        onPageChange={(page) => { setActivePage(page); setFiltersOpen(false) }}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      {/* Main content area - offset by sidebar */}
      <div className={`transition-all duration-300 ${sidebarCollapsed ? 'ml-16' : 'ml-56'}`}>
        {/* Top bar */}
        <header className="sticky top-0 z-[1001] bg-slate-950/80 backdrop-blur-xl border-b border-slate-800/50">
          <div className="px-8 py-4 flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-white">{pageInfo.title}</h1>
              <p className="text-xs text-slate-500">{pageInfo.subtitle}</p>
            </div>
            <div className="flex items-center gap-4">
              {/* Source badges */}
              <div className="hidden lg:flex gap-1.5 flex-wrap justify-end">
                {Object.entries(stats.sources).map(([source, count]) => (
                  <span key={source} className="text-[10px] bg-slate-800/80 text-slate-400 px-2 py-1 rounded-md border border-slate-800">
                    {SOURCE_LABELS[source] || source}: {count}
                  </span>
                ))}
              </div>
              {/* Filter button */}
              <FilterBar open={filtersOpen} onToggle={() => setFiltersOpen(!filtersOpen)} />
            </div>
          </div>

          {/* Active filters summary */}
          {activeFilterCount > 0 && !filtersOpen && (
            <div className="px-8 pb-3 -mt-1">
              <p className="text-xs text-indigo-400">
                {activeFilterCount} filtro{activeFilterCount > 1 ? 's' : ''} ativo{activeFilterCount > 1 ? 's' : ''} — os dados exibidos estao filtrados
              </p>
            </div>
          )}
        </header>

        {/* Page content */}
        <main className="px-8 py-6 space-y-6">
          {/* Filters panel (rendered below header when open) */}
          {filtersOpen && <div className="mb-2" />}

          {/* OVERVIEW PAGE */}
          {activePage === 'overview' && (
            <>
              {loading ? (
                <LoadingState />
              ) : (
                <>
                  <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                    <StatCard
                      label="Total Imoveis"
                      value={stats.totalListings.toLocaleString('pt-BR')}
                      sub={`${Object.keys(stats.sources).length} fontes`}
                      icon={Building}
                      accent="indigo"
                    />
                    <StatCard
                      label="Terrenos"
                      value={stats.totalLand.toLocaleString('pt-BR')}
                      sub={stats.totalListings > 0 ? `${((stats.totalLand / stats.totalListings) * 100).toFixed(1)}% do total` : '-'}
                      icon={Landmark}
                      accent="emerald"
                    />
                    <StatCard
                      label="Casas"
                      value={stats.totalHouses.toLocaleString('pt-BR')}
                      sub={stats.totalListings > 0 ? `${((stats.totalHouses / stats.totalListings) * 100).toFixed(1)}% do total` : '-'}
                      icon={Home}
                      accent="sky"
                    />
                    <StatCard
                      label="Oportunidades"
                      value={stats.totalOpportunities.toLocaleString('pt-BR')}
                      sub="score >= 30"
                      icon={Trophy}
                      accent="amber"
                    />
                    <StatCard
                      label="Preco Medio/m²"
                      value={stats.avgPriceM2Land > 0 ? fmt(stats.avgPriceM2Land) : '-'}
                      sub="terrenos ativos"
                      icon={DollarSign}
                      accent="rose"
                    />
                  </div>

                  <ClassificationSummary tiers={stats.tiers} loading={loading} />

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    <PropertyMap />
                    <div className="space-y-6">
                      <PriceTrend />
                    </div>
                  </div>

                  <MarketBenchmarks />
                </>
              )}
            </>
          )}

          {/* MAP PAGE */}
          {activePage === 'map' && <PropertyMap />}

          {/* DECISION PAGE */}
          {activePage === 'decision' && <DecisionPanel />}

          {/* VIABILITY PAGE */}
          {activePage === 'viability' && <ViabilityCalculator />}

          {/* MARKET PAGE */}
          {activePage === 'market' && (
            <>
              <PriceTrend />
              <MarketBenchmarks />
              <MarketCharts />
              {!loading && <ClassificationSummary tiers={stats.tiers} loading={loading} />}
            </>
          )}

          {/* OPPORTUNITIES PAGE */}
          {activePage === 'opportunities' && <OpportunitiesTable />}
        </main>

        {/* Footer */}
        <footer className="border-t border-slate-800/50 py-4 px-8 text-center">
          <p className="text-[10px] text-slate-600">
            MariliaBot — Pipeline: collect → normalize → classify → analyze → hunt
          </p>
        </footer>
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-3" />
        <p className="text-slate-400 text-sm">Carregando dados...</p>
      </div>
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

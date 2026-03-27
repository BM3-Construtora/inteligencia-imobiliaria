import { useState, useEffect } from 'react'
import { useFilters } from '../contexts/FilterContext'
import { supabase } from '../lib/supabase'
import { SlidersHorizontal, X, Search, RotateCcw } from 'lucide-react'

const PROPERTY_TYPES = [
  { value: 'land', label: 'Terrenos' },
  { value: 'house', label: 'Casas' },
  { value: 'condo_house', label: 'Condominio' },
  { value: 'apartment', label: 'Apartamentos' },
  { value: 'commercial', label: 'Comercial' },
]

const MARKET_TIERS = [
  { value: 'terreno_economico', label: 'Terreno Econ.', group: 'Terrenos' },
  { value: 'terreno_medio', label: 'Terreno Med.', group: 'Terrenos' },
  { value: 'terreno_alto', label: 'Terreno Alto', group: 'Terrenos' },
  { value: 'terreno_grande', label: 'Terreno Grande', group: 'Terrenos' },
  { value: 'casa_mcmv', label: 'Casa MCMV', group: 'Casas' },
  { value: 'casa_baixo_padrao', label: 'Casa Baixo', group: 'Casas' },
  { value: 'casa_medio_padrao', label: 'Casa Medio', group: 'Casas' },
  { value: 'casa_alto_padrao', label: 'Casa Alto', group: 'Casas' },
  { value: 'apto_economico', label: 'Apto Econ.', group: 'Aptos' },
  { value: 'apto_medio', label: 'Apto Med.', group: 'Aptos' },
  { value: 'apto_alto', label: 'Apto Alto', group: 'Aptos' },
]

const SOURCES = [
  { value: 'uniao', label: 'Uniao' },
  { value: 'toca', label: 'Toca' },
  { value: 'vivareal', label: 'VivaReal' },
  { value: 'chavesnamao', label: 'Chaves na Mao' },
  { value: 'imovelweb', label: 'Imovelweb' },
  { value: 'zapimoveis', label: 'ZAP' },
]

const PRICE_RANGES = [
  { label: 'Ate R$100k', min: 0, max: 100000 },
  { label: 'R$100-200k', min: 100000, max: 200000 },
  { label: 'R$200-350k', min: 200000, max: 350000 },
  { label: 'R$350-500k', min: 350000, max: 500000 },
  { label: 'R$500k-1M', min: 500000, max: 1000000 },
  { label: 'R$1M+', min: 1000000, max: null },
]

const AREA_RANGES = [
  { label: 'Ate 150m²', min: 0, max: 150 },
  { label: '150-300m²', min: 150, max: 300 },
  { label: '300-500m²', min: 300, max: 500 },
  { label: '500-1000m²', min: 500, max: 1000 },
  { label: '1000m²+', min: 1000, max: null },
]

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-all ${
        active
          ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
          : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200 border border-slate-700'
      }`}
    >
      {label}
    </button>
  )
}

function toggleInArray(arr: string[], val: string): string[] {
  return arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val]
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <label className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider mb-2 block">
      {children}
    </label>
  )
}

interface FilterBarProps {
  open: boolean
  onToggle: () => void
}

export function FilterBar({ open, onToggle }: FilterBarProps) {
  const { filters, updateFilter, resetFilters, activeFilterCount } = useFilters()
  const [neighborhoodOptions, setNeighborhoodOptions] = useState<string[]>([])
  const [neighSearch, setNeighSearch] = useState('')

  useEffect(() => {
    supabase
      .from('neighborhoods')
      .select('name')
      .gt('total_listings', 0)
      .order('total_listings', { ascending: false })
      .limit(100)
      .then(({ data }) => {
        setNeighborhoodOptions(data?.map(r => r.name) || [])
      })
  }, [])

  const filteredNeighborhoods = neighSearch
    ? neighborhoodOptions.filter(n => n.toLowerCase().includes(neighSearch.toLowerCase()))
    : neighborhoodOptions.slice(0, 20)

  return (
    <>
      {/* Filter toggle button */}
      <button
        onClick={onToggle}
        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
          open
            ? 'bg-indigo-600 text-white'
            : 'bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700'
        }`}
      >
        <SlidersHorizontal className="w-4 h-4" />
        <span>Filtros</span>
        {activeFilterCount > 0 && (
          <span className="bg-white/20 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
            {activeFilterCount}
          </span>
        )}
      </button>

      {/* Filter panel */}
      {open && (
        <div className="bg-slate-900/95 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-6 shadow-2xl shadow-black/20">
          {/* Panel header */}
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-indigo-400" />
              <h3 className="text-white font-semibold text-sm">Filtros Avancados</h3>
              {activeFilterCount > 0 && (
                <span className="text-xs text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-full">
                  {activeFilterCount} ativo{activeFilterCount > 1 ? 's' : ''}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {activeFilterCount > 0 && (
                <button
                  onClick={resetFilters}
                  className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors px-2 py-1 rounded-md hover:bg-slate-800"
                >
                  <RotateCcw className="w-3 h-3" />
                  Limpar todos
                </button>
              )}
              <button
                onClick={onToggle}
                className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left column */}
            <div className="space-y-5">
              {/* Property Type */}
              <div>
                <SectionTitle>Tipo de Imovel</SectionTitle>
                <div className="flex flex-wrap gap-2">
                  {PROPERTY_TYPES.map(t => (
                    <Chip
                      key={t.value}
                      label={t.label}
                      active={filters.propertyType.includes(t.value)}
                      onClick={() => updateFilter('propertyType', toggleInArray(filters.propertyType, t.value))}
                    />
                  ))}
                </div>
              </div>

              {/* Sources */}
              <div>
                <SectionTitle>Fonte</SectionTitle>
                <div className="flex flex-wrap gap-2">
                  {SOURCES.map(s => (
                    <Chip
                      key={s.value}
                      label={s.label}
                      active={filters.sources.includes(s.value)}
                      onClick={() => updateFilter('sources', toggleInArray(filters.sources, s.value))}
                    />
                  ))}
                </div>
              </div>

              {/* Price ranges */}
              <div>
                <SectionTitle>Faixa de Preco</SectionTitle>
                <div className="flex flex-wrap gap-2">
                  {PRICE_RANGES.map(r => {
                    const active = filters.priceMin === r.min && filters.priceMax === r.max
                    return (
                      <Chip
                        key={r.label}
                        label={r.label}
                        active={active}
                        onClick={() => {
                          if (active) {
                            updateFilter('priceMin', null)
                            updateFilter('priceMax', null)
                          } else {
                            updateFilter('priceMin', r.min)
                            updateFilter('priceMax', r.max)
                          }
                        }}
                      />
                    )
                  })}
                </div>
              </div>

              {/* Area ranges */}
              <div>
                <SectionTitle>Faixa de Area</SectionTitle>
                <div className="flex flex-wrap gap-2">
                  {AREA_RANGES.map(r => {
                    const active = filters.areaMin === r.min && filters.areaMax === r.max
                    return (
                      <Chip
                        key={r.label}
                        label={r.label}
                        active={active}
                        onClick={() => {
                          if (active) {
                            updateFilter('areaMin', null)
                            updateFilter('areaMax', null)
                          } else {
                            updateFilter('areaMin', r.min)
                            updateFilter('areaMax', r.max)
                          }
                        }}
                      />
                    )
                  })}
                </div>
              </div>
            </div>

            {/* Right column */}
            <div className="space-y-5">
              {/* Classification */}
              <div>
                <SectionTitle>Classificacao de Mercado</SectionTitle>
                {['Terrenos', 'Casas', 'Aptos'].map(group => (
                  <div key={group} className="mb-2">
                    <p className="text-[10px] text-slate-600 font-medium mb-1">{group}</p>
                    <div className="flex flex-wrap gap-2">
                      {MARKET_TIERS.filter(t => t.group === group).map(t => (
                        <Chip
                          key={t.value}
                          label={t.label}
                          active={filters.marketTier.includes(t.value)}
                          onClick={() => updateFilter('marketTier', toggleInArray(filters.marketTier, t.value))}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {/* Date range + MCMV */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <SectionTitle>Periodo</SectionTitle>
                  <div className="space-y-2">
                    <input
                      type="date"
                      value={filters.dateFrom || ''}
                      onChange={e => updateFilter('dateFrom', e.target.value || null)}
                      className="w-full bg-slate-800 text-slate-200 text-xs px-3 py-2 rounded-lg border border-slate-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                    />
                    <input
                      type="date"
                      value={filters.dateTo || ''}
                      onChange={e => updateFilter('dateTo', e.target.value || null)}
                      className="w-full bg-slate-800 text-slate-200 text-xs px-3 py-2 rounded-lg border border-slate-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                    />
                  </div>
                </div>
                <div>
                  <SectionTitle>MCMV</SectionTitle>
                  <div className="space-y-2">
                    <Chip label="Todos" active={filters.isMcmv === null} onClick={() => updateFilter('isMcmv', null)} />
                    <Chip label="Apenas MCMV" active={filters.isMcmv === true} onClick={() => updateFilter('isMcmv', true)} />
                    <Chip label="Sem MCMV" active={filters.isMcmv === false} onClick={() => updateFilter('isMcmv', false)} />
                  </div>
                </div>
              </div>

              {/* Neighborhood */}
              <div>
                <SectionTitle>
                  Bairro {filters.neighborhoods.length > 0 && (
                    <span className="text-indigo-400 normal-case">({filters.neighborhoods.length} selecionado{filters.neighborhoods.length > 1 ? 's' : ''})</span>
                  )}
                </SectionTitle>
                <div className="relative mb-2">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text"
                    value={neighSearch}
                    onChange={e => setNeighSearch(e.target.value)}
                    placeholder="Buscar bairro..."
                    className="w-full bg-slate-800 text-slate-200 text-xs pl-8 pr-3 py-2 rounded-lg border border-slate-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                  />
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto pr-1">
                  {filteredNeighborhoods.map(n => (
                    <Chip
                      key={n}
                      label={n.length > 20 ? n.slice(0, 18) + '..' : n}
                      active={filters.neighborhoods.includes(n)}
                      onClick={() => updateFilter('neighborhoods', toggleInArray(filters.neighborhoods, n))}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

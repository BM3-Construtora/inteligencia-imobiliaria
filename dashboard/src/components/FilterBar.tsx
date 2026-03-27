import { useState, useEffect } from 'react'
import { useFilters, DEFAULT_FILTERS } from '../contexts/FilterContext'
import { supabase } from '../lib/supabase'

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

function ToggleChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 text-xs rounded-md transition-all ${
        active
          ? 'bg-indigo-600 text-white shadow-sm'
          : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
      }`}
    >
      {label}
    </button>
  )
}

function toggleInArray(arr: string[], val: string): string[] {
  return arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val]
}

export function FilterBar() {
  const { filters, updateFilter, resetFilters, activeFilterCount } = useFilters()
  const [expanded, setExpanded] = useState(false)
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
    <div className="bg-slate-800 rounded-xl border border-slate-700">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-5 py-3 flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-3">
          <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
          <span className="text-white font-semibold text-sm">Filtros</span>
          {activeFilterCount > 0 && (
            <span className="bg-indigo-600 text-white text-xs px-2 py-0.5 rounded-full">
              {activeFilterCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <button
              onClick={(e) => { e.stopPropagation(); resetFilters() }}
              className="text-xs text-slate-400 hover:text-white transition-colors"
            >
              Limpar
            </button>
          )}
          <svg
            className={`w-4 h-4 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Expanded filters */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-slate-700 pt-4">
          {/* Row 1: Property Type + Source */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">Tipo de Imovel</label>
              <div className="flex flex-wrap gap-1.5">
                {PROPERTY_TYPES.map(t => (
                  <ToggleChip
                    key={t.value}
                    label={t.label}
                    active={filters.propertyType.includes(t.value)}
                    onClick={() => updateFilter('propertyType', toggleInArray(filters.propertyType, t.value))}
                  />
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">Fonte</label>
              <div className="flex flex-wrap gap-1.5">
                {SOURCES.map(s => (
                  <ToggleChip
                    key={s.value}
                    label={s.label}
                    active={filters.sources.includes(s.value)}
                    onClick={() => updateFilter('sources', toggleInArray(filters.sources, s.value))}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Row 2: Market Tier */}
          <div>
            <label className="text-xs text-slate-400 font-medium mb-1.5 block">Classificacao</label>
            <div className="flex flex-wrap gap-1.5">
              {MARKET_TIERS.map(t => (
                <ToggleChip
                  key={t.value}
                  label={t.label}
                  active={filters.marketTier.includes(t.value)}
                  onClick={() => updateFilter('marketTier', toggleInArray(filters.marketTier, t.value))}
                />
              ))}
            </div>
          </div>

          {/* Row 3: Price + Area ranges */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">Faixa de Preco</label>
              <div className="flex flex-wrap gap-1.5">
                {PRICE_RANGES.map(r => {
                  const active = filters.priceMin === r.min && filters.priceMax === r.max
                  return (
                    <ToggleChip
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
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">Faixa de Area</label>
              <div className="flex flex-wrap gap-1.5">
                {AREA_RANGES.map(r => {
                  const active = filters.areaMin === r.min && filters.areaMax === r.max
                  return (
                    <ToggleChip
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

          {/* Row 4: Date range + MCMV + Neighborhood */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">Periodo</label>
              <div className="flex gap-2">
                <input
                  type="date"
                  value={filters.dateFrom || ''}
                  onChange={e => updateFilter('dateFrom', e.target.value || null)}
                  className="flex-1 bg-slate-700 text-slate-200 text-xs px-2.5 py-1.5 rounded-md border border-slate-600 focus:border-indigo-500 focus:outline-none"
                />
                <input
                  type="date"
                  value={filters.dateTo || ''}
                  onChange={e => updateFilter('dateTo', e.target.value || null)}
                  className="flex-1 bg-slate-700 text-slate-200 text-xs px-2.5 py-1.5 rounded-md border border-slate-600 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">MCMV</label>
              <div className="flex gap-1.5">
                <ToggleChip label="Todos" active={filters.isMcmv === null} onClick={() => updateFilter('isMcmv', null)} />
                <ToggleChip label="Apenas MCMV" active={filters.isMcmv === true} onClick={() => updateFilter('isMcmv', true)} />
                <ToggleChip label="Sem MCMV" active={filters.isMcmv === false} onClick={() => updateFilter('isMcmv', false)} />
              </div>
            </div>
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">
                Bairro {filters.neighborhoods.length > 0 && `(${filters.neighborhoods.length})`}
              </label>
              <input
                type="text"
                value={neighSearch}
                onChange={e => setNeighSearch(e.target.value)}
                placeholder="Buscar bairro..."
                className="w-full bg-slate-700 text-slate-200 text-xs px-2.5 py-1.5 rounded-md border border-slate-600 focus:border-indigo-500 focus:outline-none mb-1.5"
              />
              <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                {filteredNeighborhoods.map(n => (
                  <ToggleChip
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
      )}
    </div>
  )
}

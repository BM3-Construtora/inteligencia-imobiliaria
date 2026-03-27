import { createContext, useContext, useState, useMemo, type ReactNode } from 'react'

export interface Filters {
  propertyType: string[]       // ['land', 'house', 'apartment', ...]
  marketTier: string[]         // ['terreno_economico', 'casa_mcmv', ...]
  neighborhoods: string[]      // ['Centro', 'Palmital', ...]
  sources: string[]            // ['uniao', 'toca', ...]
  priceMin: number | null
  priceMax: number | null
  areaMin: number | null
  areaMax: number | null
  dateFrom: string | null      // 'YYYY-MM-DD'
  dateTo: string | null
  isMcmv: boolean | null       // null = any, true = only mcmv, false = exclude mcmv
}

export const DEFAULT_FILTERS: Filters = {
  propertyType: [],
  marketTier: [],
  neighborhoods: [],
  sources: [],
  priceMin: null,
  priceMax: null,
  areaMin: null,
  areaMax: null,
  dateFrom: null,
  dateTo: null,
  isMcmv: null,
}

interface FilterContextType {
  filters: Filters
  setFilters: (f: Filters) => void
  updateFilter: <K extends keyof Filters>(key: K, value: Filters[K]) => void
  resetFilters: () => void
  activeFilterCount: number
}

const FilterContext = createContext<FilterContextType | null>(null)

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)

  const updateFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const resetFilters = () => setFilters(DEFAULT_FILTERS)

  const activeFilterCount = useMemo(() => {
    let count = 0
    if (filters.propertyType.length) count++
    if (filters.marketTier.length) count++
    if (filters.neighborhoods.length) count++
    if (filters.sources.length) count++
    if (filters.priceMin != null || filters.priceMax != null) count++
    if (filters.areaMin != null || filters.areaMax != null) count++
    if (filters.dateFrom || filters.dateTo) count++
    if (filters.isMcmv != null) count++
    return count
  }, [filters])

  return (
    <FilterContext.Provider value={{ filters, setFilters, updateFilter, resetFilters, activeFilterCount }}>
      {children}
    </FilterContext.Provider>
  )
}

export function useFilters() {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilters must be used within FilterProvider')
  return ctx
}

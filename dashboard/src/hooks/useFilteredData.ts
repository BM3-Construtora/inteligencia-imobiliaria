import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useFilters, type Filters } from '../contexts/FilterContext'
import type { Neighborhood } from '../types'

function applyFiltersToQuery(query: any, filters: Filters) {
  if (filters.propertyType.length > 0) {
    query = query.in('property_type', filters.propertyType)
  }
  if (filters.marketTier.length > 0) {
    query = query.in('market_tier', filters.marketTier)
  }
  if (filters.neighborhoods.length > 0) {
    query = query.in('neighborhood', filters.neighborhoods)
  }
  if (filters.sources.length > 0) {
    query = query.in('source', filters.sources)
  }
  if (filters.priceMin != null) {
    query = query.gte('sale_price', filters.priceMin)
  }
  if (filters.priceMax != null) {
    query = query.lte('sale_price', filters.priceMax)
  }
  if (filters.areaMin != null) {
    query = query.gte('total_area', filters.areaMin)
  }
  if (filters.areaMax != null) {
    query = query.lte('total_area', filters.areaMax)
  }
  if (filters.dateFrom) {
    query = query.gte('first_seen_at', filters.dateFrom)
  }
  if (filters.dateTo) {
    query = query.lte('first_seen_at', filters.dateTo + 'T23:59:59')
  }
  if (filters.isMcmv === true) {
    query = query.eq('is_mcmv', true)
  } else if (filters.isMcmv === false) {
    query = query.eq('is_mcmv', false)
  }
  return query
}

export function useFilteredStats() {
  const { filters } = useFilters()
  const [data, setData] = useState({
    totalListings: 0,
    totalLand: 0,
    totalHouses: 0,
    totalOpportunities: 0,
    avgPriceM2Land: 0,
    sources: {} as Record<string, number>,
    tiers: {} as Record<string, number>,
  })
  const [loading, setLoading] = useState(true)

  const filterKey = JSON.stringify(filters)

  useEffect(() => {
    setLoading(true)
    async function fetch() {
      // Fetch filtered listings
      let query = supabase
        .from('listings')
        .select('source, property_type, market_tier, price_per_m2')
        .eq('is_active', true)

      query = applyFiltersToQuery(query, filters)
      const { data: rows } = await query

      const sources: Record<string, number> = {}
      const tiers: Record<string, number> = {}
      let landCount = 0
      let houseCount = 0
      const landPrices: number[] = []

      rows?.forEach(r => {
        sources[r.source] = (sources[r.source] || 0) + 1
        if (r.market_tier) tiers[r.market_tier] = (tiers[r.market_tier] || 0) + 1
        if (r.property_type === 'land') {
          landCount++
          if (r.price_per_m2) landPrices.push(r.price_per_m2)
        }
        if (r.property_type === 'house' || r.property_type === 'condo_house') houseCount++
      })

      const avgPm2 = landPrices.length > 0
        ? landPrices.reduce((a, b) => a + b, 0) / landPrices.length
        : 0

      // Opportunities count (always unfiltered since they're only land)
      const { count: oppCount } = await supabase
        .from('opportunities')
        .select('id', { count: 'exact', head: true })

      setData({
        totalListings: rows?.length || 0,
        totalLand: landCount,
        totalHouses: houseCount,
        totalOpportunities: oppCount || 0,
        avgPriceM2Land: avgPm2,
        sources,
        tiers,
      })
      setLoading(false)
    }
    fetch()
  }, [filterKey])

  return { data, loading }
}

export function useFilteredNeighborhoods() {
  const { filters } = useFilters()
  const [neighborhoods, setNeighborhoods] = useState<Neighborhood[]>([])
  const [loading, setLoading] = useState(true)

  const hasListingFilters = filters.propertyType.length > 0 ||
    filters.marketTier.length > 0 ||
    filters.sources.length > 0 ||
    filters.priceMin != null || filters.priceMax != null ||
    filters.areaMin != null || filters.areaMax != null ||
    filters.dateFrom || filters.dateTo ||
    filters.isMcmv != null

  const filterKey = JSON.stringify(filters)

  useEffect(() => {
    setLoading(true)
    async function fetch() {
      if (hasListingFilters) {
        // Need to aggregate from filtered listings
        let query = supabase
          .from('listings')
          .select('neighborhood, property_type, market_tier, price_per_m2, latitude, longitude, sale_price, total_area')
          .eq('is_active', true)

        query = applyFiltersToQuery(query, filters)
        const { data: rows } = await query

        // Aggregate by neighborhood
        const neighMap = new Map<string, {
          name: string
          total: number
          land: number
          houses: number
          tiers: Record<string, number>
          landPrices: number[]
          housePrices: number[]
          lats: number[]
          lngs: number[]
        }>()

        rows?.forEach(r => {
          if (!r.neighborhood) return
          let n = neighMap.get(r.neighborhood)
          if (!n) {
            n = { name: r.neighborhood, total: 0, land: 0, houses: 0, tiers: {}, landPrices: [], housePrices: [], lats: [], lngs: [] }
            neighMap.set(r.neighborhood, n)
          }
          n.total++
          if (r.property_type === 'land') {
            n.land++
            if (r.price_per_m2) n.landPrices.push(r.price_per_m2)
          }
          if (r.property_type === 'house' || r.property_type === 'condo_house') {
            n.houses++
            if (r.price_per_m2) n.housePrices.push(r.price_per_m2)
          }
          if (r.market_tier) n.tiers[r.market_tier] = (n.tiers[r.market_tier] || 0) + 1
          if (r.latitude && r.longitude) {
            n.lats.push(r.latitude)
            n.lngs.push(r.longitude)
          }
        })

        // Also need neighborhood-selected filter
        let entries = Array.from(neighMap.values())
        if (filters.neighborhoods.length > 0) {
          entries = entries.filter(n => filters.neighborhoods.includes(n.name))
        }

        const result: Neighborhood[] = entries
          .filter(n => n.total > 0)
          .map((n, i) => ({
            id: i,
            name: n.name,
            zone: null,
            avg_price_m2_land: n.landPrices.length > 0
              ? n.landPrices.reduce((a, b) => a + b, 0) / n.landPrices.length
              : null,
            avg_price_m2_house: n.housePrices.length > 0
              ? n.housePrices.reduce((a, b) => a + b, 0) / n.housePrices.length
              : null,
            avg_price_m2_apt: null,
            total_listings: n.total,
            total_land: n.land,
            total_houses: n.houses,
            total_listings_by_tier: n.tiers,
            latitude: n.lats.length > 0 ? n.lats.reduce((a, b) => a + b, 0) / n.lats.length : null,
            longitude: n.lngs.length > 0 ? n.lngs.reduce((a, b) => a + b, 0) / n.lngs.length : null,
            avg_days_on_market: null,
            avg_risk_score: null,
            risk_breakdown: null,
            absorption_rate: null,
            months_of_inventory: null,
            removed_last_30d: null,
            new_last_30d: null,
            market_heat_score: null,
          }))
          .sort((a, b) => b.total_listings - a.total_listings)

        setNeighborhoods(result)
      } else {
        // No listing-level filters, use pre-aggregated neighborhoods
        let query = supabase
          .from('neighborhoods')
          .select('*')
          .gt('total_listings', 0)

        if (filters.neighborhoods.length > 0) {
          query = query.in('name', filters.neighborhoods)
        }

        const { data } = await query.order('total_listings', { ascending: false })
        setNeighborhoods(data || [])
      }
      setLoading(false)
    }
    fetch()
  }, [filterKey, hasListingFilters])

  return { neighborhoods, loading }
}

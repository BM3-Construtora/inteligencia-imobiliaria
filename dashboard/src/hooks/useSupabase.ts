import { useEffect, useState } from 'react'
import { supabase, fetchAllRows } from '../lib/supabase'
import type { Opportunity, MarketSnapshot, Neighborhood } from '../types'

export function useStats() {
  const [stats, setStats] = useState({
    totalListings: 0,
    totalLand: 0,
    totalOpportunities: 0,
    avgPriceM2Land: 0,
    sources: {} as Record<string, number>,
    types: {} as Record<string, number>,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      // Use exact counts (no row limit issue) + paginated fetches for aggregation
      const [listings, land, opportunities] = await Promise.all([
        supabase.from('listings').select('id', { count: 'exact', head: true }).eq('is_active', true),
        supabase.from('listings').select('id', { count: 'exact', head: true }).eq('is_active', true).eq('property_type', 'land'),
        supabase.from('opportunities').select('id', { count: 'exact', head: true }),
      ])

      // Fetch all rows for aggregation (paginated to avoid 1000 limit)
      const allListings = await fetchAllRows<{ source: string; property_type: string; price_per_m2: number | null }>(
        (from) => from.select('source, property_type, price_per_m2').eq('is_active', true),
        'listings',
      )

      const sources: Record<string, number> = {}
      const types: Record<string, number> = {}
      const prices: number[] = []

      allListings.forEach(r => {
        sources[r.source] = (sources[r.source] || 0) + 1
        types[r.property_type] = (types[r.property_type] || 0) + 1
        if (r.property_type === 'land' && r.price_per_m2) prices.push(r.price_per_m2)
      })

      const avgPm2 = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : 0

      setStats({
        totalListings: listings.count || 0,
        totalLand: land.count || 0,
        totalOpportunities: opportunities.count || 0,
        avgPriceM2Land: avgPm2,
        sources,
        types,
      })
      setLoading(false)
    }
    fetch()
  }, [])

  return { stats, loading }
}

export function useOpportunities(limit = 20) {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const { data } = await supabase
        .from('opportunities')
        .select(`
          id, listing_id, score, score_breakdown, reason, created_at,
          listing:listings(id, source, source_id, title, neighborhood, sale_price, total_area, price_per_m2, is_mcmv, main_image_url, url)
        `)
        .order('score', { ascending: false })
        .limit(limit)

      setOpportunities((data as unknown as Opportunity[]) || [])
      setLoading(false)
    }
    fetch()
  }, [limit])

  return { opportunities, loading }
}

export function useViabilityStudies(listingIds: number[]) {
  const [studies, setStudies] = useState<Record<number, any[]>>({})
  const [loading, setLoading] = useState(true)

  const key = listingIds.join(',')

  useEffect(() => {
    if (!listingIds.length) { setLoading(false); return }
    async function fetch() {
      const { data } = await supabase
        .from('viability_studies')
        .select('listing_id, scenario, outputs, is_viable')
        .in('listing_id', listingIds)

      const grouped: Record<number, any[]> = {}
      data?.forEach(s => {
        if (!grouped[s.listing_id]) grouped[s.listing_id] = []
        grouped[s.listing_id].push(s)
      })
      setStudies(grouped)
      setLoading(false)
    }
    fetch()
  }, [key])

  return { studies, loading }
}

export function useSoldEstimates() {
  const [data, setData] = useState<{ total: number; byNeighborhood: Record<string, number> }>({
    total: 0, byNeighborhood: {}
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const rows = await fetchAllRows<{ neighborhood: string | null }>(
        (from) => from.select('neighborhood'),
        'sold_estimates',
      )

      const byNeighborhood: Record<string, number> = {}
      rows.forEach(r => {
        if (r.neighborhood) {
          byNeighborhood[r.neighborhood] = (byNeighborhood[r.neighborhood] || 0) + 1
        }
      })
      setData({ total: rows.length, byNeighborhood })
      setLoading(false)
    }
    fetch()
  }, [])

  return { ...data, loading }
}

export function useMarketSnapshots() {
  const [snapshots, setSnapshots] = useState<MarketSnapshot[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const { data } = await supabase
        .from('market_snapshots')
        .select('*')
        .is('neighborhood', null)
        .not('property_type', 'is', null)
        .order('property_type')

      setSnapshots(data || [])
      setLoading(false)
    }
    fetch()
  }, [])

  return { snapshots, loading }
}

export function useNeighborhoods() {
  const [neighborhoods, setNeighborhoods] = useState<Neighborhood[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const { data } = await supabase
        .from('neighborhoods')
        .select('*')
        .gt('total_land', 0)
        .order('total_land', { ascending: false })

      setNeighborhoods(data || [])
      setLoading(false)
    }
    fetch()
  }, [])

  return { neighborhoods, loading }
}

export function useMapData() {
  const [neighborhoods, setNeighborhoods] = useState<Neighborhood[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const { data } = await supabase
        .from('neighborhoods')
        .select('*')
        .not('latitude', 'is', null)
        .not('longitude', 'is', null)
        .gt('total_listings', 0)
        .order('total_listings', { ascending: false })

      setNeighborhoods(data || [])
      setLoading(false)
    }
    fetch()
  }, [])

  return { neighborhoods, loading }
}

export function useClassificationStats() {
  const [tiers, setTiers] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const rows = await fetchAllRows<{ market_tier: string }>(
        (from) => from.select('market_tier').eq('is_active', true).not('market_tier', 'is', null),
        'listings',
      )

      const counts: Record<string, number> = {}
      rows.forEach(r => {
        counts[r.market_tier] = (counts[r.market_tier] || 0) + 1
      })
      setTiers(counts)
      setLoading(false)
    }
    fetch()
  }, [])

  return { tiers, loading }
}

import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
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
      const [listings, land, opportunities] = await Promise.all([
        supabase.from('listings').select('id', { count: 'exact', head: true }).eq('is_active', true),
        supabase.from('listings').select('id', { count: 'exact', head: true }).eq('is_active', true).eq('property_type', 'land'),
        supabase.from('opportunities').select('id', { count: 'exact', head: true }),
      ])

      // Sources
      const sourceData = await supabase.from('listings').select('source').eq('is_active', true)
      const sources: Record<string, number> = {}
      sourceData.data?.forEach(r => { sources[r.source] = (sources[r.source] || 0) + 1 })

      // Types
      const typeData = await supabase.from('listings').select('property_type').eq('is_active', true)
      const types: Record<string, number> = {}
      typeData.data?.forEach(r => { types[r.property_type] = (types[r.property_type] || 0) + 1 })

      // Avg price/m2 land
      const landPrices = await supabase
        .from('listings')
        .select('price_per_m2')
        .eq('is_active', true)
        .eq('property_type', 'land')
        .not('price_per_m2', 'is', null)
      const prices = landPrices.data?.map(r => r.price_per_m2).filter(Boolean) || []
      const avgPm2 = prices.length > 0 ? prices.reduce((a: number, b: number) => a + b, 0) / prices.length : 0

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

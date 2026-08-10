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

export interface MapListingPoint {
  id: number
  neighborhood: string | null
  latitude: number
  longitude: number
  sale_price: number | null
  total_area: number | null
  price_per_m2: number | null
  url: string | null
  is_mcmv: boolean
  market_tier: string | null
  mcmv_score: number | null
  score: number
}

type EmbeddedListing = {
  id: number
  neighborhood: string | null
  latitude: number | null
  longitude: number | null
  sale_price: number | null
  total_area: number | null
  price_per_m2: number | null
  url: string | null
  is_mcmv: boolean
  market_tier: string | null
  mcmv_accessibility_score: number | null
}

// Pins por imóvel no mapa: usa o conjunto de oportunidades (acionável e
// limitado), com as coordenadas do listing embutido. Evita renderizar os
// ~20k listings individuais, que travariam o Leaflet.
export function useOpportunityPoints() {
  const [points, setPoints] = useState<MapListingPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchPoints() {
      const rows = await fetchAllRows<{ score: number; listing: EmbeddedListing | EmbeddedListing[] | null }>(
        (from) => from.select(
          'score, listing:listings!inner(id, neighborhood, latitude, longitude, sale_price, total_area, price_per_m2, url, is_mcmv, market_tier, mcmv_accessibility_score)',
        ),
        'opportunities',
      )

      const pts: MapListingPoint[] = []
      for (const r of rows) {
        const l = Array.isArray(r.listing) ? r.listing[0] : r.listing
        if (!l || l.latitude == null || l.longitude == null) continue
        pts.push({
          id: l.id,
          neighborhood: l.neighborhood,
          latitude: l.latitude,
          longitude: l.longitude,
          sale_price: l.sale_price,
          total_area: l.total_area,
          price_per_m2: l.price_per_m2,
          url: l.url,
          is_mcmv: l.is_mcmv,
          market_tier: l.market_tier,
          mcmv_score: l.mcmv_accessibility_score,
          score: r.score,
        })
      }
      setPoints(pts)
      setLoading(false)
    }
    fetchPoints()
  }, [])

  return { points, loading }
}

export interface CensusSector {
  sector_code: string
  renda_per_capita: number | null
  densidade_demo: number | null
  geometry: GeoJSON.Geometry
}

// Choropleth de renda: setores censitários via RPC GeoJSON (sql/052).
export function useCensusGeoJson() {
  const [sectors, setSectors] = useState<CensusSector[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchSectors() {
      const { data, error } = await supabase.rpc('census_sectors_geojson')
      if (error || !data) { setLoading(false); return }
      const parsed: CensusSector[] = []
      for (const row of data as { sector_code: string; renda_per_capita: number | null; densidade_demo: number | null; geojson: string }[]) {
        try {
          parsed.push({
            sector_code: row.sector_code,
            renda_per_capita: row.renda_per_capita,
            densidade_demo: row.densidade_demo,
            geometry: JSON.parse(row.geojson) as GeoJSON.Geometry,
          })
        } catch { /* geojson inválido — pula o setor */ }
      }
      setSectors(parsed)
      setLoading(false)
    }
    fetchSectors()
  }, [])

  return { sectors, loading }
}

export interface EconomicCentroid {
  name: string
  label_pt: string | null
  latitude: number
  longitude: number
  radius_m: number
  description: string | null
}

// Polos econômicos + raio de influência (RPC sql/052).
export function useEconomicCentroids() {
  const [centroids, setCentroids] = useState<EconomicCentroid[]>([])

  useEffect(() => {
    async function fetchCentroids() {
      const { data, error } = await supabase.rpc('economic_centroids_geojson')
      if (error || !data) return
      setCentroids(data as EconomicCentroid[])
    }
    fetchCentroids()
  }, [])

  return { centroids }
}

export interface CompetitionPoint {
  neighborhood: string
  latitude: number
  longitude: number
  count: number
}

// Radar de concorrência plotado no centroide do bairro (v1 sem geocode fino):
// agrega alvarás/EIV de radar_concorrencia por bairro e cruza com as
// coordenadas de `neighborhoods`.
export function useCompetitionPoints() {
  const [points, setPoints] = useState<CompetitionPoint[]>([])

  useEffect(() => {
    async function fetchCompetition() {
      const [radar, neighborhoods] = await Promise.all([
        supabase.from('radar_concorrencia').select('neighborhood'),
        supabase.from('neighborhoods').select('name, latitude, longitude').not('latitude', 'is', null),
      ])

      const counts: Record<string, number> = {}
      for (const r of (radar.data as { neighborhood: string | null }[] | null) || []) {
        if (r.neighborhood) counts[r.neighborhood.toLowerCase()] = (counts[r.neighborhood.toLowerCase()] || 0) + 1
      }
      const coords: Record<string, { name: string; lat: number; lng: number }> = {}
      for (const n of (neighborhoods.data as { name: string; latitude: number; longitude: number }[] | null) || []) {
        coords[n.name.toLowerCase()] = { name: n.name, lat: n.latitude, lng: n.longitude }
      }

      const pts: CompetitionPoint[] = []
      for (const [key, count] of Object.entries(counts)) {
        const c = coords[key]
        if (c) pts.push({ neighborhood: c.name, latitude: c.lat, longitude: c.lng, count })
      }
      setPoints(pts)
    }
    fetchCompetition()
  }, [])

  return { points }
}

export interface BairroTipoStat {
  bairro: string
  property_type: string
  total: number | null
  ativos: number | null
  mcmv: number | null
  preco_mediano: number | null
  preco_medio: number | null
  ppm2_mediano: number | null
  area_mediana: number | null
  aluguel_mediano: number | null
  aluguel_n: number | null
  hist_total: number | null
  saiu_do_ar: number | null
  taxa_saida_pct: number | null
  dias_medio: number | null
  baixaram_preco: number | null
}

export interface BairroResumo {
  bairro: string
  listings_total: number
  listings_ativos: number
  mcmv: number
  mcmv_pct: number | null
  acessibilidade_media: number | null
  acc_n: number
  avm_total: number
  avm_under: number
}

export interface BairroData {
  resumo: BairroResumo
  tipos: Record<string, BairroTipoStat>
}

// Painel do Bairro: junta as matviews bairro_resumo + bairro_tipo_stats (sql/053)
// numa estrutura por bairro. Refresh via refresh_bairro_stats() no pipeline.
export function useBairros() {
  const [bairros, setBairros] = useState<Record<string, BairroData>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const [resumos, tipos] = await Promise.all([
        fetchAllRows<BairroResumo>((from) => from.select('*'), 'bairro_resumo'),
        fetchAllRows<BairroTipoStat>((from) => from.select('*'), 'bairro_tipo_stats'),
      ])

      const map: Record<string, BairroData> = {}
      for (const r of resumos) map[r.bairro] = { resumo: r, tipos: {} }
      for (const t of tipos) {
        if (!t.property_type || !map[t.bairro]) continue
        map[t.bairro].tipos[t.property_type] = t
      }
      setBairros(map)
      setLoading(false)
    }
    fetch()
  }, [])

  return { bairros, loading }
}

export interface TrendPoint { date: string; ppm2: number }

// Série de preço/m² por bairro (terreno) a partir de market_snapshots.
// Normaliza o nome do bairro igual ao norm_bairro do sql/053 (initcap+trim)
// pra casar com as chaves de useBairros.
export function useBairroLandTrends() {
  const [trends, setTrends] = useState<Record<string, TrendPoint[]>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetch() {
      const rows = await fetchAllRows<{ neighborhood: string | null; snapshot_date: string; avg_price_m2: number | null }>(
        (from) => from
          .select('neighborhood, snapshot_date, avg_price_m2')
          .eq('property_type', 'land')
          .not('neighborhood', 'is', null)
          .not('avg_price_m2', 'is', null)
          .order('snapshot_date', { ascending: true }),
        'market_snapshots',
      )
      const norm = (s: string) =>
        s.trim().split(/\s+/).map(w => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w)).join(' ')
      const map: Record<string, TrendPoint[]> = {}
      for (const r of rows) {
        if (!r.neighborhood || r.avg_price_m2 == null) continue
        const b = norm(r.neighborhood)
        ;(map[b] ||= []).push({ date: r.snapshot_date, ppm2: r.avg_price_m2 })
      }
      setTrends(map)
      setLoading(false)
    }
    fetch()
  }, [])

  return { trends, loading }
}

export interface UndervaluedRow {
  listing_id: number
  actual_price: number | null
  p25: number | null
  p50: number | null
  mispricing_pct: number | null
  shap_summary: string | null
  confidence: number | null
  neighborhood: string | null
  total_area: number | null
  url: string | null
}

// Imóveis subprecificados pelo AVM (pedido abaixo do P25). Dado real em prod.
export function useUndervalued(limit = 50) {
  const [rows, setRows] = useState<UndervaluedRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchRows() {
      const { data } = await supabase
        .from('avm_predictions')
        .select(
          'listing_id, actual_price, p25, p50, mispricing_pct, shap_summary, confidence, ' +
          'listing:listings!inner(neighborhood, total_area, url, is_active)',
        )
        .eq('is_undervalued', true)
        .order('mispricing_pct', { ascending: false })
        .limit(limit * 2)

      const out: UndervaluedRow[] = []
      for (const r of (data as unknown as Array<Record<string, unknown>>) || []) {
        const lraw = r.listing
        const l = (Array.isArray(lraw) ? lraw[0] : lraw) as Record<string, unknown> | undefined
        if (!l || !l.is_active) continue
        out.push({
          listing_id: r.listing_id as number,
          actual_price: (r.actual_price as number) ?? null,
          p25: (r.p25 as number) ?? null,
          p50: (r.p50 as number) ?? null,
          mispricing_pct: (r.mispricing_pct as number) ?? null,
          shap_summary: (r.shap_summary as string) ?? null,
          confidence: (r.confidence as number) ?? null,
          neighborhood: (l.neighborhood as string) ?? null,
          total_area: (l.total_area as number) ?? null,
          url: (l.url as string) ?? null,
        })
        if (out.length >= limit) break
      }
      setRows(out)
      setLoading(false)
    }
    fetchRows()
  }, [limit])

  return { rows, loading }
}

export interface Loteamento {
  titulo: string | null
  tipo: string | null
  issue_date: string | null
  neighborhood: string | null
}

// Loteamentos/desmembramentos aprovados (futura oferta). Fonte: DOM-MAR.
export function useLoteamentos(limit = 60) {
  const [rows, setRows] = useState<Loteamento[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchRows() {
      const { data, count } = await supabase
        .from('parcelamento_solo_marilia')
        .select('titulo, tipo, issue_date, neighborhood', { count: 'exact' })
        .not('issue_date', 'is', null)
        .order('issue_date', { ascending: false })
        .limit(limit)

      setRows((data as Loteamento[]) || [])
      setTotal(count || 0)
      setLoading(false)
    }
    fetchRows()
  }, [limit])

  return { rows, total, loading }
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

export interface Listing {
  id: number
  source: string
  source_id: string
  url: string | null
  property_type: string
  business_type: string
  title: string | null
  address: string | null
  neighborhood: string | null
  city: string
  state: string
  sale_price: number | null
  total_area: number | null
  price_per_m2: number | null
  bedrooms: number | null
  bathrooms: number | null
  parking_spaces: number | null
  is_mcmv: boolean
  main_image_url: string | null
  first_seen_at: string
  market_tier: string | null
}

export interface Opportunity {
  id: number
  listing_id: number
  score: number
  score_breakdown: Record<string, number>
  reason: string
  created_at: string
  listing?: Listing
}

export interface MarketSnapshot {
  id: number
  snapshot_date: string
  property_type: string | null
  neighborhood: string | null
  total_listings: number
  avg_price: number | null
  median_price: number | null
  avg_price_m2: number | null
  min_price: number | null
  max_price: number | null
  avg_area: number | null
}

export interface Neighborhood {
  id: number
  name: string
  zone: string | null
  avg_price_m2_land: number | null
  avg_price_m2_house: number | null
  avg_price_m2_apt: number | null
  total_listings: number
  total_land: number
  total_houses: number
  total_listings_by_tier: Record<string, number> | null
  latitude: number | null
  longitude: number | null
  avg_days_on_market: number | null
  avg_risk_score: number | null
  risk_breakdown: Record<string, number> | null
  absorption_rate: number | null
  months_of_inventory: number | null
  removed_last_30d: number | null
  new_last_30d: number | null
}

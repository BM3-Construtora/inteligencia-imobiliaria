import { useState, useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import { useFilteredNeighborhoods } from '../hooks/useFilteredData'
import { MapLegend } from './MapLegend'
import type { Neighborhood } from '../types'
import 'leaflet/dist/leaflet.css'

type MapView = 'all' | 'land' | 'houses'
type ColorMode = 'price' | 'risk'

const TIER_LABELS: Record<string, string> = {
  terreno_economico: 'Terreno Econom.',
  terreno_medio: 'Terreno Medio',
  terreno_alto: 'Terreno Alto',
  terreno_grande: 'Terreno Grande',
  casa_mcmv: 'Casa MCMV',
  casa_baixo_padrao: 'Casa Baixo',
  casa_medio_padrao: 'Casa Medio',
  casa_alto_padrao: 'Casa Alto',
  apto_economico: 'Apto Econom.',
  apto_medio: 'Apto Medio',
  apto_alto: 'Apto Alto',
}

function getCount(n: Neighborhood, view: MapView): number {
  if (view === 'land') return n.total_land
  if (view === 'houses') return n.total_houses
  return n.total_listings
}

function getAvgPrice(n: Neighborhood, view: MapView): number | null {
  if (view === 'land') return n.avg_price_m2_land
  if (view === 'houses') return n.avg_price_m2_house
  return n.avg_price_m2_land ?? n.avg_price_m2_house
}

function priceToColor(price: number | null, minPrice: number, maxPrice: number): string {
  if (price == null || maxPrice === minPrice) return '#6366f1'
  const t = Math.min(1, Math.max(0, (price - minPrice) / (maxPrice - minPrice)))
  if (t < 0.5) {
    const r = Math.round(34 + (t * 2) * (234 - 34))
    return `rgb(${r}, 197, 94)`
  }
  const g = Math.round(197 - ((t - 0.5) * 2) * (197 - 68))
  return `rgb(239, ${g}, 68)`
}

function fmt(n: number | null): string {
  if (n == null) return '-'
  return `R$ ${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

export function PropertyMap() {
  const { neighborhoods, loading } = useFilteredNeighborhoods()
  const [view, setView] = useState<MapView>('all')
  const [colorMode, setColorMode] = useState<ColorMode>('price')

  const { filtered, minPrice, maxPrice, minRisk, maxRisk } = useMemo(() => {
    const withCoords = neighborhoods.filter(n => n.latitude != null && n.longitude != null)
    const items = withCoords.filter(n => getCount(n, view) > 0)
    const prices = items.map(n => getAvgPrice(n, view)).filter((p): p is number => p != null)
    const risks = items.map(n => n.avg_risk_score).filter((r): r is number => r != null)
    return {
      filtered: items,
      minPrice: prices.length > 0 ? Math.min(...prices) : 0,
      maxPrice: prices.length > 0 ? Math.max(...prices) : 1,
      minRisk: risks.length > 0 ? Math.min(...risks) : 1,
      maxRisk: risks.length > 0 ? Math.max(...risks) : 5,
    }
  }, [neighborhoods, view])

  if (loading) {
    return <div className="text-slate-400 py-8 text-center">Carregando mapa...</div>
  }

  if (filtered.length === 0) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <h3 className="text-white font-semibold mb-2">Mapa de Bairros</h3>
        <p className="text-slate-400 text-sm">Nenhum bairro encontrado com os filtros atuais.</p>
      </div>
    )
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-white font-semibold">Mapa de Bairros — Marilia/SP</h3>
          <p className="text-xs text-slate-400">{filtered.length} bairros</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {([['all', 'Todos'], ['land', 'Terrenos'], ['houses', 'Casas']] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setView(key)}
                className={`px-3 py-1 text-xs rounded-md transition-colors ${
                  view === key
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex gap-1 border-l border-slate-600 pl-3">
            <button
              onClick={() => setColorMode('price')}
              className={`px-2 py-1 text-xs rounded-md transition-colors ${
                colorMode === 'price' ? 'bg-emerald-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Preco
            </button>
            <button
              onClick={() => setColorMode('risk')}
              className={`px-2 py-1 text-xs rounded-md transition-colors ${
                colorMode === 'risk' ? 'bg-red-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Risco
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-lg overflow-hidden relative" style={{ height: 420 }}>
        <MapContainer
          center={[-22.2139, -49.9461]}
          zoom={13}
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          {filtered.map(n => {
            const count = getCount(n, view)
            const price = getAvgPrice(n, view)
            const radius = Math.max(6, Math.sqrt(count) * 4)
            const color = colorMode === 'risk' && n.avg_risk_score != null
              ? priceToColor(n.avg_risk_score, minRisk, maxRisk)  // reuse green→red gradient
              : priceToColor(price, minPrice, maxPrice)
            const tiers = n.total_listings_by_tier || {}

            return (
              <CircleMarker
                key={n.id}
                center={[n.latitude!, n.longitude!]}
                radius={radius}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.6,
                  weight: 2,
                }}
              >
                <Popup>
                  <div className="text-sm min-w-[200px]">
                    <p className="font-bold text-base mb-1">{n.name}</p>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs mb-2">
                      <span className="text-gray-500">Total:</span>
                      <span className="font-medium">{n.total_listings}</span>
                      <span className="text-gray-500">Terrenos:</span>
                      <span className="font-medium">{n.total_land}</span>
                      <span className="text-gray-500">Casas:</span>
                      <span className="font-medium">{n.total_houses}</span>
                      <span className="text-gray-500">R$/m² terreno:</span>
                      <span className="font-medium">{fmt(n.avg_price_m2_land)}</span>
                      <span className="text-gray-500">R$/m² casa:</span>
                      <span className="font-medium">{fmt(n.avg_price_m2_house)}</span>
                      <span className="text-gray-500">Tempo medio:</span>
                      <span className="font-medium">{n.avg_days_on_market != null ? `${n.avg_days_on_market} dias` : '-'}</span>
                      {n.avg_risk_score != null && (<>
                        <span className="text-gray-500">Risco medio:</span>
                        <span className={`font-medium ${n.avg_risk_score >= 3 ? 'text-red-500' : n.avg_risk_score >= 2 ? 'text-yellow-500' : 'text-green-500'}`}>
                          {n.avg_risk_score.toFixed(1)}/5
                        </span>
                      </>)}
                    </div>
                    {Object.keys(tiers).length > 0 && (
                      <>
                        <p className="font-semibold text-xs mb-0.5 border-t pt-1">Classificacao</p>
                        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
                          {Object.entries(tiers)
                            .sort(([, a], [, b]) => b - a)
                            .map(([tier, count]) => (
                              <span key={tier}>
                                <span className="text-gray-500">{TIER_LABELS[tier] || tier}:</span>{' '}
                                <span className="font-medium">{count}</span>
                              </span>
                            ))}
                        </div>
                      </>
                    )}
                  </div>
                </Popup>
              </CircleMarker>
            )
          })}
        </MapContainer>
        <MapLegend
          minPrice={colorMode === 'risk' ? minRisk : minPrice}
          maxPrice={colorMode === 'risk' ? maxRisk : maxPrice}
          label={colorMode === 'risk' ? 'Risco' : 'Preco/m²'}
          unitSuffix={colorMode === 'risk' ? '/5' : '/m²'}
        />
      </div>
    </div>
  )
}

function fmtValue(n: number, suffix: string): string {
  if (suffix === '/5') return n.toFixed(1)
  return `R$ ${(n / 1000).toFixed(0)}k`
}

interface MapLegendProps {
  minPrice: number
  maxPrice: number
  label?: string
  unitSuffix?: string
}

export function MapLegend({ minPrice, maxPrice, label = 'Preco/m²', unitSuffix = '/m²' }: MapLegendProps) {
  return (
    <div className="absolute bottom-3 left-3 z-[1000] bg-slate-900/90 backdrop-blur-sm border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-300">
      <p className="font-semibold mb-1.5 text-slate-200">Legenda</p>
      <div className="flex items-center gap-2 mb-1.5">
        <span>{label}:</span>
        <div
          className="h-2.5 rounded-full flex-1"
          style={{
            background: 'linear-gradient(to right, rgb(34, 197, 94), rgb(234, 179, 8), rgb(239, 68, 68))',
            minWidth: 80,
          }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-400">
        <span>{fmtValue(minPrice, unitSuffix)}{unitSuffix}</span>
        <span>{fmtValue(maxPrice, unitSuffix)}{unitSuffix}</span>
      </div>
      <div className="flex items-center gap-2 mt-1.5 border-t border-slate-700 pt-1.5">
        <span>Tamanho:</span>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-indigo-500" />
          <span className="text-[10px]">poucos</span>
          <div className="w-4 h-4 rounded-full bg-indigo-500" />
          <span className="text-[10px]">muitos</span>
        </div>
      </div>
    </div>
  )
}

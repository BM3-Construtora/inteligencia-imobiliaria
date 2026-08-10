import { useMemo, useState } from 'react'
import { Search, TrendingUp, TrendingDown, Minus, Home, Building, Landmark, Store, Trees, AlertTriangle } from 'lucide-react'
import { StatCard } from './StatCard'
import { useBairros, useBairroLandTrends, type BairroData, type TrendPoint } from '../hooks/useSupabase'

const TYPE_META: Record<string, { pt: string; icon: typeof Home; dot: string }> = {
  house: { pt: 'Casa', icon: Home, dot: 'bg-emerald-400' },
  apartment: { pt: 'Apartamento', icon: Building, dot: 'bg-sky-400' },
  land: { pt: 'Terreno', icon: Landmark, dot: 'bg-amber-400' },
  commercial: { pt: 'Comercial', icon: Store, dot: 'bg-violet-400' },
  farm: { pt: 'Chácara/Sítio', icon: Trees, dot: 'bg-lime-400' },
}
const TYPE_ORDER = ['house', 'apartment', 'land', 'commercial', 'farm']
const NOISE = new Set(['Marília', '(Sem Bairro)'])

function brl(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1e6) return `R$ ${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1).replace('.', ',')} mi`
  if (v >= 1e3) return `R$ ${Math.round(v / 1e3)} mil`
  return `R$ ${Math.round(v)}`
}
function ppm2(v: number | null): string {
  return v == null ? '—' : `R$ ${Math.round(v).toLocaleString('pt-BR')}/m²`
}
function nfmt(v: number | null): string {
  return v == null ? '—' : Math.round(v).toLocaleString('pt-BR')
}

type SortKey = 'ativos' | 'preco' | 'absorcao' | 'oport'
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'ativos', label: 'mais ativos' },
  { key: 'preco', label: 'preço/m²' },
  { key: 'absorcao', label: 'gira rápido' },
  { key: 'oport', label: 'oportunidade' },
]

function scoreFor(d: BairroData, key: SortKey): number {
  const t = d.tipos.house || d.tipos.land || d.tipos.apartment
  if (key === 'preco') return t?.ppm2_mediano || 0
  if (key === 'oport') return d.resumo.avm_under
  if (key === 'absorcao') {
    let s = 0, n = 0
    for (const pt of Object.keys(d.tipos)) {
      const a = d.tipos[pt]
      if ((a.hist_total || 0) >= 4 && a.taxa_saida_pct != null) { s += a.taxa_saida_pct; n++ }
    }
    return n ? s / n : -1
  }
  return d.resumo.listings_ativos
}

export function BairroPanel() {
  const { bairros, loading } = useBairros()
  const { trends } = useBairroLandTrends()
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('ativos')
  const [selected, setSelected] = useState<string | null>(null)

  // mediana da cidade por tipo (para o delta "vs cidade")
  const city = useMemo(() => {
    const acc: Record<string, number[]> = { house: [], apartment: [], land: [], commercial: [] }
    let ativos = 0, under = 0, total = 0
    for (const b of Object.values(bairros)) {
      ativos += b.resumo.listings_ativos; under += b.resumo.avm_under; total += b.resumo.listings_total
      for (const t of Object.keys(acc)) {
        const tp = b.tipos[t]
        if (tp?.ppm2_mediano && (tp.ativos || 0) >= 3) acc[t].push(tp.ppm2_mediano)
      }
    }
    const med = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null }
    return {
      ativos, under, total, count: Object.keys(bairros).length,
      ppm2: { house: med(acc.house), apartment: med(acc.apartment), land: med(acc.land), commercial: med(acc.commercial) } as Record<string, number | null>,
    }
  }, [bairros])

  const list = useMemo(() => {
    const q = query.trim().toLowerCase()
    return Object.values(bairros)
      .filter(d => d.resumo.listings_total >= 2 && (!q || d.resumo.bairro.toLowerCase().includes(q)))
      .map(d => ({ d, s: scoreFor(d, sortKey) }))
      .sort((a, z) => z.s - a.s || z.d.resumo.listings_ativos - a.d.resumo.listings_ativos)
      .slice(0, 120)
      .map(x => x.d)
  }, [bairros, query, sortKey])

  const current = (selected && bairros[selected]) || list[0] || null

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* KPIs da cidade */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard label="Imóveis ativos" value={nfmt(city.ativos)} sub="agora no mercado" accent="indigo" />
        <StatCard label="Bairros" value={nfmt(city.count)} sub="mapeados" accent="sky" />
        <StatCard label="Preço/m² casa" value={ppm2(city.ppm2.house)} sub="mediana da cidade" accent="emerald" />
        <StatCard label="Preço/m² terreno" value={ppm2(city.ppm2.land)} sub="mediana da cidade" accent="amber" />
        <StatCard label="Subprecificados" value={nfmt(city.under)} sub="AVM abaixo do justo" accent="rose" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 items-start">
        {/* Lista de bairros */}
        <aside className="bg-slate-800/50 rounded-xl border border-slate-800 flex flex-col lg:sticky lg:top-24 max-h-[calc(100vh-8rem)]">
          <div className="p-3 border-b border-slate-800">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Buscar bairro..."
                className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {SORTS.map(s => (
                <button
                  key={s.key}
                  onClick={() => setSortKey(s.key)}
                  className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors ${
                    sortKey === s.key
                      ? 'bg-indigo-600 border-indigo-600 text-white'
                      : 'border-slate-700 text-slate-400 hover:text-white'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
          <div className="overflow-y-auto flex-1">
            {list.map(d => {
              const r = d.resumo
              const t = d.tipos.house || d.tipos.land || d.tipos.apartment
              let right = '—'
              if (sortKey === 'oport') right = `${r.avm_under}`
              else if (sortKey === 'absorcao') { const sc = scoreFor(d, 'absorcao'); right = sc >= 0 ? `${Math.round(sc)}%` : '—' }
              else right = t?.ppm2_mediano ? `R$ ${Math.round(t.ppm2_mediano).toLocaleString('pt-BR')}` : '—'
              const active = current?.resumo.bairro === r.bairro
              return (
                <button
                  key={r.bairro}
                  onClick={() => setSelected(r.bairro)}
                  className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 border-b border-slate-800/60 text-left transition-colors ${
                    active ? 'bg-indigo-600/15' : 'hover:bg-slate-800/60'
                  }`}
                >
                  <div className="min-w-0">
                    <p className={`text-sm font-medium truncate ${active ? 'text-indigo-300' : 'text-white'}`}>{r.bairro}</p>
                    <p className="text-[11px] text-slate-500 tabular-nums">{r.listings_ativos} ativos · {r.mcmv} MCMV</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-semibold text-white tabular-nums">{right}</p>
                    <p className="text-[10px] text-slate-500">{sortKey === 'oport' ? 'barganhas' : sortKey === 'absorcao' ? 'giro' : 'R$/m²'}</p>
                  </div>
                </button>
              )
            })}
            {list.length === 0 && <p className="text-slate-500 text-sm text-center py-6">Nenhum bairro encontrado.</p>}
          </div>
        </aside>

        {/* Detalhe do bairro */}
        {current ? <BairroDetail d={current} city={city} trend={trends[current.resumo.bairro] || []} /> : (
          <div className="bg-slate-800/50 rounded-xl border border-slate-800 p-12 text-center text-slate-500">
            Selecione um bairro para ver a ficha.
          </div>
        )}
      </div>
    </div>
  )
}

function Delta({ val, city }: { val: number | null; city: number | null }) {
  if (val == null || !city) return null
  const pct = Math.round((100 * (val - city)) / city)
  if (Math.abs(pct) < 3) return <span className="inline-flex items-center gap-0.5 text-[10px] text-slate-400 ml-1"><Minus className="w-3 h-3" />na média</span>
  const up = pct > 0
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] ml-1 ${up ? 'text-amber-400' : 'text-emerald-400'}`}>
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {up ? '+' : ''}{pct}% vs cidade
    </span>
  )
}

function Sparkline({ points }: { points: TrendPoint[] }) {
  const w = 280, h = 60, pad = 5
  const ys = points.map(p => p.ppm2)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const rangeY = maxY - minY || 1
  const x = (i: number) => pad + (i / (points.length - 1)) * (w - 2 * pad)
  const y = (v: number) => h - pad - ((v - minY) / rangeY) * (h - 2 * pad)
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.ppm2).toFixed(1)}`).join(' ')
  const area = `${line} L${x(points.length - 1).toFixed(1)},${h - pad} L${x(0).toFixed(1)},${h - pad} Z`
  const last = points[points.length - 1]
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-16" preserveAspectRatio="none" role="img" aria-label="tendência de preço/m²">
      <defs>
        <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(129 140 248)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="rgb(129 140 248)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#spark)" />
      <path d={line} fill="none" stroke="rgb(129 140 248)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      <circle cx={x(points.length - 1)} cy={y(last.ppm2)} r="2.5" fill="rgb(165 180 252)" />
    </svg>
  )
}

function BairroDetail({ d, city, trend }: { d: BairroData; city: { ppm2: Record<string, number | null> }; trend: TrendPoint[] }) {
  const r = d.resumo
  const trendPct = trend.length >= 2 && trend[0].ppm2
    ? Math.round((100 * (trend[trend.length - 1].ppm2 - trend[0].ppm2)) / trend[0].ppm2)
    : null
  const types = TYPE_ORDER.filter(t => d.tipos[t] && (d.tipos[t].total || 0) > 0)
  const rentTypes = TYPE_ORDER.filter(t => d.tipos[t] && (d.tipos[t].aluguel_n || 0) > 0)
  const absTypes = TYPE_ORDER.filter(t => d.tipos[t] && (d.tipos[t].hist_total || 0) >= 2)
  const noise = NOISE.has(r.bairro)

  return (
    <section className="space-y-4 min-w-0">
      {/* Cabeçalho */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-800 p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500">Ficha do bairro</p>
            <h2 className="text-2xl font-bold text-white">{r.bairro}</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="text-[11px] bg-slate-700/50 text-slate-300 px-2.5 py-1 rounded-md">{r.listings_ativos} ativos · {r.listings_total} hist.</span>
            <span className="text-[11px] bg-slate-700/50 text-slate-300 px-2.5 py-1 rounded-md">{r.mcmv} MCMV</span>
            {r.acessibilidade_media != null && (
              <span className="text-[11px] bg-indigo-500/15 text-indigo-300 px-2.5 py-1 rounded-md">acessibilidade {Math.round(r.acessibilidade_media)}/100 · n={r.acc_n}</span>
            )}
            {r.avm_under > 0 && (
              <span className="text-[11px] bg-amber-500/15 text-amber-300 px-2.5 py-1 rounded-md">{r.avm_under} subprecificado{r.avm_under > 1 ? 's' : ''}</span>
            )}
          </div>
        </div>
        {noise && (
          <p className="flex items-center gap-1.5 text-[11px] text-rose-400 mt-3">
            <AlertTriangle className="w-3.5 h-3.5" /> Rótulo genérico (nome da cidade ou vazio). Trate como ruído de parse, não bairro real.
          </p>
        )}
      </div>

      {/* Preço por tipo */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-800 p-5">
        <h3 className="text-white font-semibold text-sm">Preço por tipo de imóvel</h3>
        <p className="text-xs text-slate-500 mb-4">Mediana do anunciado entre ativos. Delta compara com a mediana da cidade.</p>
        {types.length ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {types.map(t => {
              const tp = d.tipos[t]; const m = TYPE_META[t]; const Icon = m.icon
              return (
                <div key={t} className="bg-slate-900/50 rounded-lg border border-slate-800 p-4">
                  <div className="flex items-center gap-2 text-slate-300 text-sm font-medium">
                    <Icon className="w-4 h-4" /> {m.pt}
                  </div>
                  <p className="text-xl font-bold text-white mt-2 tabular-nums">{brl(tp.preco_mediano)}</p>
                  <p className="text-xs text-slate-400 tabular-nums">{ppm2(tp.ppm2_mediano)}<Delta val={tp.ppm2_mediano} city={city.ppm2[t]} /></p>
                  <div className="flex justify-between text-xs text-slate-500 mt-3 pt-2 border-t border-slate-800 tabular-nums">
                    <span>{tp.ativos} ativos</span>
                    <span>{tp.area_mediana ? `${Math.round(tp.area_mediana)} m²` : 'área —'}</span>
                  </div>
                </div>
              )
            })}
          </div>
        ) : <p className="text-slate-500 text-sm">Sem imóveis ativos com preço.</p>}
      </div>

      {/* Tendência de preço (terreno) */}
      {trend.length >= 2 && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-800 p-5">
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <div>
              <h3 className="text-white font-semibold text-sm">Tendência de preço/m² · terreno</h3>
              <p className="text-xs text-slate-500">Média por bairro ao longo das coletas ({trend.length} pontos).</p>
            </div>
            {trendPct != null && (
              <span className={`inline-flex items-center gap-1 text-xs font-medium ${trendPct > 0 ? 'text-emerald-400' : trendPct < 0 ? 'text-rose-400' : 'text-slate-400'}`}>
                {trendPct > 0 ? <TrendingUp className="w-3.5 h-3.5" /> : trendPct < 0 ? <TrendingDown className="w-3.5 h-3.5" /> : <Minus className="w-3.5 h-3.5" />}
                {trendPct > 0 ? '+' : ''}{trendPct}% no período
              </span>
            )}
          </div>
          <div className="mt-3">
            <Sparkline points={trend} />
            <div className="flex justify-between text-[11px] text-slate-500 mt-1 tabular-nums">
              <span>{ppm2(trend[0].ppm2)}<span className="text-slate-600 ml-1">{trend[0].date.slice(5)}</span></span>
              <span>{ppm2(trend[trend.length - 1].ppm2)}<span className="text-slate-600 ml-1">{trend[trend.length - 1].date.slice(5)}</span></span>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* Absorção */}
        <div className="bg-slate-800/50 rounded-xl border border-slate-800 p-5">
          <h3 className="text-white font-semibold text-sm">Velocidade de venda</h3>
          <p className="text-xs text-slate-500 mb-3">Anúncios que saíram do ar = proxy de vendido. Taxa alta e poucos dias = bairro que gira.</p>
          {absTypes.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                    <th className="text-left font-medium py-1.5">Tipo</th>
                    <th className="text-right font-medium">Hist.</th>
                    <th className="text-right font-medium">Saída</th>
                    <th className="text-right font-medium">Dias</th>
                    <th className="text-right font-medium">↓preço</th>
                  </tr>
                </thead>
                <tbody>
                  {absTypes.map(t => {
                    const a = d.tipos[t]
                    return (
                      <tr key={t} className="border-t border-slate-800/60 tabular-nums">
                        <td className="py-2 text-slate-300">{TYPE_META[t].pt}</td>
                        <td className="text-right text-slate-400">{a.hist_total}</td>
                        <td className="text-right text-white font-medium">{a.taxa_saida_pct != null ? `${a.taxa_saida_pct}%` : '—'}</td>
                        <td className="text-right text-slate-400">{a.dias_medio ? `${Math.round(a.dias_medio)}d` : '—'}</td>
                        <td className="text-right text-slate-400">{a.baixaram_preco || 0}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="text-slate-500 text-sm">Histórico insuficiente.</p>}
        </div>

        {/* Aluguel + oportunidade */}
        <div className="bg-slate-800/50 rounded-xl border border-slate-800 p-5">
          <h3 className="text-white font-semibold text-sm">Aluguel</h3>
          <p className="text-xs text-slate-500 mb-3">Mediana do aluguel anunciado por tipo.</p>
          {rentTypes.length ? (
            <div className="space-y-1.5">
              {rentTypes.map(t => (
                <div key={t} className="flex justify-between text-sm">
                  <span className="text-slate-400">{TYPE_META[t].pt} <span className="text-slate-600">({d.tipos[t].aluguel_n})</span></span>
                  <span className="text-white font-medium tabular-nums">{brl(d.tipos[t].aluguel_mediano)}/mês</span>
                </div>
              ))}
            </div>
          ) : <p className="text-slate-500 text-sm">Sem anúncios de aluguel.</p>}

          <h3 className="text-white font-semibold text-sm mt-5">Oportunidade</h3>
          <p className="text-xs text-slate-500 mb-2">Imóveis marcados como abaixo do valor justo (AVM).</p>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">Subprecificados</span>
            <span className="text-amber-400 font-semibold tabular-nums">{r.avm_under} de {r.avm_total}</span>
          </div>
        </div>
      </div>
    </section>
  )
}

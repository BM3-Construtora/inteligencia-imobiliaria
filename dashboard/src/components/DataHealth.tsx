import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Database,
  MapPin,
  DollarSign,
  Ruler,
  Building,
  AlertTriangle,
  Layers,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { supabase, fetchAllRows } from '../lib/supabase'
import { StatCard } from './StatCard'

interface AgentRun {
  id: number | string
  agent_name: string
  status: string
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  items_processed: number | null
  items_failed: number | null
}

interface AgentStat {
  agent_name: string
  total: number
  success: number
  failed: number
  successRate: number
  avgDurationSec: number
}

interface DataQualityRow {
  id: number | string
  created_at: string
  source: string | null
  rule: string | null
  severity: string | null
  details: unknown
}

interface SourceQuality {
  source: string
  total: number
  active: number
  geocoded: number
  withPrice: number
  quarantined: number
}

function relativeTime(iso: string): string {
  const d = new Date(iso).getTime()
  const now = Date.now()
  const diff = Math.max(0, now - d)
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s atras`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}min atras`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h atras`
  const days = Math.floor(h / 24)
  return `${days}d atras`
}

function formatDuration(ms: number | null): string {
  if (!ms || ms <= 0) return '-'
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rem = Math.floor(s % 60)
  return `${m}m ${rem}s`
}

function pct(num: number, total: number): string {
  if (!total) return '0.0%'
  return `${((num / total) * 100).toFixed(1)}%`
}

function StatusBadge({ status }: { status: string }) {
  const s = (status || '').toLowerCase()
  let cls = 'bg-slate-700/40 text-slate-300 border-slate-600/40'
  let Icon = Clock
  if (s === 'success' || s === 'completed' || s === 'ok') {
    cls = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
    Icon = CheckCircle2
  } else if (s === 'failed' || s === 'error') {
    cls = 'bg-rose-500/10 text-rose-400 border-rose-500/30'
    Icon = XCircle
  } else if (s === 'running' || s === 'in_progress' || s === 'started') {
    cls = 'bg-amber-500/10 text-amber-400 border-amber-500/30'
    Icon = Clock
  } else if (s === 'partial' || s === 'warning') {
    cls = 'bg-amber-500/10 text-amber-400 border-amber-500/30'
    Icon = AlertTriangle
  }
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded border ${cls}`}>
      <Icon className="w-3 h-3" />
      {status || '-'}
    </span>
  )
}

function SectionCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="bg-slate-900/40 border border-slate-800 rounded-xl p-5">
      <header className="mb-4">
        <h2 className="text-sm font-bold text-white">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </header>
      {children}
    </section>
  )
}

function LoadingRow({ cols = 6 }: { cols?: number }) {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-3 py-2"><div className="h-3 bg-slate-800 rounded w-3/4" /></td>
      ))}
    </tr>
  )
}

export function DataHealth() {
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [runsLoading, setRunsLoading] = useState(true)

  const [agentStats, setAgentStats] = useState<AgentStat[]>([])
  const [agentStatsLoading, setAgentStatsLoading] = useState(true)

  const [coverage, setCoverage] = useState({
    total: 0,
    geocoded: 0,
    withPrice: 0,
    withArea: 0,
    withNeighborhood: 0,
    quarantined: 0,
    deduped: 0,
  })
  const [coverageLoading, setCoverageLoading] = useState(true)

  const [qualityLog, setQualityLog] = useState<DataQualityRow[]>([])
  const [qualityLoading, setQualityLoading] = useState(true)
  const [ruleFilter, setRuleFilter] = useState<string>('all')

  const [sourceQuality, setSourceQuality] = useState<SourceQuality[]>([])
  const [sourceQualityLoading, setSourceQualityLoading] = useState(true)

  const [matchDist, setMatchDist] = useState<{ name: string; count: number }[]>([])
  const [matchLoading, setMatchLoading] = useState(true)

  // 1. Last 30 agent runs
  useEffect(() => {
    (async () => {
      const { data, error } = await supabase
        .from('agent_runs')
        .select('id, agent_name, status, started_at, finished_at, duration_ms, items_processed, items_failed')
        .order('started_at', { ascending: false })
        .limit(30)
      if (!error && data) setRuns(data as AgentRun[])
      setRunsLoading(false)
    })()
  }, [])

  // 2. Success rate per agent — fetch all rows paginated
  useEffect(() => {
    (async () => {
      const rows = await fetchAllRows<{ agent_name: string; status: string; duration_ms: number | null }>(
        (from) => from.select('agent_name, status, duration_ms'),
        'agent_runs',
      ).catch(() => [] as { agent_name: string; status: string; duration_ms: number | null }[])

      const map = new Map<string, { total: number; success: number; failed: number; durSum: number; durN: number }>()
      rows.forEach(r => {
        const name = r.agent_name ?? 'unknown'
        const m = map.get(name) ?? { total: 0, success: 0, failed: 0, durSum: 0, durN: 0 }
        m.total += 1
        const st = (r.status || '').toLowerCase()
        if (st === 'success' || st === 'completed' || st === 'ok') m.success += 1
        else if (st === 'failed' || st === 'error') m.failed += 1
        if (r.duration_ms && r.duration_ms > 0) { m.durSum += r.duration_ms; m.durN += 1 }
        map.set(name, m)
      })

      const stats: AgentStat[] = Array.from(map.entries()).map(([agent_name, m]) => ({
        agent_name,
        total: m.total,
        success: m.success,
        failed: m.failed,
        successRate: m.total > 0 ? (m.success / m.total) * 100 : 0,
        avgDurationSec: m.durN > 0 ? m.durSum / m.durN / 1000 : 0,
      })).sort((a, b) => b.total - a.total)

      setAgentStats(stats)
      setAgentStatsLoading(false)
    })()
  }, [])

  // 3. Coverage KPIs — all count: exact, head: true
  useEffect(() => {
    (async () => {
      const active = supabase.from('listings').select('id', { count: 'exact', head: true }).eq('is_active', true)
      const geocoded = supabase.from('listings').select('id', { count: 'exact', head: true })
        .eq('is_active', true).not('latitude', 'is', null).not('longitude', 'is', null)
      const withPrice = supabase.from('listings').select('id', { count: 'exact', head: true })
        .eq('is_active', true).not('sale_price', 'is', null)
      const withArea = supabase.from('listings').select('id', { count: 'exact', head: true })
        .eq('is_active', true).not('total_area', 'is', null)
      const withNeighborhood = supabase.from('listings').select('id', { count: 'exact', head: true })
        .eq('is_active', true).not('neighborhood', 'is', null)
      const quarantined = supabase.from('listings').select('id', { count: 'exact', head: true }).eq('quarantined', true)
      const deduped = supabase.from('listings').select('id', { count: 'exact', head: true })
        .eq('is_active', true).not('canonical_listing_id', 'is', null)

      const safe = async (p: PromiseLike<{ count: number | null }>): Promise<{ count: number | null }> => {
        try { return await p } catch { return { count: 0 } }
      }
      const [a, g, p, ar, n, q, d] = await Promise.all([
        safe(active), safe(geocoded), safe(withPrice), safe(withArea), safe(withNeighborhood),
        safe(quarantined), safe(deduped),
      ])

      setCoverage({
        total: a.count ?? 0,
        geocoded: g.count ?? 0,
        withPrice: p.count ?? 0,
        withArea: ar.count ?? 0,
        withNeighborhood: n.count ?? 0,
        quarantined: q.count ?? 0,
        deduped: d.count ?? 0,
      })
      setCoverageLoading(false)
    })()
  }, [])

  // 4. Data quality log — last 50
  useEffect(() => {
    (async () => {
      const { data, error } = await supabase
        .from('data_quality_log')
        .select('id, created_at, source, rule, severity, details')
        .order('created_at', { ascending: false })
        .limit(50)
      if (!error && data) setQualityLog(data as DataQualityRow[])
      setQualityLoading(false)
    })()
  }, [])

  const availableRules = useMemo(() => {
    const set = new Set<string>()
    qualityLog.forEach(r => { if (r.rule) set.add(r.rule) })
    return Array.from(set).sort()
  }, [qualityLog])

  const filteredQuality = useMemo(() => {
    if (ruleFilter === 'all') return qualityLog
    return qualityLog.filter(r => r.rule === ruleFilter)
  }, [qualityLog, ruleFilter])

  // 5. Quality per source
  useEffect(() => {
    (async () => {
      const rows = await fetchAllRows<{
        source: string | null
        is_active: boolean | null
        latitude: number | null
        longitude: number | null
        sale_price: number | null
        quarantined: boolean | null
      }>(
        (from) => from.select('source, is_active, latitude, longitude, sale_price, quarantined'),
        'listings',
      ).catch(() => [])

      const map = new Map<string, SourceQuality>()
      rows.forEach(r => {
        const s = r.source ?? 'unknown'
        const cur = map.get(s) ?? { source: s, total: 0, active: 0, geocoded: 0, withPrice: 0, quarantined: 0 }
        cur.total += 1
        if (r.is_active) cur.active += 1
        if (r.latitude != null && r.longitude != null) cur.geocoded += 1
        if (r.sale_price != null) cur.withPrice += 1
        if (r.quarantined) cur.quarantined += 1
        map.set(s, cur)
      })

      setSourceQuality(Array.from(map.values()).sort((a, b) => b.total - a.total))
      setSourceQualityLoading(false)
    })()
  }, [])

  // 6. Match method distribution (decision_rule with fallback to match_method)
  useEffect(() => {
    (async () => {
      const rows = await fetchAllRows<{ decision_rule: string | null; match_method: string | null }>(
        (from) => from.select('decision_rule, match_method'),
        'listing_matches',
      ).catch(() => [])

      const map = new Map<string, number>()
      rows.forEach(r => {
        const key = (r.decision_rule ?? r.match_method ?? 'unknown') as string
        map.set(key, (map.get(key) ?? 0) + 1)
      })

      const dist = Array.from(map.entries())
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count)

      setMatchDist(dist)
      setMatchLoading(false)
    })()
  }, [])

  return (
    <div className="space-y-6">
      {/* 1. Pipeline Status */}
      <SectionCard title="Status do Pipeline" subtitle="Ultimas 30 execucoes dos agentes">
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800">
                <th className="text-left font-medium px-3 py-2">Agente</th>
                <th className="text-left font-medium px-3 py-2">Status</th>
                <th className="text-left font-medium px-3 py-2">Inicio</th>
                <th className="text-left font-medium px-3 py-2">Duracao</th>
                <th className="text-right font-medium px-3 py-2">Processados</th>
                <th className="text-right font-medium px-3 py-2">Falhas</th>
              </tr>
            </thead>
            <tbody>
              {runsLoading && Array.from({ length: 5 }).map((_, i) => <LoadingRow key={i} />)}
              {!runsLoading && runs.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-500">Nenhuma execucao registrada</td></tr>
              )}
              {!runsLoading && runs.map(r => {
                const isFailed = (r.status || '').toLowerCase() === 'failed' || (r.status || '').toLowerCase() === 'error'
                return (
                  <tr key={r.id} className={`border-b border-slate-800/50 ${isFailed ? 'bg-rose-500/5' : ''}`}>
                    <td className="px-3 py-2 text-white font-medium">{r.agent_name ?? '-'}</td>
                    <td className="px-3 py-2"><StatusBadge status={r.status} /></td>
                    <td className="px-3 py-2 text-slate-400">{r.started_at ? relativeTime(r.started_at) : '-'}</td>
                    <td className="px-3 py-2 text-slate-400">{formatDuration(r.duration_ms)}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{r.items_processed ?? '-'}</td>
                    <td className={`px-3 py-2 text-right ${r.items_failed ? 'text-rose-400' : 'text-slate-500'}`}>{r.items_failed ?? '-'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {/* 2. Success rate per agent */}
      <SectionCard title="Taxa de Sucesso por Agente" subtitle="Agregado historico de todas as execucoes">
        {agentStatsLoading ? (
          <div className="text-xs text-slate-500">Carregando...</div>
        ) : agentStats.length === 0 ? (
          <div className="text-xs text-slate-500">Nenhum agente registrado</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {agentStats.map(a => {
              const rateColor = a.successRate >= 95 ? 'text-emerald-400'
                : a.successRate >= 80 ? 'text-amber-400'
                : 'text-rose-400'
              return (
                <div key={a.agent_name} className="bg-slate-800/40 border border-slate-800 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-bold text-white truncate">{a.agent_name}</p>
                    <span className="text-[10px] text-slate-500">{a.total} runs</span>
                  </div>
                  <div className="flex items-end justify-between">
                    <div>
                      <p className={`text-2xl font-bold ${rateColor}`}>{a.successRate.toFixed(1)}%</p>
                      <p className="text-[10px] text-slate-500 mt-0.5">{a.success} ok / {a.failed} falhas</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-300">{a.avgDurationSec.toFixed(1)}s</p>
                      <p className="text-[10px] text-slate-500">duracao media</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </SectionCard>

      {/* 3. Coverage KPIs */}
      <SectionCard title="Cobertura dos Dados" subtitle="Qualidade do dataset ativo">
        {coverageLoading ? (
          <div className="text-xs text-slate-500">Carregando...</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            <StatCard label="Anuncios Ativos" value={coverage.total.toLocaleString('pt-BR')} sub="total de listings ativos" icon={Database} accent="indigo" />
            <StatCard label="Geocodificados" value={pct(coverage.geocoded, coverage.total)} sub={`${coverage.geocoded.toLocaleString('pt-BR')} com lat/lng`} icon={MapPin} accent="sky" />
            <StatCard label="Com Preco" value={pct(coverage.withPrice, coverage.total)} sub={`${coverage.withPrice.toLocaleString('pt-BR')} com sale_price`} icon={DollarSign} accent="emerald" />
            <StatCard label="Com Area" value={pct(coverage.withArea, coverage.total)} sub={`${coverage.withArea.toLocaleString('pt-BR')} com total_area`} icon={Ruler} accent="amber" />
            <StatCard label="Com Bairro" value={pct(coverage.withNeighborhood, coverage.total)} sub={`${coverage.withNeighborhood.toLocaleString('pt-BR')} com neighborhood`} icon={Building} accent="indigo" />
            <StatCard label="Em Quarentena" value={coverage.quarantined.toLocaleString('pt-BR')} sub="anuncios suspeitos" icon={AlertTriangle} accent="rose" />
            <StatCard label="Taxa Dedup" value={pct(coverage.deduped, coverage.total)} sub={`${coverage.deduped.toLocaleString('pt-BR')} canonicalizados`} icon={Layers} accent="sky" />
          </div>
        )}
      </SectionCard>

      {/* 4. Data Quality Log */}
      <SectionCard title="Log de Qualidade de Dados" subtitle="Ultimos 50 eventos">
        <div className="flex items-center gap-2 mb-3">
          <label className="text-[10px] text-slate-500 uppercase tracking-wider">Filtro por regra</label>
          <select
            value={ruleFilter}
            onChange={e => setRuleFilter(e.target.value)}
            className="text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded px-2 py-1 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">Todas</option>
            {availableRules.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800">
                <th className="text-left font-medium px-3 py-2">Quando</th>
                <th className="text-left font-medium px-3 py-2">Source</th>
                <th className="text-left font-medium px-3 py-2">Regra</th>
                <th className="text-left font-medium px-3 py-2">Severidade</th>
                <th className="text-left font-medium px-3 py-2">Detalhes</th>
              </tr>
            </thead>
            <tbody>
              {qualityLoading && Array.from({ length: 5 }).map((_, i) => <LoadingRow key={i} cols={5} />)}
              {!qualityLoading && filteredQuality.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-500">Nenhum evento registrado</td></tr>
              )}
              {!qualityLoading && filteredQuality.map(r => {
                const sev = (r.severity ?? '').toLowerCase()
                const sevCls = sev === 'error' || sev === 'critical'
                  ? 'text-rose-400'
                  : sev === 'warning' || sev === 'warn'
                  ? 'text-amber-400'
                  : 'text-slate-400'
                const detailStr = (() => {
                  try {
                    const s = typeof r.details === 'string' ? r.details : JSON.stringify(r.details)
                    return (s ?? '').slice(0, 120)
                  } catch {
                    return '-'
                  }
                })()
                return (
                  <tr key={r.id} className="border-b border-slate-800/50">
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{r.created_at ? relativeTime(r.created_at) : '-'}</td>
                    <td className="px-3 py-2 text-slate-300">{r.source ?? '-'}</td>
                    <td className="px-3 py-2 text-white">{r.rule ?? '-'}</td>
                    <td className={`px-3 py-2 ${sevCls}`}>{r.severity ?? '-'}</td>
                    <td className="px-3 py-2 text-slate-500 font-mono text-[10px] max-w-md truncate">{detailStr}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {/* 5. Quality by source */}
      <SectionCard title="Qualidade por Fonte" subtitle="Cobertura agregada por origem dos dados">
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800">
                <th className="text-left font-medium px-3 py-2">Fonte</th>
                <th className="text-right font-medium px-3 py-2">Total</th>
                <th className="text-right font-medium px-3 py-2">Ativos</th>
                <th className="text-right font-medium px-3 py-2">Geocoded</th>
                <th className="text-right font-medium px-3 py-2">Com Preco</th>
                <th className="text-right font-medium px-3 py-2">Quarentena</th>
              </tr>
            </thead>
            <tbody>
              {sourceQualityLoading && Array.from({ length: 4 }).map((_, i) => <LoadingRow key={i} cols={6} />)}
              {!sourceQualityLoading && sourceQuality.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-500">Sem dados</td></tr>
              )}
              {!sourceQualityLoading && sourceQuality.map(s => (
                <tr key={s.source} className="border-b border-slate-800/50">
                  <td className="px-3 py-2 text-white font-medium">{s.source}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{s.total.toLocaleString('pt-BR')}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{s.active.toLocaleString('pt-BR')}</td>
                  <td className="px-3 py-2 text-right text-sky-400">{pct(s.geocoded, s.total)}</td>
                  <td className="px-3 py-2 text-right text-emerald-400">{pct(s.withPrice, s.total)}</td>
                  <td className={`px-3 py-2 text-right ${s.quarantined > 0 ? 'text-rose-400' : 'text-slate-500'}`}>{s.quarantined.toLocaleString('pt-BR')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {/* 6. Match method distribution */}
      <SectionCard title="Distribuicao de Metodos de Match" subtitle="Por decision_rule (fallback: match_method)">
        {matchLoading ? (
          <div className="text-xs text-slate-500">Carregando...</div>
        ) : matchDist.length === 0 ? (
          <div className="text-xs text-slate-500">Nenhum match registrado</div>
        ) : (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={matchDist} margin={{ top: 10, right: 20, left: 10, bottom: 50 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} angle={-25} textAnchor="end" interval={0} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#e2e8f0' }}
                />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </SectionCard>
    </div>
  )
}

export const DataHealthIcon = Activity

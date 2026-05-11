import { useEffect, useState, useCallback } from 'react'
import { ExternalLink, Check, X, SkipForward } from 'lucide-react'
import { supabase } from '../lib/supabase'

interface MatchRow {
  id: number
  listing_a_id: number
  listing_b_id: number
  match_score: number
  decision_rule: string | null
  addr_score: number | null
  geo_distance_m: number | null
  price_diff_pct: number | null
  area_diff_pct: number | null
  bed_match: boolean | null
  bath_match: boolean | null
  a_source: string | null
  a_title: string | null
  a_address: string | null
  a_neighborhood: string | null
  a_price: number | null
  a_area: number | null
  a_url: string | null
  b_source: string | null
  b_title: string | null
  b_address: string | null
  b_neighborhood: string | null
  b_price: number | null
  b_area: number | null
  b_url: string | null
  created_at: string
}

const PAGE_SIZE = 20

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
}

function fmtArea(n: number | null | undefined): string {
  if (n == null) return '-'
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })} m²`
}

function Chip({ label, value, tone = 'default' }: { label: string; value: string; tone?: 'default' | 'good' | 'bad' | 'warn' }) {
  const toneClass =
    tone === 'good' ? 'bg-emerald-900/40 text-emerald-300 border-emerald-700/50'
    : tone === 'bad' ? 'bg-rose-900/40 text-rose-300 border-rose-700/50'
    : tone === 'warn' ? 'bg-amber-900/40 text-amber-300 border-amber-700/50'
    : 'bg-slate-800/80 text-slate-300 border-slate-700'
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded border font-mono ${toneClass}`}>
      <span className="opacity-60">{label}:</span> {value}
    </span>
  )
}

function ListingCard({ side, source, title, address, neighborhood, price, area, url }: {
  side: 'A' | 'B'
  source: string | null
  title: string | null
  address: string | null
  neighborhood: string | null
  price: number | null
  area: number | null
  url: string | null
}) {
  return (
    <div className="flex-1 bg-slate-900/60 rounded-xl border border-slate-700 p-4 min-w-0">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold text-indigo-400 bg-indigo-500/10 border border-indigo-500/30 px-2 py-0.5 rounded">
          Listing {side}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
          {source || '-'}
        </span>
      </div>
      <h3 className="text-sm font-medium text-white line-clamp-2 mb-1" title={title || ''}>
        {title || 'Sem titulo'}
      </h3>
      <p className="text-xs text-slate-400 line-clamp-1 mb-0.5">{address || '-'}</p>
      <p className="text-xs text-slate-500 mb-3">{neighborhood || '-'}</p>
      <div className="flex items-center gap-4 text-xs">
        <span className="text-emerald-400 font-mono font-semibold">{fmt(price)}</span>
        <span className="text-slate-300 font-mono">{fmtArea(area)}</span>
      </div>
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300"
        >
          Ver anuncio <ExternalLink className="w-3 h-3" />
        </a>
      )}
    </div>
  )
}

export function MatchReview() {
  const [rows, setRows] = useState<MatchRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [submitting, setSubmitting] = useState<number | null>(null)
  const [stats, setStats] = useState({ reviewed: 0, approved: 0, rejected: 0 })

  const loadStats = useCallback(async () => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const iso = today.toISOString()

    const [approved, rejected] = await Promise.all([
      supabase.from('listing_matches').select('id', { count: 'exact', head: true })
        .eq('confirmed', true).gte('updated_at', iso),
      supabase.from('listing_matches').select('id', { count: 'exact', head: true })
        .eq('confirmed', false).gte('updated_at', iso),
    ])

    const a = approved.count || 0
    const r = rejected.count || 0
    setStats({ reviewed: a + r, approved: a, rejected: r })
  }, [])

  const load = useCallback(async (pageIdx: number) => {
    setLoading(true)
    setError(null)
    try {
      const from = pageIdx * PAGE_SIZE
      const to = from + PAGE_SIZE - 1
      const { data, error: err, count } = await supabase
        .from('match_review_queue')
        .select('*', { count: 'exact' })
        .range(from, to)

      if (err) throw err
      setRows((data as unknown as MatchRow[]) || [])
      setTotal(count || 0)
    } catch (e: any) {
      setError(e.message || 'Erro ao carregar fila')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(page) }, [load, page])
  useEffect(() => { loadStats() }, [loadStats])

  async function decide(matchId: number, confirmed: boolean | null) {
    setSubmitting(matchId)
    try {
      if (confirmed === null) {
        // Skip: just remove locally
        setRows(prev => prev.filter(r => r.id !== matchId))
      } else {
        const { error: err } = await supabase
          .from('listing_matches')
          .update({ confirmed, updated_at: new Date().toISOString() })
          .eq('id', matchId)
        if (err) throw err
        setRows(prev => prev.filter(r => r.id !== matchId))
        setStats(s => ({
          reviewed: s.reviewed + 1,
          approved: s.approved + (confirmed ? 1 : 0),
          rejected: s.rejected + (confirmed ? 0 : 1),
        }))
      }

      // If page emptied, reload (in case there are more rows after current page)
      if (rows.length <= 1 && total > PAGE_SIZE) {
        load(page)
      }
    } catch (e: any) {
      setError(e.message || 'Erro ao salvar decisao')
    } finally {
      setSubmitting(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-4">
      {/* Counter */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 flex flex-wrap items-center gap-6">
        <div>
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Revisados hoje</p>
          <p className="text-2xl font-bold text-white font-mono">{stats.reviewed}</p>
        </div>
        <div>
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Aprovados</p>
          <p className="text-2xl font-bold text-emerald-400 font-mono">{stats.approved}</p>
        </div>
        <div>
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Rejeitados</p>
          <p className="text-2xl font-bold text-rose-400 font-mono">{stats.rejected}</p>
        </div>
        <div className="ml-auto text-right">
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Fila pendente</p>
          <p className="text-2xl font-bold text-indigo-400 font-mono">{total}</p>
        </div>
      </div>

      {error && (
        <div className="bg-rose-900/30 border border-rose-700/50 text-rose-300 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-slate-400 py-12 text-center">Carregando fila de revisao...</div>
      ) : rows.length === 0 ? (
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-12 text-center">
          <p className="text-slate-300 text-sm">Nenhum match pendente nesta pagina.</p>
          <p className="text-slate-500 text-xs mt-1">A fila so mostra matches com score entre 0.70 e 0.90.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {rows.map(row => {
            const isBusy = submitting === row.id
            return (
              <div key={row.id} className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                <div className="flex flex-col md:flex-row gap-4 p-4">
                  <ListingCard
                    side="A"
                    source={row.a_source}
                    title={row.a_title}
                    address={row.a_address}
                    neighborhood={row.a_neighborhood}
                    price={row.a_price}
                    area={row.a_area}
                    url={row.a_url}
                  />
                  <ListingCard
                    side="B"
                    source={row.b_source}
                    title={row.b_title}
                    address={row.b_address}
                    neighborhood={row.b_neighborhood}
                    price={row.b_price}
                    area={row.b_area}
                    url={row.b_url}
                  />
                </div>

                {/* Metadata chips */}
                <div className="px-4 pb-3 flex flex-wrap gap-1.5">
                  <Chip label="score" value={row.match_score?.toFixed(3) ?? '-'} tone={row.match_score >= 0.85 ? 'good' : 'warn'} />
                  {row.decision_rule && <Chip label="rule" value={row.decision_rule} />}
                  {row.addr_score != null && <Chip label="addr" value={`${(row.addr_score * 100).toFixed(0)}%`} />}
                  {row.geo_distance_m != null && <Chip label="geo" value={`${row.geo_distance_m.toFixed(0)}m`} />}
                  {row.price_diff_pct != null && <Chip label="preco diff" value={`${row.price_diff_pct.toFixed(1)}%`} />}
                  {row.area_diff_pct != null && <Chip label="area diff" value={`${row.area_diff_pct.toFixed(1)}%`} />}
                  <Chip label="quartos" value={row.bed_match ? 'match' : 'diff'} tone={row.bed_match ? 'good' : 'bad'} />
                  <Chip label="banh" value={row.bath_match ? 'match' : 'diff'} tone={row.bath_match ? 'good' : 'bad'} />
                </div>

                {/* Actions */}
                <div className="border-t border-slate-700 bg-slate-900/40 p-3 flex gap-2 justify-end">
                  <button
                    disabled={isBusy}
                    onClick={() => decide(row.id, false)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 text-rose-300 border border-rose-700/40 text-xs font-medium disabled:opacity-40"
                  >
                    <X className="w-3.5 h-3.5" /> Nao, diferentes
                  </button>
                  <button
                    disabled={isBusy}
                    onClick={() => decide(row.id, null)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/40 hover:bg-slate-700/60 text-slate-300 border border-slate-600/40 text-xs font-medium disabled:opacity-40"
                  >
                    <SkipForward className="w-3.5 h-3.5" /> Pular
                  </button>
                  <button
                    disabled={isBusy}
                    onClick={() => decide(row.id, true)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600/15 hover:bg-emerald-600/25 text-emerald-300 border border-emerald-700/40 text-xs font-medium disabled:opacity-40"
                  >
                    <Check className="w-3.5 h-3.5" /> Sim, e o mesmo
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between bg-slate-800 rounded-xl border border-slate-700 px-4 py-3">
          <p className="text-xs text-slate-400">
            Pagina {page + 1} de {totalPages} — {total} matches pendentes
          </p>
          <div className="flex gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(0, p - 1))}
              className="px-3 py-1.5 text-xs rounded-lg bg-slate-700 hover:bg-slate-600 text-white disabled:opacity-40"
            >
              Anterior
            </button>
            <button
              disabled={page + 1 >= totalPages}
              onClick={() => setPage(p => p + 1)}
              className="px-3 py-1.5 text-xs rounded-lg bg-slate-700 hover:bg-slate-600 text-white disabled:opacity-40"
            >
              Proxima
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

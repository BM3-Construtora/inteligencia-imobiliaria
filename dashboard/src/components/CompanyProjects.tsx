import { useCallback, useEffect, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { supabase } from '../lib/supabase'

interface CompanyProject {
  id: number
  name: string
  land_listing_id: number | null
  neighborhood: string | null
  project_type: string
  units: number
  land_cost: number | null
  construction_cost_projected: number | null
  construction_cost_actual: number | null
  revenue_projected: number | null
  revenue_actual: number | null
  margin_projected_pct: number | null
  margin_actual_pct: number | null
  sale_price_per_unit: number | null
  construction_months: number | null
  roi_actual_pct: number | null
  status: string
  started_at: string | null
  completed_at: string | null
  notes: string | null
  created_at: string
}

const PROJECT_TYPES = [
  { value: 'mcmv_faixa1', label: 'MCMV Faixa 1' },
  { value: 'mcmv_faixa2', label: 'MCMV Faixa 2' },
  { value: 'mcmv_faixa3', label: 'MCMV Faixa 3' },
  { value: 'casa_padrao', label: 'Casa Padrao' },
]

const STATUSES = [
  { value: 'planning', label: 'Planejamento' },
  { value: 'approved', label: 'Aprovado' },
  { value: 'construction', label: 'Construcao' },
  { value: 'selling', label: 'Vendendo' },
  { value: 'sold_out', label: 'Vendido' },
  { value: 'cancelled', label: 'Cancelado' },
]

const STATUS_TONE: Record<string, string> = {
  planning: 'bg-slate-700 text-slate-300',
  approved: 'bg-indigo-900/50 text-indigo-300 border border-indigo-700/40',
  construction: 'bg-amber-900/40 text-amber-300 border border-amber-700/40',
  selling: 'bg-sky-900/40 text-sky-300 border border-sky-700/40',
  sold_out: 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/40',
  cancelled: 'bg-rose-900/40 text-rose-300 border border-rose-700/40',
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
}

function vgvProjetado(p: CompanyProject): number | null {
  if (p.sale_price_per_unit == null || p.units == null) return null
  return p.sale_price_per_unit * p.units
}

function margemProjetada(p: CompanyProject): number | null {
  const vgv = vgvProjetado(p)
  if (!vgv) return p.margin_projected_pct
  const custos = (p.land_cost || 0) + (p.construction_cost_projected || 0)
  if (custos <= 0) return null
  return ((vgv - custos) / vgv) * 100
}

interface FormState {
  name: string
  land_listing_id: string
  neighborhood: string
  project_type: string
  units: string
  land_cost: string
  construction_cost_projected: string
  construction_months: string
  sale_price_per_unit: string
  status: string
  notes: string
}

const EMPTY_FORM: FormState = {
  name: '',
  land_listing_id: '',
  neighborhood: '',
  project_type: 'mcmv_faixa2',
  units: '1',
  land_cost: '',
  construction_cost_projected: '',
  construction_months: '',
  sale_price_per_unit: '',
  status: 'planning',
  notes: '',
}

function ProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function update<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm(f => ({ ...f, [k]: v }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) { setError('Nome e obrigatorio'); return }
    setSaving(true)
    setError(null)
    try {
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        project_type: form.project_type,
        units: parseInt(form.units) || 1,
        status: form.status,
      }
      if (form.land_listing_id) payload.land_listing_id = parseInt(form.land_listing_id)
      if (form.neighborhood.trim()) payload.neighborhood = form.neighborhood.trim()
      if (form.land_cost) payload.land_cost = parseFloat(form.land_cost)
      if (form.construction_cost_projected) payload.construction_cost_projected = parseFloat(form.construction_cost_projected)
      if (form.construction_months) payload.construction_months = parseInt(form.construction_months)
      if (form.sale_price_per_unit) payload.sale_price_per_unit = parseFloat(form.sale_price_per_unit)
      if (form.notes.trim()) payload.notes = form.notes.trim()

      const { error: err } = await supabase.from('company_projects').insert(payload)
      if (err) throw err
      onCreated()
      onClose()
    } catch (e: any) {
      setError(e.message || 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[2000] bg-black/60 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto">
      <div className="bg-slate-900 rounded-xl border border-slate-700 w-full max-w-2xl my-8">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h2 className="text-base font-semibold text-white">Novo Projeto BM3</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={submit} className="p-4 space-y-3">
          {error && (
            <div className="bg-rose-900/30 border border-rose-700/50 text-rose-300 text-xs rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <Field label="Nome do projeto *">
            <input
              required
              value={form.name}
              onChange={e => update('name', e.target.value)}
              className="form-input"
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Tipo de projeto">
              <select value={form.project_type} onChange={e => update('project_type', e.target.value)} className="form-input">
                {PROJECT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </Field>
            <Field label="Status">
              <select value={form.status} onChange={e => update('status', e.target.value)} className="form-input">
                {STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Bairro">
              <input value={form.neighborhood} onChange={e => update('neighborhood', e.target.value)} className="form-input" />
            </Field>
            <Field label="ID do terreno (listing)">
              <input
                type="number"
                value={form.land_listing_id}
                onChange={e => update('land_listing_id', e.target.value)}
                className="form-input"
                placeholder="opcional"
              />
            </Field>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Field label="Unidades">
              <input type="number" min={1} value={form.units} onChange={e => update('units', e.target.value)} className="form-input" />
            </Field>
            <Field label="Meses de obra">
              <input type="number" value={form.construction_months} onChange={e => update('construction_months', e.target.value)} className="form-input" />
            </Field>
            <Field label="Preco/unidade (R$)">
              <input type="number" step="0.01" value={form.sale_price_per_unit} onChange={e => update('sale_price_per_unit', e.target.value)} className="form-input" />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Custo do terreno (R$)">
              <input type="number" step="0.01" value={form.land_cost} onChange={e => update('land_cost', e.target.value)} className="form-input" />
            </Field>
            <Field label="Custo construcao projetado (R$)">
              <input type="number" step="0.01" value={form.construction_cost_projected} onChange={e => update('construction_cost_projected', e.target.value)} className="form-input" />
            </Field>
          </div>

          <Field label="Notas">
            <textarea
              value={form.notes}
              onChange={e => update('notes', e.target.value)}
              rows={3}
              className="form-input resize-none"
            />
          </Field>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50"
            >
              {saving ? 'Salvando...' : 'Salvar projeto'}
            </button>
          </div>
        </form>
      </div>

      <style>{`
        .form-input {
          width: 100%;
          background: rgb(15 23 42);
          border: 1px solid rgb(51 65 85);
          border-radius: 0.5rem;
          padding: 0.5rem 0.75rem;
          color: white;
          font-size: 0.875rem;
        }
        .form-input:focus { outline: none; border-color: rgb(99 102 241); }
      `}</style>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider text-slate-400 mb-1 block">{label}</span>
      {children}
    </label>
  )
}

export function CompanyProjects() {
  const [projects, setProjects] = useState<CompanyProject[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data, error: err } = await supabase
        .from('company_projects')
        .select('*')
        .order('created_at', { ascending: false })
      if (err) throw err
      setProjects((data as CompanyProject[]) || [])
    } catch (e: any) {
      setError(e.message || 'Erro ao carregar projetos')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-4">
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 flex items-center justify-between">
        <div>
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Projetos cadastrados</p>
          <p className="text-2xl font-bold text-white font-mono">{projects.length}</p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
        >
          <Plus className="w-4 h-4" /> Novo projeto
        </button>
      </div>

      {error && (
        <div className="bg-rose-900/30 border border-rose-700/50 text-rose-300 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-left border-b border-slate-700 text-xs uppercase tracking-wider">
                <th className="px-4 py-3 font-medium">Nome</th>
                <th className="px-4 py-3 font-medium">Tipo</th>
                <th className="px-4 py-3 font-medium">Bairro</th>
                <th className="px-4 py-3 font-medium text-right">Unid.</th>
                <th className="px-4 py-3 font-medium text-right">Preco/un</th>
                <th className="px-4 py-3 font-medium text-right">VGV proj.</th>
                <th className="px-4 py-3 font-medium text-right">Margem proj.</th>
                <th className="px-4 py-3 font-medium text-right">Custo terreno</th>
                <th className="px-4 py-3 font-medium text-right">Custo obra</th>
                <th className="px-4 py-3 font-medium text-right">Meses</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={11} className="px-4 py-12 text-center text-slate-400">Carregando...</td></tr>
              ) : projects.length === 0 ? (
                <tr><td colSpan={11} className="px-4 py-12 text-center text-slate-400">Nenhum projeto cadastrado ainda.</td></tr>
              ) : projects.map(p => {
                const vgv = vgvProjetado(p)
                const margem = margemProjetada(p)
                const statusInfo = STATUSES.find(s => s.value === p.status)
                return (
                  <tr key={p.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 text-white font-medium">{p.name}</td>
                    <td className="px-4 py-3 text-slate-300 text-xs">
                      {PROJECT_TYPES.find(t => t.value === p.project_type)?.label || p.project_type}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{p.neighborhood || '-'}</td>
                    <td className="px-4 py-3 text-right text-slate-300 font-mono">{p.units}</td>
                    <td className="px-4 py-3 text-right text-slate-300 font-mono">{fmt(p.sale_price_per_unit)}</td>
                    <td className="px-4 py-3 text-right text-emerald-400 font-mono">{fmt(vgv)}</td>
                    <td className="px-4 py-3 text-right font-mono">
                      {margem != null
                        ? <span className={margem >= 20 ? 'text-emerald-400' : margem >= 10 ? 'text-amber-400' : 'text-rose-400'}>{margem.toFixed(1)}%</span>
                        : <span className="text-slate-500">-</span>}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300 font-mono">{fmt(p.land_cost)}</td>
                    <td className="px-4 py-3 text-right text-slate-300 font-mono">{fmt(p.construction_cost_projected)}</td>
                    <td className="px-4 py-3 text-right text-slate-300 font-mono">{p.construction_months ?? '-'}</td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${STATUS_TONE[p.status] || 'bg-slate-700 text-slate-300'}`}>
                        {statusInfo?.label || p.status}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {modalOpen && <ProjectModal onClose={() => setModalOpen(false)} onCreated={load} />}
    </div>
  )
}

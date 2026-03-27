import type { LucideIcon } from 'lucide-react'

interface StatCardProps {
  label: string
  value: string | number
  sub?: string
  icon?: LucideIcon
  trend?: 'up' | 'down' | 'neutral'
  accent?: 'indigo' | 'emerald' | 'amber' | 'rose' | 'sky'
}

const ACCENT_MAP = {
  indigo: { bg: 'bg-indigo-500/10', text: 'text-indigo-400', border: 'border-indigo-500/20' },
  emerald: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  amber: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  rose: { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/20' },
  sky: { bg: 'bg-sky-500/10', text: 'text-sky-400', border: 'border-sky-500/20' },
}

export function StatCard({ label, value, sub, icon: Icon, accent = 'indigo' }: StatCardProps) {
  const colors = ACCENT_MAP[accent]

  return (
    <div className={`bg-slate-800/50 rounded-xl p-5 border ${colors.border} hover:bg-slate-800 transition-colors`}>
      <div className="flex items-start justify-between mb-3">
        <p className="text-slate-400 text-xs font-medium uppercase tracking-wider">{label}</p>
        {Icon && (
          <div className={`w-8 h-8 rounded-lg ${colors.bg} flex items-center justify-center`}>
            <Icon className={`w-4 h-4 ${colors.text}`} />
          </div>
        )}
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  )
}

import {
  LayoutDashboard,
  Map,
  Target,
  Calculator,
  BarChart3,
  Table2,
  ChevronLeft,
  ChevronRight,
  Building2,
} from 'lucide-react'

export type Page = 'overview' | 'map' | 'decision' | 'viability' | 'market' | 'opportunities'

const NAV_ITEMS: { key: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { key: 'overview', label: 'Visao Geral', icon: LayoutDashboard },
  { key: 'map', label: 'Mapa', icon: Map },
  { key: 'decision', label: 'Decisao', icon: Target },
  { key: 'viability', label: 'Viabilidade', icon: Calculator },
  { key: 'market', label: 'Mercado', icon: BarChart3 },
  { key: 'opportunities', label: 'Oportunidades', icon: Table2 },
]

interface SidebarProps {
  activePage: Page
  onPageChange: (page: Page) => void
  collapsed: boolean
  onToggleCollapse: () => void
}

export function Sidebar({ activePage, onPageChange, collapsed, onToggleCollapse }: SidebarProps) {
  return (
    <aside
      className={`fixed top-0 left-0 h-screen bg-slate-950 border-r border-slate-800 z-[1002] flex flex-col transition-all duration-300 ${
        collapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-slate-800 shrink-0">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shrink-0">
          <Building2 className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <div className="overflow-hidden">
            <p className="text-white font-bold text-sm leading-tight">MariliaBot</p>
            <p className="text-slate-500 text-[10px] leading-tight">Inteligencia Imobiliaria</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
          const active = activePage === key
          return (
            <button
              key={key}
              onClick={() => onPageChange(key)}
              title={collapsed ? label : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                active
                  ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60 border border-transparent'
              }`}
            >
              <Icon className={`w-[18px] h-[18px] shrink-0 ${active ? 'text-indigo-400' : ''}`} />
              {!collapsed && <span>{label}</span>}
            </button>
          )
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={onToggleCollapse}
        className="flex items-center justify-center h-12 border-t border-slate-800 text-slate-500 hover:text-white transition-colors shrink-0"
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>
    </aside>
  )
}

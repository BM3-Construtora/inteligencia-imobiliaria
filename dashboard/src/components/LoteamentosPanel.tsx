import { useLoteamentos } from '../hooks/useSupabase'

const TIPO_COLOR: Record<string, string> = {
  loteamento: 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30',
  desmembramento: 'bg-sky-600/20 text-sky-400 border-sky-500/30',
  parcelamento: 'bg-slate-600/20 text-slate-300 border-slate-500/30',
  subdivisao: 'bg-amber-600/20 text-amber-400 border-amber-500/30',
}

function fmtDate(d: string | null): string {
  if (!d) return '-'
  const s = d.slice(0, 10)
  const [y, m, day] = s.split('-')
  return day && m && y ? `${day}/${m}/${y}` : s
}

export function LoteamentosPanel() {
  const { rows, total, loading } = useLoteamentos(60)

  if (loading) {
    return <div className="text-slate-400 py-8 text-center">Carregando loteamentos...</div>
  }

  const named = rows.filter((r) => r.titulo).length

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="mb-4">
        <h3 className="text-white font-semibold">Novos loteamentos aprovados</h3>
        <p className="text-xs text-slate-400">
          Parcelamentos de solo aprovados no Diario Oficial — sinal de futura oferta de terreno.
          {total > 0 && ` ${total} no historico, ${named} nomeados nesta lista.`}
        </p>
      </div>

      {rows.length === 0 ? (
        <p className="text-slate-400 text-sm">Nenhum loteamento aprovado registrado.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-700">
                <th className="py-2 pr-3 font-medium">Data</th>
                <th className="py-2 pr-3 font-medium">Tipo</th>
                <th className="py-2 pr-3 font-medium">Empreendimento</th>
                <th className="py-2 font-medium">Bairro</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const tipo = (r.tipo || 'parcelamento').toLowerCase()
                const badge = TIPO_COLOR[tipo] || TIPO_COLOR.parcelamento
                return (
                  <tr key={`${r.issue_date}-${i}`} className="border-b border-slate-800/60 hover:bg-slate-800/40">
                    <td className="py-2 pr-3 text-slate-300 whitespace-nowrap">{fmtDate(r.issue_date)}</td>
                    <td className="py-2 pr-3">
                      <span className={`text-[10px] px-2 py-0.5 rounded-md border ${badge}`}>{tipo}</span>
                    </td>
                    <td className="py-2 pr-3 text-white">
                      {r.titulo || <span className="text-slate-500 italic">sem nome no decreto</span>}
                    </td>
                    <td className="py-2 text-slate-400">{r.neighborhood || '-'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

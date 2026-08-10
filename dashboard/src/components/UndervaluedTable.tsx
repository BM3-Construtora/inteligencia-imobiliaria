import { useUndervalued } from '../hooks/useSupabase'

function fmt(n: number | null): string {
  if (n == null) return '-'
  return `R$ ${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

export function UndervaluedTable() {
  const { rows, loading } = useUndervalued(50)

  if (loading) {
    return <div className="text-slate-400 py-8 text-center">Carregando avaliacoes...</div>
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="mb-4">
        <h3 className="text-white font-semibold">Imoveis subprecificados</h3>
        <p className="text-xs text-slate-400">
          Pedido abaixo do P25 do modelo de avaliacao (AVM), ordenado pela maior diferenca.
        </p>
      </div>

      {rows.length === 0 ? (
        <p className="text-slate-400 text-sm">
          Nenhum imovel subprecificado no momento (nenhum pedido abaixo do P25).
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-700">
                <th className="py-2 pr-3 font-medium">Bairro</th>
                <th className="py-2 pr-3 font-medium text-right">Area</th>
                <th className="py-2 pr-3 font-medium text-right">Pedido</th>
                <th className="py-2 pr-3 font-medium text-right">Justo (P50)</th>
                <th className="py-2 pr-3 font-medium text-right">Abaixo</th>
                <th className="py-2 pr-3 font-medium">Por que</th>
                <th className="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.listing_id} className="border-b border-slate-800/60 hover:bg-slate-800/40">
                  <td className="py-2 pr-3 text-white">{r.neighborhood || '-'}</td>
                  <td className="py-2 pr-3 text-right text-slate-300">
                    {r.total_area != null ? `${r.total_area.toLocaleString('pt-BR')} m²` : '-'}
                  </td>
                  <td className="py-2 pr-3 text-right text-slate-300">{fmt(r.actual_price)}</td>
                  <td className="py-2 pr-3 text-right text-slate-300">{fmt(r.p50)}</td>
                  <td className="py-2 pr-3 text-right">
                    <span className="text-emerald-400 font-medium">
                      {r.mispricing_pct != null ? `${r.mispricing_pct.toFixed(0)}%` : '-'}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-slate-400 max-w-[320px]">
                    <span className="line-clamp-2">{r.shap_summary || '-'}</span>
                  </td>
                  <td className="py-2">
                    {r.url && (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 text-xs whitespace-nowrap"
                      >
                        anuncio
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-slate-600 mt-3">
            Estimativa por modelo — referencia para negociacao, nao avaliacao formal.
          </p>
        </div>
      )}
    </div>
  )
}

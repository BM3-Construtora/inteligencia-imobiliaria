import { useState, useMemo } from 'react'

const FAIXAS = [
  { key: 'mcmv_faixa1', label: 'MCMV Faixa 1', valorMax: 190000, area: 40, custo_mult: 0.85, pav: 2, aprov: 0.55 },
  { key: 'mcmv_faixa2', label: 'MCMV Faixa 2', valorMax: 264000, area: 45, custo_mult: 1.0, pav: 2, aprov: 0.60 },
  { key: 'mcmv_faixa3', label: 'MCMV Faixa 3', valorMax: 350000, area: 55, custo_mult: 1.15, pav: 2, aprov: 0.55 },
  { key: 'casa_padrao', label: 'Casa Padrao', valorMax: 500000, area: 70, custo_mult: 1.40, pav: 1, aprov: 0.50 },
]

const BDI = 0.30
const INFRA_PCT = 0.12
const PROJ_PCT = 0.05
const MARKETING_PCT = 0.03
const ADMIN_PCT = 0.04
const IMPOSTOS_PCT = 0.04

function fmt(n: number): string {
  return `R$ ${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

function simulate(landPrice: number, landArea: number, faixa: typeof FAIXAS[0], sinapiCost: number) {
  const custoM2 = sinapiCost * faixa.custo_mult
  const areaConstruivel = landArea * faixa.aprov * faixa.pav
  const unidades = Math.floor(areaConstruivel / faixa.area)
  if (unidades < 1) return null

  const areaTotal = unidades * faixa.area
  const custoBase = areaTotal * custoM2
  const custoBDI = custoBase * BDI
  const custoConstrucao = custoBase + custoBDI
  const custoInfra = custoBase * INFRA_PCT
  const custoProj = custoBase * PROJ_PCT
  const custoObra = custoConstrucao + custoInfra + custoProj

  const vgv = unidades * faixa.valorMax
  const custoMkt = vgv * MARKETING_PCT
  const custoAdm = vgv * ADMIN_PCT
  const custoImp = vgv * IMPOSTOS_PCT

  const investTotal = landPrice + custoObra + custoMkt + custoAdm + custoImp
  const lucro = vgv - investTotal
  const margem = vgv > 0 ? (lucro / vgv) * 100 : 0
  const roi = investTotal > 0 ? (lucro / investTotal) * 100 : 0

  const mesesObra = faixa.key.startsWith('mcmv') ? 8 : 12
  const mesesVenda = Math.max(3, Math.ceil(unidades / 2))
  const payback = (mesesObra + mesesVenda) / 12

  return { unidades, areaTotal, custoObra, vgv, investTotal, lucro, margem, roi, payback, custoM2 }
}

export function ViabilityCalculator() {
  const [landPrice, setLandPrice] = useState(200000)
  const [landArea, setLandArea] = useState(500)
  const [sinapi, setSinapi] = useState(1920)

  const results = useMemo(() => {
    return FAIXAS.map(f => ({
      faixa: f,
      result: simulate(landPrice, landArea, f, sinapi),
    }))
  }, [landPrice, landArea, sinapi])

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <h3 className="text-white font-semibold mb-1">Calculadora de Viabilidade</h3>
      <p className="text-xs text-slate-400 mb-4">Simule um projeto: insira preco e area do terreno</p>

      {/* Inputs */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div>
          <label className="text-xs text-slate-400 block mb-1">Preco do Terreno (R$)</label>
          <input
            type="number"
            value={landPrice}
            onChange={e => setLandPrice(Number(e.target.value))}
            className="w-full bg-slate-700 text-white px-3 py-2 rounded-md border border-slate-600 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="text-xs text-slate-400 block mb-1">Area do Terreno (m²)</label>
          <input
            type="number"
            value={landArea}
            onChange={e => setLandArea(Number(e.target.value))}
            className="w-full bg-slate-700 text-white px-3 py-2 rounded-md border border-slate-600 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="text-xs text-slate-400 block mb-1">SINAPI/m² (R$)</label>
          <input
            type="number"
            value={sinapi}
            onChange={e => setSinapi(Number(e.target.value))}
            className="w-full bg-slate-700 text-white px-3 py-2 rounded-md border border-slate-600 focus:border-indigo-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Results grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {results.map(({ faixa, result }) => {
          if (!result) return (
            <div key={faixa.key} className="bg-slate-700/30 rounded-lg p-4 border border-slate-700">
              <p className="text-sm font-semibold text-slate-400">{faixa.label}</p>
              <p className="text-xs text-slate-500 mt-2">Terreno insuficiente para este cenario</p>
            </div>
          )

          const isViable = result.margem >= 15
          const borderColor = isViable ? 'border-green-700/50' : 'border-red-700/50'
          const bgColor = isViable ? 'bg-green-900/20' : 'bg-red-900/20'

          return (
            <div key={faixa.key} className={`rounded-lg p-4 border ${borderColor} ${bgColor}`}>
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-white">{faixa.label}</p>
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                  isViable ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
                }`}>
                  {isViable ? 'GO' : 'NO-GO'}
                </span>
              </div>

              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Unidades</span>
                  <span className="text-white font-mono">{result.unidades}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">VGV</span>
                  <span className="text-white font-mono">{fmt(result.vgv)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Investimento</span>
                  <span className="text-white font-mono">{fmt(result.investTotal)}</span>
                </div>
                <div className="flex justify-between border-t border-slate-600 pt-1.5">
                  <span className="text-slate-400">Lucro</span>
                  <span className={`font-mono font-bold ${result.lucro > 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {fmt(result.lucro)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Margem</span>
                  <span className={`font-mono font-bold ${isViable ? 'text-green-400' : 'text-red-400'}`}>
                    {result.margem.toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">ROI</span>
                  <span className="text-white font-mono">{result.roi.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Payback</span>
                  <span className="text-white font-mono">{result.payback.toFixed(1)} anos</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Custo/m²</span>
                  <span className="text-slate-300 font-mono">{fmt(result.custoM2)}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-[10px] text-slate-500 mt-3">
        BDI: {(BDI*100).toFixed(0)}% | Infra: {(INFRA_PCT*100).toFixed(0)}% | Projetos: {(PROJ_PCT*100).toFixed(0)}% | Marketing: {(MARKETING_PCT*100).toFixed(0)}% | Admin: {(ADMIN_PCT*100).toFixed(0)}% | Impostos: {(IMPOSTOS_PCT*100).toFixed(0)}%
      </p>
    </div>
  )
}

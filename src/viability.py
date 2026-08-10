"""Viability — MCMV construction feasibility simulator with real SINAPI costs.

Calculates VGV, TIR, Payback and margin for land opportunities.
Focus: MCMV Faixa 1/2/3 with real construction cost data.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from postgrest.exceptions import APIError

from src.db import get_client

logger = logging.getLogger(__name__)

# ============================================================
# Calibration assumptions (interior SP, projeto popular/MCMV)
# Source: cross-check vs BM3 historical data when company_projects is populated
# Override via env vars: VIABILITY_COMMISSION_PCT etc.
# ============================================================
import os

# Defaults calibrados com dados reais BM3 (3 projetos: 1 vendido + 2 em construção)
# Casa 1 (Santa Antonieta, vendida 2020): margem bruta 24%, extras 11% do total,
# vendida direto sem corretora, 8 meses obra.
# Casa 2/3 (Santa Clara, paradas): estouro orçamento 11%, 52% pago em cartão.
COMMISSION_PCT = float(os.getenv("VIABILITY_COMMISSION_PCT", "2.0"))
TYPICAL_SALES_MONTHS = int(os.getenv("VIABILITY_SALES_MONTHS", "6"))
WORKING_CAPITAL_ANNUAL_PCT = float(os.getenv("VIABILITY_CAPITAL_PCT", "18.0"))
REWORK_BUFFER_PCT = float(os.getenv("VIABILITY_REWORK_PCT", "11.0"))
TETO_VENDA_DISCOUNT = float(os.getenv("VIABILITY_TETO_DISCOUNT", "0.90"))

# BDI — BM3 trabalha "no osso", custos diretos + retrabalho 11% cobrem o BDI clássico.
BDI_PCT = float(os.getenv("VIABILITY_BDI_PCT", "0.15"))

# EFFICIENCY_FACTOR — BM3 constrói ~15% mais barato que SINAPI puro
# (Casa 1 Santa Antonieta: SINAPI 2020 R$1500/m² × 50m² = R$75k vs real R$64k bruto).
# Multiplica custo_m2 final pra ajustar pra realidade do construtor.
EFFICIENCY_FACTOR = float(os.getenv("VIABILITY_EFFICIENCY", "0.85"))

# ============================================================
# MCMV 2026 — Atualizado conforme Portaria MCID mar/2026
# Fonte: gov.br/cidades, Portaria 725/2023 (especificações),
#        Portaria 335/2026 (atualizações)
# ============================================================
#
# Modelo BM3: terreno 10×25m (250m²) → desdobra em 2 lotes de
# 5×25m (125m² cada) → 1 casa por lote.
# Lote mínimo MCMV: 125m² (Portaria 725/2023)
# Área construída mínima: 40m² (casa térrea)
#
# Benefícios fiscais para construtora:
# - RET MCMV Faixa 1: 1% sobre receita (IRPJ+CSLL+PIS+COFINS unificados)
# - RET demais faixas: 4% sobre receita (vs 9.25% regime normal)
# - Prazo para aderir ao RET: até 31/12/2028
# - Patrimônio de afetação: cada obra = CNPJ próprio
#
# Financiamento Caixa "Apoio à Produção":
# - Até 100% do custo de obra financiado
# - Até 36 meses para construir + 9 meses de carência
# - Taxa: ~9.5% a.a. (MCMV)
# - Liberação mensal por medição
# - Capital próprio necessário: terreno + capital de giro inicial
#
MCMV_FAIXAS = {
    "mcmv_faixa1": {
        "nome": "MCMV Faixa 1",
        "renda_max": 3200,              # Atualizado mar/2026
        "valor_max_imovel": 190000,     # Faixa 1 urbana (varia por localidade)
        "subsidio_max": 55000,
        "taxa_juros_aa": 0.04,
        "ret_pct": 0.01,               # RET 1% (benefício fiscal)
        "unidade_area_m2": 40,          # Mínimo Portaria 725
        "lote_minimo_m2": 125,          # Lote mínimo MCMV
        "custo_multiplier": 0.85,       # Padrão mais simples
    },
    "mcmv_faixa2": {
        "nome": "MCMV Faixa 2",
        "renda_max": 5000,              # Atualizado mar/2026
        "valor_max_imovel": 264000,     # Teto Faixa 2 urbana
        "subsidio_max": 55000,
        "taxa_juros_aa": 0.065,
        "ret_pct": 0.04,               # RET 4%
        "unidade_area_m2": 50,          # Casa 2 quartos
        "lote_minimo_m2": 125,          # Desdobro: 250m² → 2×125m²
        "custo_multiplier": 1.0,
    },
    "mcmv_faixa3": {
        "nome": "MCMV Faixa 3",
        "renda_max": 9600,              # Atualizado mar/2026
        "valor_max_imovel": 400000,     # Atualizado: era 350k
        "subsidio_max": 0,
        "taxa_juros_aa": 0.0816,
        "ret_pct": 0.04,               # RET 4%
        "unidade_area_m2": 60,          # Casa 3 quartos
        "lote_minimo_m2": 125,
        "custo_multiplier": 1.15,
    },
    "casa_padrao": {
        "nome": "Casa Padrão Médio",
        "renda_max": 15000,
        "valor_max_imovel": 600000,     # Atualizado: era 500k (Faixa 4)
        "subsidio_max": 0,
        "taxa_juros_aa": 0.11,
        "ret_pct": 0.04,
        "unidade_area_m2": 80,
        "lote_minimo_m2": 150,
        "custo_multiplier": 1.40,
    },
}

# Custos operacionais (% do VGV)
CUSTO_PROJETOS_PCT = 0.05       # Projetos (arquitetura, estrutural, etc.)
CUSTO_MARKETING_PCT = 0.02      # MCMV vende fácil (subsídio), 2% suficiente
CUSTO_ADMIN_PCT = 0.03          # Construtora familiar = overhead baixo
CUSTO_INFRA_PCT = 0.10          # Infraestrutura (água, esgoto, luz, calçada)
# Impostos: usando RET (1% Faixa 1 ou 4% demais) — calculado dinamicamente

# GO/NO-GO criteria
MIN_MARGEM_PCT = 15.0
MAX_PAYBACK_ANOS = 4
# Teto de investimento por projeto: caixa disponível da BM3.
# Um projeto que estoura isso não é viável, por melhor que seja a margem.
MAX_INVESTMENT = float(os.getenv("VIABILITY_MAX_INVESTMENT", "500000"))


def _get_sinapi_cost() -> float:
    """Get latest SINAPI cost/m² for SP from market_indices."""
    try:
        from src.collectors.sinapi import get_latest_sinapi_cost
        return get_latest_sinapi_cost()
    except Exception:
        return 1920.0


def get_market_context(neighborhood: str, db: Any = None) -> dict[str, Any]:
    """Retorna contexto de mercado para um bairro usando os dados coletados.

    Retorna:
      itbi_heat          — variação ITBI últimos 3m vs mesmo período ano anterior (-1 a +1)
      obras_investment   — obras públicas concluídas no bairro (últimos 3 anos)
      licitacoes_pipeline— licitações de obras abertas na cidade (último ano)
      prazo_venda_ajuste — meses a somar ao prazo_venda_meses base
      preco_premium_pct  — % adicional no preço de venda por investimento público
    """
    if db is None:
        db = get_client()

    ctx: dict[str, Any] = {
        "itbi_heat": 0.0,
        "obras_investment": 0,
        "licitacoes_pipeline": 0,
        "prazo_venda_ajuste": 0,
        "preco_premium_pct": 0.0,
    }

    # ITBI heat: variação últimos 3 meses vs mesmo trimestre do ano anterior
    try:
        from datetime import datetime as _dt
        now = _dt.now()
        cur_year, cur_month = now.year, now.month

        def _itbi_count(year: int, month_end: int, months: int = 3) -> int:
            total = 0
            for delta in range(months):
                m = month_end - delta
                y = year
                if m < 1:
                    m += 12
                    y -= 1
                r = (
                    db.table("receitas_marilia")
                    .select("id", count="exact")
                    .ilike("descricao_receita", "%ITBI%")
                    .eq("exercicio", y)
                    .eq("mes", m)
                    .execute()
                )
                total += r.count or 0
            return total

        itbi_cur = _itbi_count(cur_year, cur_month)
        itbi_prev = _itbi_count(cur_year - 1, cur_month)

        if itbi_prev > 0:
            ctx["itbi_heat"] = round(min(1.0, max(-1.0, (itbi_cur / itbi_prev) - 1.0)), 2)
        elif itbi_cur > 0:
            ctx["itbi_heat"] = 0.3

        if ctx["itbi_heat"] >= 0.2:
            ctx["prazo_venda_ajuste"] = -2
        elif ctx["itbi_heat"] <= -0.2:
            ctx["prazo_venda_ajuste"] = 2
    except Exception:
        logger.warning("[viability] ITBI heat failed", exc_info=True)

    # Obras concluídas no bairro (últimos 3 anos) → premium de preço
    try:
        from datetime import datetime as _dt
        cutoff_year = _dt.now().year - 3
        r = (
            db.table("obras_publicas_marilia")
            .select("id", count="exact")
            .eq("situacao", "Concluído")
            .gte("year", cutoff_year)
            .ilike("neighborhood", f"%{neighborhood}%")
            .execute()
        )
        ctx["obras_investment"] = r.count or 0
        # +0.5% por obra concluída, cap 7%
        ctx["preco_premium_pct"] = round(min(7.0, (r.count or 0) * 0.5), 1)
    except Exception:
        logger.warning("[viability] obras investment failed", exc_info=True)

    # Licitações abertas na cidade (pipeline de obras públicas)
    try:
        from datetime import datetime as _dt
        r = (
            db.table("licitacoes_obras_marilia")
            .select("id", count="exact")
            .eq("situacao", "Aberto")
            .gte("year", _dt.now().year - 1)
            .execute()
        )
        ctx["licitacoes_pipeline"] = r.count or 0
    except Exception:
        logger.warning("[viability] licitacoes pipeline failed", exc_info=True)

    return ctx


def calc_cost_breakdown(
    land_cost: float,
    area_total: float,
    sinapi_per_m2: float,
    units: int,
    custo_multiplier: float = 1.0,
    ret_pct: float = 0.04,
    prazo_venda_meses: int = TYPICAL_SALES_MONTHS,
    preco_venda_unidade: float = 0.0,
) -> dict[str, float]:
    """Pure cost-breakdown calculation. No I/O, no DB, no LLM.

    Args:
        land_cost: Total price paid for land (R$).
        area_total: Total built area across all units (m²).
        sinapi_per_m2: SINAPI construction cost per m² (R$).
        units: Number of units in the project.
        custo_multiplier: Faixa-specific cost multiplier (e.g. 0.85, 1.0, 1.15).
        ret_pct: RET (tax) percentage applied on VGV (0.01 or 0.04).
        prazo_venda_meses: Sales horizon in months for working-capital cost.
        preco_venda_unidade: Unit sale price (R$). If 0, VGV-dependent fields stay 0.

    Returns:
        Dict with all cost line items, VGV, lucro, margem, ROI.
    """
    custo_m2 = sinapi_per_m2 * custo_multiplier * EFFICIENCY_FACTOR
    custo_construcao_base = area_total * custo_m2
    custo_bdi = custo_construcao_base * BDI_PCT
    custo_construcao = custo_construcao_base + custo_bdi
    custo_infra = custo_construcao_base * CUSTO_INFRA_PCT
    custo_projetos = custo_construcao_base * CUSTO_PROJETOS_PCT
    custo_retrabalho = custo_construcao_base * (REWORK_BUFFER_PCT / 100.0)
    custo_total_obra = custo_construcao + custo_infra + custo_projetos + custo_retrabalho

    vgv = units * preco_venda_unidade
    custo_marketing = vgv * CUSTO_MARKETING_PCT
    custo_admin = vgv * CUSTO_ADMIN_PCT
    custo_comissao = vgv * (COMMISSION_PCT / 100.0)
    custo_impostos = vgv * ret_pct
    custo_financeiro_pct = (WORKING_CAPITAL_ANNUAL_PCT / 100.0) * (prazo_venda_meses / 12.0)
    custo_financeiro = (land_cost + custo_total_obra) * custo_financeiro_pct
    custos_operacionais = (
        custo_marketing + custo_admin + custo_comissao
        + custo_impostos + custo_financeiro
    )

    investimento_total = land_cost + custo_total_obra + custos_operacionais
    lucro_bruto = vgv - land_cost - custo_total_obra
    lucro_liquido = vgv - investimento_total
    margem_bruta = (lucro_bruto / vgv * 100) if vgv > 0 else 0.0
    margem_liquida = (lucro_liquido / vgv * 100) if vgv > 0 else 0.0
    roi = (lucro_liquido / investimento_total * 100) if investimento_total > 0 else 0.0

    return {
        "custo_m2": custo_m2,
        "custo_terreno": land_cost,
        "custo_construcao_base": custo_construcao_base,
        "custo_bdi": custo_bdi,
        "custo_construcao": custo_construcao,
        "custo_infra": custo_infra,
        "custo_projetos": custo_projetos,
        "custo_retrabalho": custo_retrabalho,
        "custo_total_obra": custo_total_obra,
        "custo_marketing": custo_marketing,
        "custo_admin": custo_admin,
        "custo_comissao": custo_comissao,
        "custo_impostos": custo_impostos,
        "custo_financeiro": custo_financeiro,
        "custos_operacionais": custos_operacionais,
        "investimento_total": investimento_total,
        "vgv": vgv,
        "lucro_bruto": lucro_bruto,
        "lucro_liquido": lucro_liquido,
        "margem_bruta_pct": margem_bruta,
        "margem_liquida_pct": margem_liquida,
        "roi_pct": roi,
    }


def simulate_project(
    land_price: float,
    land_area: float,
    faixa_key: str = "mcmv_faixa2",
    sinapi_cost: float | None = None,
    neighborhood_avg_price_m2: float | None = None,
    prazo_venda_meses: int = TYPICAL_SALES_MONTHS,
    market_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Simulate a construction project and return full financial analysis.

    Returns: dict with inputs, costs, revenue, margins, TIR, payback, go/no-go.
    """
    if land_price <= 0 or land_area <= 0:
        return None

    faixa = MCMV_FAIXAS.get(faixa_key)
    if not faixa:
        return None

    sinapi = sinapi_cost or _get_sinapi_cost()
    custo_m2 = sinapi * faixa["custo_multiplier"] * EFFICIENCY_FACTOR

    # --- Units calculation ---
    # Modelo BM3: casas individuais em lotes separados.
    # Terreno grande → subdivide em N lotes → 1 casa por lote.
    # Terreno pequeno (1 lote) → 1 casa.
    lote_minimo = faixa["lote_minimo_m2"]
    unidade_area = faixa["unidade_area_m2"]
    unidades = max(1, int(land_area / lote_minimo))

    if land_area < lote_minimo * 0.8:
        return None  # Terreno muito pequeno para essa faixa

    area_total = unidades * unidade_area  # Total construído (não é a área do terreno)

    # --- Costs ---
    custo_terreno = land_price
    custo_construcao_base = area_total * custo_m2
    custo_bdi = custo_construcao_base * BDI_PCT
    custo_construcao = custo_construcao_base + custo_bdi
    custo_infra = custo_construcao_base * CUSTO_INFRA_PCT
    custo_projetos = custo_construcao_base * CUSTO_PROJETOS_PCT
    # Retrabalho médio em obra residencial (5% sobre construção bruta)
    custo_retrabalho = custo_construcao_base * (REWORK_BUFFER_PCT / 100.0)

    custo_total_obra = custo_construcao + custo_infra + custo_projetos + custo_retrabalho

    # --- Revenue ---
    # MCMV: preço de venda = teto da faixa (valor fixo financiável pela Caixa).
    # Aplicamos desconto TETO_VENDA_DISCOUNT — mercado raramente paga teto cheio.
    # Para casa_padrao (não-MCMV), usa mercado como referência.
    preco_teto = faixa["valor_max_imovel"]
    preco_venda_unidade = preco_teto * TETO_VENDA_DISCOUNT
    if faixa_key == "casa_padrao" and neighborhood_avg_price_m2 and neighborhood_avg_price_m2 > 0:
        preco_mercado = neighborhood_avg_price_m2 * unidade_area
        preco_venda_unidade = min(preco_venda_unidade, preco_mercado * 1.05)

    # Aplica ajustes do contexto de mercado
    ctx = market_context or {}
    if ctx:
        prazo_venda_meses = max(1, prazo_venda_meses + ctx.get("prazo_venda_ajuste", 0))
        premium = ctx.get("preco_premium_pct", 0.0)
        if premium > 0:
            preco_venda_unidade = preco_venda_unidade * (1 + premium / 100.0)
            # MCMV tem teto legal — não pode ultrapassar valor_max_imovel
            if faixa_key.startswith("mcmv"):
                preco_venda_unidade = min(preco_venda_unidade, preco_teto)

    vgv = unidades * preco_venda_unidade

    # --- Operational costs (% of VGV) ---
    custo_marketing = vgv * CUSTO_MARKETING_PCT
    custo_admin = vgv * CUSTO_ADMIN_PCT
    # Comissão de venda (corretagem) — 4% sobre VGV
    custo_comissao = vgv * (COMMISSION_PCT / 100.0)
    # Impostos via RET: 1% (Faixa 1) ou 4% (demais) — vs 9.25% regime normal
    ret_pct = faixa.get("ret_pct", 0.04)
    custo_impostos = vgv * ret_pct
    # Custo financeiro: capital de giro durante venda (12% a.a. pro-rata pelo prazo)
    custo_financeiro_pct = (WORKING_CAPITAL_ANNUAL_PCT / 100.0) * (prazo_venda_meses / 12.0)
    custo_financeiro = (custo_terreno + custo_total_obra) * custo_financeiro_pct
    custos_operacionais = (
        custo_marketing + custo_admin + custo_comissao
        + custo_impostos + custo_financeiro
    )

    # --- Totals ---
    investimento_total = custo_terreno + custo_total_obra + custos_operacionais
    lucro_bruto = vgv - custo_terreno - custo_total_obra
    lucro_liquido = vgv - investimento_total
    margem_bruta = (lucro_bruto / vgv * 100) if vgv > 0 else 0
    margem_liquida = (lucro_liquido / vgv * 100) if vgv > 0 else 0
    roi = (lucro_liquido / investimento_total * 100) if investimento_total > 0 else 0

    # --- Timeline & Payback ---
    meses_construcao = 8 if faixa_key.startswith("mcmv") else 12
    meses_venda = max(3, int(unidades / 2))  # Estimate: sell 2 units/month
    payback_meses = meses_construcao + meses_venda
    payback_anos = payback_meses / 12

    # --- TIR (simplified) ---
    # Monthly cash flow: -investment spread over construction, +revenue spread over sales
    investimento_mensal = investimento_total / meses_construcao
    receita_mensal = vgv / meses_venda

    fluxo = [0.0]  # t=0
    for m in range(1, payback_meses + 1):
        if m <= meses_construcao:
            fluxo.append(-investimento_mensal)
        else:
            fluxo.append(receita_mensal)

    tir_mensal = _calc_irr(fluxo)
    tir_anual = ((1 + tir_mensal) ** 12 - 1) * 100 if tir_mensal else 0

    # --- GO/NO-GO ---
    # O teto de investimento entra no is_viable: um projeto acima do caixa da BM3
    # não é executável, mesmo com margem e payback bons.
    within_budget = investimento_total <= MAX_INVESTMENT
    is_viable = (
        margem_liquida >= MIN_MARGEM_PCT
        and payback_anos <= MAX_PAYBACK_ANOS
        and within_budget
    )
    go_reasons = []
    nogo_reasons = []

    if margem_liquida >= MIN_MARGEM_PCT:
        go_reasons.append(f"Margem {margem_liquida:.1f}% >= {MIN_MARGEM_PCT}%")
    else:
        nogo_reasons.append(f"Margem {margem_liquida:.1f}% < {MIN_MARGEM_PCT}%")

    if payback_anos <= MAX_PAYBACK_ANOS:
        go_reasons.append(f"Payback {payback_anos:.1f} anos <= {MAX_PAYBACK_ANOS}")
    else:
        nogo_reasons.append(f"Payback {payback_anos:.1f} anos > {MAX_PAYBACK_ANOS}")

    if within_budget:
        go_reasons.append(f"Investimento R${investimento_total:,.0f} dentro do budget")
    else:
        nogo_reasons.append(
            f"Investimento R${investimento_total:,.0f} > R${MAX_INVESTMENT:,.0f} budget"
        )

    return {
        "scenario": faixa["nome"],
        "faixa_key": faixa_key,
        "is_viable": is_viable,
        "go_reasons": go_reasons,
        "nogo_reasons": nogo_reasons,
        "market_context": ctx if ctx else None,
        "inputs": {
            "custo_terreno": round(custo_terreno),
            "area_terreno_m2": round(land_area, 1),
            "preco_terreno_m2": round(land_price / land_area, 2),
            "sinapi_custo_m2": round(sinapi, 2),
            "custo_m2_ajustado": round(custo_m2, 2),
            "bdi_pct": BDI_PCT,
            "unidade_area_m2": unidade_area,
            "preco_venda_unidade": round(preco_venda_unidade),
            "preco_teto_faixa": round(preco_teto),
            "teto_discount": TETO_VENDA_DISCOUNT,
            "prazo_venda_meses": prazo_venda_meses,
            "comissao_venda_pct": COMMISSION_PCT,
            "custo_financeiro_pct": round(custo_financeiro_pct * 100, 2),
            "retrabalho_buffer_pct": REWORK_BUFFER_PCT,
        },
        "outputs": {
            "unidades": unidades,
            "area_total_m2": round(area_total, 1),
            "custo_terreno": round(custo_terreno),
            "custo_construcao": round(custo_construcao),
            "custo_infra": round(custo_infra),
            "custo_projetos": round(custo_projetos),
            "custo_retrabalho": round(custo_retrabalho),
            "custo_total_obra": round(custo_total_obra),
            "custo_marketing": round(custo_marketing),
            "custo_admin": round(custo_admin),
            "custo_comissao": round(custo_comissao),
            "custo_financeiro": round(custo_financeiro),
            "custo_impostos": round(custo_impostos),
            "investimento_total": round(investimento_total),
            "vgv": round(vgv),
            "lucro_bruto": round(lucro_bruto),
            "lucro_liquido": round(lucro_liquido),
            "margem_bruta_pct": round(margem_bruta, 1),
            "margem_liquida_pct": round(margem_liquida, 1),
            "roi_pct": round(roi, 1),
            "tir_anual_pct": round(tir_anual, 1),
            "payback_meses": payback_meses,
            "payback_anos": round(payback_anos, 1),
            "custo_por_unidade": round(investimento_total / unidades) if unidades > 0 else 0,
        },
    }


def _calc_irr(cashflows: list[float], guess: float = 0.05, max_iter: int = 100) -> float:
    """Calculate Internal Rate of Return using Newton's method."""
    rate = guess
    for _ in range(max_iter):
        try:
            npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))
            dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows))
        except (OverflowError, ZeroDivisionError):
            return 0.0
        if abs(dnpv) < 1e-10:
            break
        new_rate = rate - npv / dnpv
        if new_rate <= -1.0 or new_rate > 10.0:
            return 0.0
        if abs(new_rate - rate) < 1e-8:
            return new_rate
        rate = new_rate
    return rate


def run_viability(
    listing_ids: list[int] | None = None,
    params: dict[str, float] | None = None,
) -> dict[str, int]:
    """Run viability studies on land listings across all MCMV faixas."""
    db = get_client()
    stats = {"analyzed": 0, "viable": 0, "not_viable": 0, "scenarios": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "viability", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        sinapi_cost = _get_sinapi_cost()
        logger.info(f"[viability] Using SINAPI cost: R${sinapi_cost:.2f}/m²")

        # Get target listings
        if listing_ids:
            result = (
                db.table("listings")
                .select("id, sale_price, total_area, neighborhood, is_mcmv")
                .in_("id", listing_ids)
                .execute()
            )
        else:
            opps = (
                db.table("opportunities")
                .select("listing_id")
                .gte("score", 60)
                .order("score", desc=True)
                .limit(50)
                .execute()
            )
            ids = [o["listing_id"] for o in opps.data]
            if not ids:
                logger.info("[viability] No opportunities with score >= 60")
                _finish_run(db, run_id, "completed", stats)
                return stats

            result = (
                db.table("listings")
                .select("id, sale_price, total_area, neighborhood, is_mcmv")
                .in_("id", ids)
                .execute()
            )

        listings = result.data
        logger.info(f"[viability] Analyzing {len(listings)} listings × {len(MCMV_FAIXAS)} faixas")

        # Get neighborhood avg prices for revenue estimation
        neigh_prices: dict[str, float] = {}
        neighs = list(set(l.get("neighborhood", "") for l in listings if l.get("neighborhood")))
        for n in neighs:
            try:
                r = db.table("neighborhoods").select("avg_price_m2_house").eq("name", n).limit(1).execute()
                if r.data and r.data[0].get("avg_price_m2_house"):
                    neigh_prices[n] = float(r.data[0]["avg_price_m2_house"])
            except Exception:
                pass

        # Market context (ITBI heat + obras investment) — cached per neighborhood
        market_ctx_cache: dict[str, dict] = {}
        for n in neighs:
            try:
                market_ctx_cache[n] = get_market_context(n, db)
            except Exception:
                market_ctx_cache[n] = {}

        # Clear previous studies
        ids_to_clear = [l["id"] for l in listings]
        if ids_to_clear:
            db.table("viability_studies").delete().in_("listing_id", ids_to_clear).execute()

        typed_cols_available = True
        legacy_warning_emitted = False

        for listing in listings:
            stats["analyzed"] += 1
            best_result = None
            best_margin = -999

            try:
                neigh = listing.get("neighborhood", "")
                mctx = market_ctx_cache.get(neigh, {})
                for faixa_key in MCMV_FAIXAS:
                    study = simulate_project(
                        land_price=float(listing.get("sale_price") or 0),
                        land_area=float(listing.get("total_area") or 0),
                        faixa_key=faixa_key,
                        sinapi_cost=sinapi_cost,
                        neighborhood_avg_price_m2=neigh_prices.get(neigh),
                        market_context=mctx,
                    )
                    if not study:
                        continue

                    # Sensitivity analysis
                    study_opt = simulate_project(
                        float(listing.get("sale_price") or 0),
                        float(listing.get("total_area") or 0),
                        faixa_key, sinapi_cost * 0.90,
                        neigh_prices.get(neigh),
                        market_context=mctx,
                    )
                    study_pes = simulate_project(
                        float(listing.get("sale_price") or 0),
                        float(listing.get("total_area") or 0),
                        faixa_key, sinapi_cost * 1.10,
                        neigh_prices.get(neigh),
                        market_context=mctx,
                    )

                    if study_opt:
                        study["outputs"]["margem_otimista_pct"] = study_opt["outputs"]["margem_liquida_pct"]
                    if study_pes:
                        study["outputs"]["margem_pessimista_pct"] = study_pes["outputs"]["margem_liquida_pct"]

                    stats["scenarios"] += 1
                    if study["is_viable"]:
                        stats["viable"] += 1
                    else:
                        stats["not_viable"] += 1

                    margin = study["outputs"]["margem_liquida_pct"]
                    if margin > best_margin:
                        best_margin = margin
                        best_result = study

                    outputs = study["outputs"]
                    inputs = study["inputs"]
                    base_payload: dict[str, Any] = {
                        "listing_id": listing["id"],
                        "scenario": study["scenario"],
                        "inputs": inputs,
                        "outputs": outputs,
                        "is_viable": study["is_viable"],
                    }
                    typed_payload = {
                        **base_payload,
                        "land_cost": inputs.get("custo_terreno"),
                        "construction_cost": outputs.get("custo_total_obra"),
                        "total_cost": outputs.get("investimento_total"),
                        "vgv": outputs.get("vgv"),
                        "gross_margin_pct": outputs.get("margem_bruta_pct"),
                        "net_margin_pct": outputs.get("margem_liquida_pct"),
                        "roi_pct": outputs.get("roi_pct"),
                        "irr_annual_pct": outputs.get("tir_anual_pct"),
                        "payback_months": outputs.get("payback_meses"),
                        "units": outputs.get("unidades"),
                    }

                    if typed_cols_available:
                        try:
                            db.table("viability_studies").insert(typed_payload).execute()
                        except APIError as e:
                            msg = str(e)
                            if "PGRST204" in msg or "column" in msg.lower():
                                typed_cols_available = False
                                if not legacy_warning_emitted:
                                    logger.warning(
                                        "[viability] Colunas tipadas ausentes em viability_studies. "
                                        "Aplique supabase/migrations/*_viability_columns.sql. Usando JSON legado."
                                    )
                                    legacy_warning_emitted = True
                                db.table("viability_studies").insert(base_payload).execute()
                            else:
                                raise
                    else:
                        db.table("viability_studies").insert(base_payload).execute()

                if best_result:
                    logger.info(
                        f"[viability] #{listing['id']} {listing.get('neighborhood', '?')}: "
                        f"melhor={best_result['scenario']} | "
                        f"margem={best_margin:.1f}% | "
                        f"{'GO' if best_result['is_viable'] else 'NO-GO'}"
                    )
            except Exception:
                logger.warning(f"[viability] Error on listing #{listing.get('id')}", exc_info=True)

        logger.info(
            f"[viability] Done: {stats['analyzed']} analyzed, "
            f"{stats['viable']} viable, {stats['not_viable']} not viable"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[viability] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _finish_run(db, run_id, status, stats, error=None):
    if not run_id:
        return
    update = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["analyzed"],
        "items_created": stats["viable"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

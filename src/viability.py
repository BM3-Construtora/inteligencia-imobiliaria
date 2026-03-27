"""Viability — MCMV construction feasibility simulator with real SINAPI costs.

Calculates VGV, TIR, Payback and margin for land opportunities.
Focus: MCMV Faixa 1/2/3 with real construction cost data.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

# BDI (Benefícios e Despesas Indiretas) — industry standard for small/medium builders
BDI_PCT = 0.30

# MCMV program parameters (2025-2026)
MCMV_FAIXAS = {
    "mcmv_faixa1": {
        "nome": "MCMV Faixa 1",
        "renda_max": 2850,
        "valor_max_imovel": 190000,
        "subsidio_max": 55000,
        "taxa_juros_aa": 0.04,
        "unidade_area_m2": 40,
        "pavimentos": 2,
        "taxa_aproveitamento": 0.55,
        "custo_multiplier": 0.85,  # Faixa 1 = padrão mais simples
    },
    "mcmv_faixa2": {
        "nome": "MCMV Faixa 2",
        "renda_max": 4700,
        "valor_max_imovel": 264000,
        "subsidio_max": 55000,
        "taxa_juros_aa": 0.05,
        "unidade_area_m2": 45,
        "pavimentos": 2,
        "taxa_aproveitamento": 0.60,
        "custo_multiplier": 1.0,
    },
    "mcmv_faixa3": {
        "nome": "MCMV Faixa 3",
        "renda_max": 8600,
        "valor_max_imovel": 350000,
        "subsidio_max": 0,
        "taxa_juros_aa": 0.075,
        "unidade_area_m2": 55,
        "pavimentos": 2,
        "taxa_aproveitamento": 0.55,
        "custo_multiplier": 1.15,
    },
    "casa_padrao": {
        "nome": "Casa Padrão Médio",
        "renda_max": 15000,
        "valor_max_imovel": 500000,
        "subsidio_max": 0,
        "taxa_juros_aa": 0.11,
        "unidade_area_m2": 70,
        "pavimentos": 1,
        "taxa_aproveitamento": 0.50,
        "custo_multiplier": 1.40,
    },
}

# Cost percentages over VGV
CUSTO_PROJETOS_PCT = 0.05
CUSTO_MARKETING_PCT = 0.03
CUSTO_ADMIN_PCT = 0.04
CUSTO_IMPOSTOS_PCT = 0.04
CUSTO_INFRA_PCT = 0.12

# GO/NO-GO criteria
MIN_MARGEM_PCT = 15.0
MAX_PAYBACK_ANOS = 4


def _get_sinapi_cost() -> float:
    """Get latest SINAPI cost/m² for SP from market_indices."""
    try:
        from src.collectors.sinapi import get_latest_sinapi_cost
        return get_latest_sinapi_cost()
    except Exception:
        return 1920.0


def simulate_project(
    land_price: float,
    land_area: float,
    faixa_key: str = "mcmv_faixa2",
    sinapi_cost: float | None = None,
    neighborhood_avg_price_m2: float | None = None,
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
    custo_m2 = sinapi * faixa["custo_multiplier"]

    # --- Units calculation ---
    area_construivel = land_area * faixa["taxa_aproveitamento"] * faixa["pavimentos"]
    unidade_area = faixa["unidade_area_m2"]
    unidades = int(area_construivel / unidade_area)

    if unidades < 1:
        return None

    area_total = unidades * unidade_area

    # --- Costs ---
    custo_terreno = land_price
    custo_construcao_base = area_total * custo_m2
    custo_bdi = custo_construcao_base * BDI_PCT
    custo_construcao = custo_construcao_base + custo_bdi
    custo_infra = custo_construcao_base * CUSTO_INFRA_PCT
    custo_projetos = custo_construcao_base * CUSTO_PROJETOS_PCT

    custo_total_obra = custo_construcao + custo_infra + custo_projetos

    # --- Revenue ---
    preco_venda_unidade = faixa["valor_max_imovel"]
    if neighborhood_avg_price_m2 and neighborhood_avg_price_m2 > 0:
        preco_mercado = neighborhood_avg_price_m2 * unidade_area
        preco_venda_unidade = min(preco_venda_unidade, preco_mercado * 1.05)

    vgv = unidades * preco_venda_unidade

    # --- Operational costs (% of VGV) ---
    custo_marketing = vgv * CUSTO_MARKETING_PCT
    custo_admin = vgv * CUSTO_ADMIN_PCT
    custo_impostos = vgv * CUSTO_IMPOSTOS_PCT
    custos_operacionais = custo_marketing + custo_admin + custo_impostos

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

    fluxo = []
    for m in range(1, payback_meses + 1):
        if m <= meses_construcao:
            fluxo.append(-investimento_mensal)
        else:
            fluxo.append(receita_mensal)

    tir_mensal = _calc_irr(fluxo)
    tir_anual = ((1 + tir_mensal) ** 12 - 1) * 100 if tir_mensal else 0

    # --- GO/NO-GO ---
    is_viable = margem_liquida >= MIN_MARGEM_PCT and payback_anos <= MAX_PAYBACK_ANOS
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

    if investimento_total <= 500000:
        go_reasons.append(f"Investimento R${investimento_total:,.0f} dentro do budget")
    else:
        nogo_reasons.append(f"Investimento R${investimento_total:,.0f} > R$500k budget")

    return {
        "scenario": faixa["nome"],
        "faixa_key": faixa_key,
        "is_viable": is_viable,
        "go_reasons": go_reasons,
        "nogo_reasons": nogo_reasons,
        "inputs": {
            "custo_terreno": round(custo_terreno),
            "area_terreno_m2": round(land_area, 1),
            "preco_terreno_m2": round(land_price / land_area, 2),
            "sinapi_custo_m2": round(sinapi, 2),
            "custo_m2_ajustado": round(custo_m2, 2),
            "bdi_pct": BDI_PCT,
            "unidade_area_m2": unidade_area,
            "preco_venda_unidade": round(preco_venda_unidade),
        },
        "outputs": {
            "unidades": unidades,
            "area_total_m2": round(area_total, 1),
            "custo_terreno": round(custo_terreno),
            "custo_construcao": round(custo_construcao),
            "custo_infra": round(custo_infra),
            "custo_projetos": round(custo_projetos),
            "custo_total_obra": round(custo_total_obra),
            "custo_marketing": round(custo_marketing),
            "custo_admin": round(custo_admin),
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
        npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))
        dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows))
        if abs(dnpv) < 1e-10:
            break
        new_rate = rate - npv / dnpv
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

        # Clear previous studies
        ids_to_clear = [l["id"] for l in listings]
        if ids_to_clear:
            db.table("viability_studies").delete().in_("listing_id", ids_to_clear).execute()

        for listing in listings:
            stats["analyzed"] += 1
            best_result = None
            best_margin = -999

            for faixa_key in MCMV_FAIXAS:
                study = simulate_project(
                    land_price=float(listing.get("sale_price") or 0),
                    land_area=float(listing.get("total_area") or 0),
                    faixa_key=faixa_key,
                    sinapi_cost=sinapi_cost,
                    neighborhood_avg_price_m2=neigh_prices.get(listing.get("neighborhood", "")),
                )
                if not study:
                    continue

                # Sensitivity analysis
                study_opt = simulate_project(
                    float(listing.get("sale_price") or 0),
                    float(listing.get("total_area") or 0),
                    faixa_key, sinapi_cost * 0.90,
                    neigh_prices.get(listing.get("neighborhood", "")),
                )
                study_pes = simulate_project(
                    float(listing.get("sale_price") or 0),
                    float(listing.get("total_area") or 0),
                    faixa_key, sinapi_cost * 1.10,
                    neigh_prices.get(listing.get("neighborhood", "")),
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

                db.table("viability_studies").insert({
                    "listing_id": listing["id"],
                    "scenario": study["scenario"],
                    "inputs": study["inputs"],
                    "outputs": study["outputs"],
                    "is_viable": study["is_viable"],
                }).execute()

            if best_result:
                logger.info(
                    f"[viability] #{listing['id']} {listing.get('neighborhood', '?')}: "
                    f"melhor={best_result['scenario']} | "
                    f"margem={best_margin:.1f}% | "
                    f"{'GO' if best_result['is_viable'] else 'NO-GO'}"
                )

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

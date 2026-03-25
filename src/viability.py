"""Viability — MCMV construction feasibility simulator for land opportunities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

# Default construction parameters (Marília region, 2024-2025)
DEFAULTS = {
    # Construction costs
    "custo_construcao_m2": 2200.0,      # R$/m² CUB-SP médio para MCMV
    "taxa_aproveitamento": 0.60,         # 60% do terreno construído
    "pavimentos": 2,                     # Sobrados / 2 andares
    "unidade_area": 45.0,               # m² por unidade MCMV típica

    # Revenue
    "preco_venda_unidade": 190000.0,    # Preço venda unidade MCMV Faixa 2
    "preco_venda_m2": 4200.0,           # R$/m² venda

    # Costs
    "custo_infraestrutura_pct": 0.12,   # 12% infra (rua, esgoto, elétrica)
    "custo_projeto_pct": 0.05,          # 5% projetos + aprovações
    "custo_comercializacao_pct": 0.06,  # 6% corretagem + marketing
    "custo_administrativo_pct": 0.04,   # 4% admin + jurídico
    "impostos_pct": 0.04,              # 4% impostos (RET MCMV)

    # MCMV parameters
    "mcmv_faixa2_renda_max": 4400.0,
    "mcmv_faixa2_valor_max": 264000.0,
    "mcmv_faixa2_subsidio_medio": 30000.0,
    "mcmv_faixa2_taxa_juros": 0.07,    # 7% a.a.
}


def run_viability(
    listing_ids: Optional[list[int]] = None,
    params: Optional[dict[str, float]] = None,
) -> dict[str, int]:
    """Run viability studies on land listings.

    If listing_ids is None, runs on all land opportunities with score >= 60.
    """
    db = get_client()
    cfg = {**DEFAULTS, **(params or {})}
    stats = {"analyzed": 0, "viable": 0, "not_viable": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "viability", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Get target listings
        if listing_ids:
            result = (
                db.table("listings")
                .select("id, sale_price, total_area, neighborhood, title, is_mcmv")
                .in_("id", listing_ids)
                .execute()
            )
        else:
            # Get top opportunities
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
                .select("id, sale_price, total_area, neighborhood, title, is_mcmv")
                .in_("id", ids)
                .execute()
            )

        listings = result.data
        logger.info(f"[viability] Analyzing {len(listings)} land listings")

        for listing in listings:
            study = _simulate(listing, cfg)
            if not study:
                continue

            stats["analyzed"] += 1
            is_viable = study["outputs"]["margem_liquida_pct"] >= 15.0

            if is_viable:
                stats["viable"] += 1
            else:
                stats["not_viable"] += 1

            db.table("viability_studies").insert({
                "listing_id": listing["id"],
                "scenario": study["scenario"],
                "inputs": study["inputs"],
                "outputs": study["outputs"],
                "is_viable": is_viable,
            }).execute()

            logger.info(
                f"[viability] #{listing['id']} {listing.get('neighborhood', '?')}: "
                f"{'VIAVEL' if is_viable else 'INVIAVEL'} | "
                f"Margem: {study['outputs']['margem_liquida_pct']:.1f}% | "
                f"ROI: {study['outputs']['roi_pct']:.1f}% | "
                f"{study['outputs']['unidades']} unidades"
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


def _simulate(
    listing: dict[str, Any],
    cfg: dict[str, float],
) -> Optional[dict[str, Any]]:
    """Simulate MCMV construction on a land listing."""
    land_price = float(listing.get("sale_price") or 0)
    land_area = float(listing.get("total_area") or 0)

    if land_price <= 0 or land_area <= 0:
        return None

    # --- Calculate buildable area and units ---
    area_construivel = land_area * cfg["taxa_aproveitamento"] * cfg["pavimentos"]
    unidade_area = cfg["unidade_area"]
    unidades = int(area_construivel / unidade_area)

    if unidades < 1:
        return None

    area_total_construida = unidades * unidade_area

    # --- Costs ---
    custo_terreno = land_price
    custo_construcao = area_total_construida * cfg["custo_construcao_m2"]
    custo_infra = custo_construcao * cfg["custo_infraestrutura_pct"]
    custo_projeto = custo_construcao * cfg["custo_projeto_pct"]
    custo_total_obra = custo_construcao + custo_infra + custo_projeto

    custo_total = custo_terreno + custo_total_obra

    # --- Revenue ---
    preco_venda = min(cfg["preco_venda_unidade"], cfg["mcmv_faixa2_valor_max"])
    vgv = unidades * preco_venda  # Valor Geral de Vendas

    # --- Operating costs ---
    custo_comercial = vgv * cfg["custo_comercializacao_pct"]
    custo_admin = vgv * cfg["custo_administrativo_pct"]
    impostos = vgv * cfg["impostos_pct"]
    custos_operacionais = custo_comercial + custo_admin + impostos

    # --- Results ---
    custo_total_final = custo_total + custos_operacionais
    lucro_bruto = vgv - custo_total
    lucro_liquido = vgv - custo_total_final
    margem_bruta_pct = (lucro_bruto / vgv * 100) if vgv > 0 else 0
    margem_liquida_pct = (lucro_liquido / vgv * 100) if vgv > 0 else 0
    roi_pct = (lucro_liquido / custo_total_final * 100) if custo_total_final > 0 else 0
    custo_por_unidade = custo_total_final / unidades if unidades > 0 else 0

    return {
        "scenario": "MCMV Faixa 2 — Sobrado",
        "inputs": {
            "custo_terreno": custo_terreno,
            "area_terreno_m2": land_area,
            "preco_terreno_m2": round(land_price / land_area, 2),
            "custo_construcao_m2": cfg["custo_construcao_m2"],
            "taxa_aproveitamento": cfg["taxa_aproveitamento"],
            "pavimentos": cfg["pavimentos"],
            "unidade_area_m2": unidade_area,
            "preco_venda_unidade": preco_venda,
        },
        "outputs": {
            "unidades": unidades,
            "area_total_construida_m2": round(area_total_construida, 2),
            "custo_terreno": round(custo_terreno, 2),
            "custo_construcao": round(custo_construcao, 2),
            "custo_infra": round(custo_infra, 2),
            "custo_projeto": round(custo_projeto, 2),
            "custo_total_obra": round(custo_total_obra, 2),
            "custo_comercial": round(custo_comercial, 2),
            "custo_admin": round(custo_admin, 2),
            "impostos": round(impostos, 2),
            "custo_total": round(custo_total_final, 2),
            "vgv": round(vgv, 2),
            "lucro_bruto": round(lucro_bruto, 2),
            "lucro_liquido": round(lucro_liquido, 2),
            "margem_bruta_pct": round(margem_bruta_pct, 2),
            "margem_liquida_pct": round(margem_liquida_pct, 2),
            "roi_pct": round(roi_pct, 2),
            "custo_por_unidade": round(custo_por_unidade, 2),
        },
    }


def _finish_run(
    db: Any,
    run_id: Optional[int],
    status: str,
    stats: dict[str, int],
    error: Optional[str] = None,
) -> None:
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

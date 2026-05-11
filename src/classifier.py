"""Classifier — classifica listings por market tier (padrão de imóvel)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

# Default MCMV max price (overridden by mcmv_rules table)
# Faixa 3 atual ~R$264k urbano; Faixa 4 chega a R$350k em algumas RMs.
# Marília está em transição — usamos teto mais alto pra não perder oportunidades;
# o agente de viability filtra depois.
DEFAULT_MCMV_MAX_PRICE = 350_000
DEFAULT_MCMV_MAX_AREA = 60  # m² (Faixa 1/2 casa típica: 50-55; teto seguro 60)
MCMV_AREA_TOLERANCE = 10    # m² — anúncios mentem; +10 evita falsos negativos


def _infer_mcmv_faixa(price: float) -> Optional[str]:
    """Infer MCMV faixa from sale price. Returns 'faixa12', 'faixa3' or None."""
    if price <= 0:
        return None
    if price <= 200_000:
        return "faixa12"
    if price <= 350_000:
        return "faixa3"
    return None


def classify_listing(
    listing: dict[str, Any],
    mcmv_max_price: float = DEFAULT_MCMV_MAX_PRICE,
) -> str | None:
    """Return the market_tier for a listing, or None if not classifiable."""
    ptype = listing.get("property_type")
    price = float(listing.get("sale_price") or 0)

    if price <= 0:
        return None

    # --- Terrenos ---
    if ptype == "land":
        area = float(listing.get("total_area") or 0)
        if area >= 1_000:
            return "terreno_grande"
        if price <= 120_000:
            return "terreno_economico"
        if price <= 250_000:
            return "terreno_medio"
        return "terreno_alto"

    # --- Casas ---
    if ptype in ("house", "condo_house"):
        raw_built = listing.get("built_area")
        built_area = float(raw_built) if raw_built is not None else None
        is_mcmv_flag = listing.get("is_mcmv", False)

        area_ok = (
            built_area is None
            or built_area <= DEFAULT_MCMV_MAX_AREA + MCMV_AREA_TOLERANCE
        )
        if is_mcmv_flag or (price <= mcmv_max_price and area_ok):
            return "casa_mcmv"
        if price <= 350_000:
            return "casa_baixo_padrao"
        if price <= 700_000:
            return "casa_medio_padrao"
        return "casa_alto_padrao"

    # --- Apartamentos (bonus: classificar também) ---
    if ptype == "apartment":
        if price <= 300_000:
            return "apto_economico"
        if price <= 600_000:
            return "apto_medio"
        return "apto_alto"

    return None


def _get_mcmv_max_price(db: Any) -> float:
    """Fetch current MCMV max price from mcmv_rules table."""
    try:
        result = (
            db.table("mcmv_rules")
            .select("valor_max_imovel")
            .or_("valid_until.is.null,valid_until.gte." + datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            .order("valid_from", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return float(result.data[0]["valor_max_imovel"])
    except Exception:
        logger.warning("[classifier] Could not fetch mcmv_rules, using default")
    return DEFAULT_MCMV_MAX_PRICE


def run_classifier() -> dict[str, int]:
    """Classify all active listings by market tier."""
    db = get_client()
    stats = {"classified": 0, "skipped": 0, "failed": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "classifier", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        mcmv_max = _get_mcmv_max_price(db)
        logger.info(f"[classifier] MCMV max price: R${mcmv_max:,.0f}")

        # Fetch all active listings (paginate)
        listings: list[dict] = []
        page_size = 1000
        offset = 0
        while True:
            result = (
                db.table("listings")
                .select("id, property_type, sale_price, total_area, built_area, is_mcmv")
                .eq("is_active", True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if not result.data:
                break
            listings.extend(result.data)
            if len(result.data) < page_size:
                break
            offset += page_size

        logger.info(f"[classifier] Processing {len(listings)} active listings")

        # Classify and group by (tier, is_mcmv) for batch updates
        by_payload: dict[tuple[str, bool], list[int]] = {}
        mcmv_count = 0
        faixa_dist = {"faixa12": 0, "faixa3": 0, "none": 0}

        for listing in listings:
            tier = classify_listing(listing, mcmv_max)
            if not tier:
                stats["skipped"] += 1
                continue

            ptype = listing.get("property_type")
            price = float(listing.get("sale_price") or 0)
            raw_built = listing.get("built_area")
            built_area = float(raw_built) if raw_built is not None else None
            apt_area_ok = (
                built_area is None
                or built_area <= DEFAULT_MCMV_MAX_AREA + MCMV_AREA_TOLERANCE
            )

            is_mcmv = tier == "casa_mcmv" or (
                ptype == "apartment"
                and tier == "apto_economico"
                and 0 < price <= mcmv_max
                and apt_area_ok
            )

            if is_mcmv:
                mcmv_count += 1
                faixa = _infer_mcmv_faixa(price)
                if faixa == "faixa12":
                    faixa_dist["faixa12"] += 1
                elif faixa == "faixa3":
                    faixa_dist["faixa3"] += 1
                else:
                    faixa_dist["none"] += 1

            by_payload.setdefault((tier, is_mcmv), []).append(listing["id"])
            stats["classified"] += 1

        for (tier, is_mcmv), ids in by_payload.items():
            for i in range(0, len(ids), 500):
                batch_ids = ids[i:i + 500]
                try:
                    db.table("listings").update(
                        {"market_tier": tier, "is_mcmv": is_mcmv}
                    ).in_("id", batch_ids).execute()
                except Exception:
                    logger.exception(f"[classifier] Failed batch update for tier {tier}")

        logger.info(f"[classifier] is_mcmv set on {mcmv_count} listings")
        logger.info(
            f"[classifier] faixa distribution: "
            f"faixa12={faixa_dist['faixa12']} "
            f"faixa3={faixa_dist['faixa3']} "
            f"none={faixa_dist['none']}"
        )

        logger.info(
            f"[classifier] Done: {stats['classified']} classified, "
            f"{stats['skipped']} skipped"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[classifier] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _finish_run(
    db: Any,
    run_id: int | None,
    status: str,
    stats: dict[str, int],
    error: str | None = None,
) -> None:
    if not run_id:
        return
    update: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["classified"] + stats["skipped"],
        "items_created": stats["classified"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

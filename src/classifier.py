"""Classifier — classifica listings por market tier (padrão de imóvel)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

# Default MCMV max price (overridden by mcmv_rules table)
DEFAULT_MCMV_MAX_PRICE = 264_000
DEFAULT_MCMV_MAX_AREA = 70  # m²


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
        built_area = float(listing.get("built_area") or 0)
        is_mcmv = listing.get("is_mcmv", False)

        if is_mcmv or (price <= mcmv_max_price and built_area > 0 and built_area <= DEFAULT_MCMV_MAX_AREA):
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

        # Classify and group by tier for batch updates
        by_tier: dict[str, list[int]] = {}

        for listing in listings:
            tier = classify_listing(listing, mcmv_max)
            if tier:
                by_tier.setdefault(tier, []).append(listing["id"])
                stats["classified"] += 1
            else:
                stats["skipped"] += 1

        # Batch update: 1 query per tier (instead of 1 per listing)
        for tier, ids in by_tier.items():
            for i in range(0, len(ids), 500):
                batch_ids = ids[i:i + 500]
                try:
                    db.table("listings").update(
                        {"market_tier": tier}
                    ).in_("id", batch_ids).execute()
                except Exception:
                    logger.exception(f"[classifier] Failed batch update for tier {tier}")

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

"""Hunter (Caçador) — scores land opportunities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.config import SUPABASE_URL
from src.db import get_client

logger = logging.getLogger(__name__)

# Scoring config (can be overridden via env)
import os

SCORING_MIN_AREA = float(os.getenv("SCORING_MIN_AREA", "200"))
SCORING_MAX_PRICE = float(os.getenv("SCORING_MAX_PRICE", "300000"))
SCORING_IDEAL_PRICE_M2 = float(os.getenv("SCORING_IDEAL_PRICE_M2", "350"))
MCMV_MAX_PRICE = float(os.getenv("MCMV_MAX_PRICE", "264000"))


def run_hunter() -> dict[str, int]:
    """Score all active land listings and create/update opportunities."""
    db = get_client()
    stats = {"scored": 0, "opportunities": 0, "top_score": 0.0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "hunter", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Get market context for relative scoring
        context = _get_market_context(db)
        logger.info(
            f"[hunter] Market context: avg_price_m2={context['avg_price_m2']}, "
            f"median_price={context['median_price']}, total_land={context['total_land']}"
        )

        # Fetch all active land listings
        result = (
            db.table("listings")
            .select("id, source, source_id, sale_price, total_area, "
                    "price_per_m2, neighborhood, latitude, longitude, "
                    "is_mcmv, title, address")
            .eq("is_active", True)
            .eq("property_type", "land")
            .not_.is_("sale_price", "null")
            .gt("sale_price", 0)
            .execute()
        )

        listings = result.data
        logger.info(f"[hunter] Scoring {len(listings)} land listings")

        scored = []
        for listing in listings:
            score, breakdown = _score_listing(listing, context)
            scored.append((listing, score, breakdown))
            stats["scored"] += 1

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        if scored:
            stats["top_score"] = scored[0][1]

        # Delete existing opportunities and re-create
        db.table("opportunities").delete().neq("id", 0).execute()

        for listing, score, breakdown in scored:
            if score < 30:
                continue  # Skip low-scoring listings

            reason = _build_reason(listing, score, breakdown)

            db.table("opportunities").insert({
                "listing_id": listing["id"],
                "score": score,
                "score_breakdown": breakdown,
                "reason": reason,
            }).execute()
            stats["opportunities"] += 1

        logger.info(
            f"[hunter] Done: {stats['scored']} scored, "
            f"{stats['opportunities']} opportunities (top: {stats['top_score']:.1f})"
        )

        # Log top 10
        for listing, score, breakdown in scored[:10]:
            logger.info(
                f"[hunter] TOP {score:.1f}: "
                f"R${listing['sale_price']:,.0f} | "
                f"{listing.get('total_area', '?')}m² | "
                f"{listing.get('neighborhood', '?')} | "
                f"{listing.get('source', '')}:{listing.get('source_id', '')}"
            )

        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[hunter] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _get_market_context(db: Any) -> dict[str, float]:
    """Get market averages for land listings to use in relative scoring."""
    result = (
        db.table("listings")
        .select("sale_price, total_area, price_per_m2")
        .eq("is_active", True)
        .eq("property_type", "land")
        .not_.is_("sale_price", "null")
        .gt("sale_price", 0)
        .execute()
    )

    prices = [float(r["sale_price"]) for r in result.data]
    areas = [float(r["total_area"]) for r in result.data if r.get("total_area")]
    price_m2s = [float(r["price_per_m2"]) for r in result.data if r.get("price_per_m2")]

    prices.sort()
    n = len(prices)
    median = prices[n // 2] if n else 0

    return {
        "avg_price": sum(prices) / n if n else 0,
        "median_price": median,
        "avg_price_m2": sum(price_m2s) / len(price_m2s) if price_m2s else 0,
        "avg_area": sum(areas) / len(areas) if areas else 0,
        "total_land": n,
    }


def _score_listing(
    listing: dict[str, Any],
    context: dict[str, float],
) -> tuple[float, dict[str, Any]]:
    """Score a single land listing. Returns (score, breakdown).

    Score is 0-100 based on:
    - price_score (30pts): lower price = better
    - price_m2_score (25pts): lower price/m² = better
    - area_score (20pts): larger area = better (up to a point)
    - mcmv_score (15pts): MCMV compatible = bonus
    - location_score (10pts): has coordinates = bonus, known neighborhood = bonus
    """
    breakdown: dict[str, Any] = {}
    price = float(listing.get("sale_price") or 0)
    area = float(listing.get("total_area") or 0)
    price_m2 = float(listing.get("price_per_m2") or 0)

    # --- Price score (30pts): better if below max, best if way below ---
    if price <= 0:
        breakdown["price"] = 0
    elif price <= SCORING_MAX_PRICE * 0.5:
        breakdown["price"] = 30  # Amazing deal
    elif price <= SCORING_MAX_PRICE * 0.75:
        breakdown["price"] = 25
    elif price <= SCORING_MAX_PRICE:
        breakdown["price"] = 20
    elif price <= SCORING_MAX_PRICE * 1.5:
        breakdown["price"] = 10
    elif price <= SCORING_MAX_PRICE * 2:
        breakdown["price"] = 5
    else:
        breakdown["price"] = 0

    # --- Price per m² score (25pts): relative to market ---
    if price_m2 <= 0:
        breakdown["price_m2"] = 5  # No data, neutral
    elif price_m2 <= SCORING_IDEAL_PRICE_M2 * 0.5:
        breakdown["price_m2"] = 25
    elif price_m2 <= SCORING_IDEAL_PRICE_M2:
        breakdown["price_m2"] = 20
    elif price_m2 <= context.get("avg_price_m2", 500):
        breakdown["price_m2"] = 15
    elif price_m2 <= context.get("avg_price_m2", 500) * 1.5:
        breakdown["price_m2"] = 8
    else:
        breakdown["price_m2"] = 0

    # --- Area score (20pts): prefer >= SCORING_MIN_AREA ---
    if area <= 0:
        breakdown["area"] = 5  # No data
    elif area >= SCORING_MIN_AREA * 2:
        breakdown["area"] = 20
    elif area >= SCORING_MIN_AREA * 1.5:
        breakdown["area"] = 18
    elif area >= SCORING_MIN_AREA:
        breakdown["area"] = 15
    elif area >= SCORING_MIN_AREA * 0.75:
        breakdown["area"] = 10
    elif area >= SCORING_MIN_AREA * 0.5:
        breakdown["area"] = 5
    else:
        breakdown["area"] = 2

    # --- MCMV score (15pts) ---
    is_mcmv = listing.get("is_mcmv", False)
    mcmv_price_ok = 0 < price <= MCMV_MAX_PRICE
    if is_mcmv:
        breakdown["mcmv"] = 15
    elif mcmv_price_ok:
        breakdown["mcmv"] = 10  # Price compatible even without flag
    elif price <= MCMV_MAX_PRICE * 1.2:
        breakdown["mcmv"] = 5  # Close to MCMV range
    else:
        breakdown["mcmv"] = 0

    # --- Location score (10pts) ---
    has_coords = (
        listing.get("latitude") is not None
        and listing.get("longitude") is not None
    )
    has_neighborhood = bool(listing.get("neighborhood"))

    loc_score = 0
    if has_coords:
        loc_score += 5
    if has_neighborhood:
        loc_score += 5
    breakdown["location"] = loc_score

    total = sum(breakdown.values())
    breakdown["total"] = total
    return total, breakdown


def _build_reason(
    listing: dict[str, Any],
    score: float,
    breakdown: dict[str, Any],
) -> str:
    """Build a human-readable reason for the score."""
    parts = []
    price = float(listing.get("sale_price") or 0)
    area = float(listing.get("total_area") or 0)
    price_m2 = float(listing.get("price_per_m2") or 0)
    neigh = listing.get("neighborhood", "?")

    if score >= 80:
        parts.append("🔥 Oportunidade excelente!")
    elif score >= 60:
        parts.append("⭐ Boa oportunidade")
    elif score >= 40:
        parts.append("👀 Vale acompanhar")
    else:
        parts.append("📋 Registro")

    parts.append(f"R$ {price:,.0f}")
    if area > 0:
        parts.append(f"{area:.0f}m²")
    if price_m2 > 0:
        parts.append(f"R$ {price_m2:,.0f}/m²")
    parts.append(f"Bairro: {neigh}")

    if breakdown.get("mcmv", 0) >= 10:
        parts.append("MCMV compatível")

    return " | ".join(parts)


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
        "items_processed": stats["scored"],
        "items_created": stats["opportunities"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

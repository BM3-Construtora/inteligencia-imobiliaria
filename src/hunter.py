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
                    "is_mcmv, title, address, first_seen_at, features")
            .eq("is_active", True)
            .eq("property_type", "land")
            .not_.is_("sale_price", "null")
            .gt("sale_price", 5000)  # Filter out placeholder/error prices
            .execute()
        )

        listings = result.data
        logger.info(f"[hunter] Scoring {len(listings)} land listings (filtered price > R$5000)")

        scored = []
        for listing in listings:
            score, breakdown = _score_listing(listing, context)
            scored.append((listing, score, breakdown))
            stats["scored"] += 1

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        if scored:
            stats["top_score"] = scored[0][1]

        # Batch upsert opportunities
        opp_batch: list[dict] = []
        for listing, score, breakdown in scored:
            if score < 30:
                continue

            reason = _build_reason(listing, score, breakdown)
            opp_batch.append({
                "listing_id": listing["id"],
                "score": score,
                "score_breakdown": breakdown,
                "reason": reason,
            })
            stats["opportunities"] += 1

        # Flush in batches of 100
        for i in range(0, len(opp_batch), 100):
            batch = opp_batch[i:i + 100]
            try:
                db.table("opportunities").upsert(
                    batch, on_conflict="listing_id"
                ).execute()
            except Exception:
                # Fallback: one by one
                for item in batch:
                    try:
                        db.table("opportunities").upsert(
                            item, on_conflict="listing_id"
                        ).execute()
                    except Exception:
                        pass

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


# Source confidence weights — based on data quality audit
# Applied as a multiplier to the raw score
SOURCE_CONFIDENCE = {
    "uniao": 1.00,       # Tier 1: GPS, endereço, MCMV flag, API estruturada
    "toca": 1.00,        # Tier 1: GPS, preço 100%, zona do bairro
    "vivareal": 0.85,    # Tier 2: bons dados preço/área, sem geo
    "chavesnamao": 0.80,  # Tier 2: muitos terrenos, área ~52% confiável
    "imovelweb": 0.70,   # Tier 3: poucos dados, área 32%, Cloudflare
}


def _score_listing(
    listing: dict[str, Any],
    context: dict[str, float],
) -> tuple[float, dict[str, Any]]:
    """Score a single land listing. Returns (score, breakdown).

    Raw score is 0-100 based on:
    - price_score (25pts): lower price = better
    - price_m2_score (20pts): lower price/m² = better
    - area_score (15pts): larger area = better (up to a point)
    - mcmv_score (10pts): MCMV compatible = bonus
    - location_score (10pts): has coordinates = bonus, known neighborhood = bonus
    - data_quality (10pts): completeness of fields for this listing
    - source_confidence (10pts): reliability of the source

    Final score = raw_score * source_confidence_multiplier
    """
    breakdown: dict[str, Any] = {}
    source = listing.get("source", "")
    price = float(listing.get("sale_price") or 0)
    area = float(listing.get("total_area") or 0)
    price_m2 = float(listing.get("price_per_m2") or 0)

    # --- Price score (25pts): better if below max, best if way below ---
    if price <= 0:
        breakdown["price"] = 0
    elif price <= SCORING_MAX_PRICE * 0.5:
        breakdown["price"] = 25
    elif price <= SCORING_MAX_PRICE * 0.75:
        breakdown["price"] = 20
    elif price <= SCORING_MAX_PRICE:
        breakdown["price"] = 17
    elif price <= SCORING_MAX_PRICE * 1.5:
        breakdown["price"] = 8
    elif price <= SCORING_MAX_PRICE * 2:
        breakdown["price"] = 4
    else:
        breakdown["price"] = 0

    # --- Price per m² score (20pts): relative to market ---
    if price_m2 <= 0:
        breakdown["price_m2"] = 0  # No data = no points (was 5 before, rewarded missing data)
    elif price_m2 <= SCORING_IDEAL_PRICE_M2 * 0.5:
        breakdown["price_m2"] = 20
    elif price_m2 <= SCORING_IDEAL_PRICE_M2:
        breakdown["price_m2"] = 17
    elif price_m2 <= context.get("avg_price_m2", 500):
        breakdown["price_m2"] = 12
    elif price_m2 <= context.get("avg_price_m2", 500) * 1.5:
        breakdown["price_m2"] = 6
    else:
        breakdown["price_m2"] = 0

    # --- Area score (15pts): prefer >= SCORING_MIN_AREA ---
    if area <= 0:
        breakdown["area"] = 0  # No data = no points
    elif area >= SCORING_MIN_AREA * 2:
        breakdown["area"] = 15
    elif area >= SCORING_MIN_AREA * 1.5:
        breakdown["area"] = 13
    elif area >= SCORING_MIN_AREA:
        breakdown["area"] = 11
    elif area >= SCORING_MIN_AREA * 0.75:
        breakdown["area"] = 7
    elif area >= SCORING_MIN_AREA * 0.5:
        breakdown["area"] = 4
    else:
        breakdown["area"] = 2

    # --- MCMV score (10pts) ---
    is_mcmv = listing.get("is_mcmv", False)
    mcmv_price_ok = 0 < price <= MCMV_MAX_PRICE
    if is_mcmv:
        breakdown["mcmv"] = 10
    elif mcmv_price_ok:
        breakdown["mcmv"] = 7
    elif price <= MCMV_MAX_PRICE * 1.2:
        breakdown["mcmv"] = 3
    else:
        breakdown["mcmv"] = 0

    # --- Location score (10pts) ---
    has_coords = (
        listing.get("latitude") is not None
        and listing.get("longitude") is not None
    )
    has_neighborhood = bool(listing.get("neighborhood"))
    has_address = bool(listing.get("address"))

    loc_score = 0
    if has_coords:
        loc_score += 5
    if has_neighborhood:
        loc_score += 3
    if has_address:
        loc_score += 2
    breakdown["location"] = loc_score

    # --- Data quality score (10pts): reward complete listings ---
    dq = 0
    if price > 0:
        dq += 2
    if area > 0:
        dq += 2
    if price_m2 > 0:
        dq += 2
    if has_coords:
        dq += 2
    if listing.get("title"):
        dq += 1
    if listing.get("is_mcmv") is not None:
        dq += 1
    breakdown["data_quality"] = dq

    # --- Enriched features bonus (up to 10pts) ---
    features = listing.get("features") or {}
    if isinstance(features, list):
        features = {}
    enriched = features.get("_source") == "claude_haiku"

    enrich_score = 0
    if enriched:
        # Infrastructure: +1 per item (max 4)
        infra = features.get("infraestrutura") or []
        enrich_score += min(len(infra), 4)

        # Proximities: +1 per item (max 3)
        prox = features.get("proximidades") or []
        enrich_score += min(len(prox), 3)

        # Zoning: residential = +2, mixed = +1
        zoning = (features.get("zoneamento") or "").lower()
        if "residencial" in zoning:
            enrich_score += 2
        elif "misto" in zoning:
            enrich_score += 1

        # Flat terrain bonus
        terreno = features.get("caracteristicas_terreno") or []
        if any("plano" in str(t).lower() for t in terreno):
            enrich_score += 1

    breakdown["enriched"] = min(enrich_score, 10)

    # --- Stale bonus (5pts): terrenos parados há muito tempo = vendedor negocia ---
    from datetime import datetime, timezone
    stale = 0
    fs = listing.get("first_seen_at")
    if fs:
        try:
            first = datetime.fromisoformat(str(fs).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - first).days
            if days >= 120:
                stale = 5  # 4+ meses parado
            elif days >= 90:
                stale = 4
            elif days >= 60:
                stale = 2
        except (ValueError, TypeError):
            pass
    breakdown["stale_bonus"] = stale

    # --- Source confidence (10pts) ---
    confidence = SOURCE_CONFIDENCE.get(source, 0.70)
    breakdown["source_confidence"] = round(confidence * 10)

    raw_total = sum(breakdown.values())

    # Apply source confidence as multiplier to the raw score
    final = round(raw_total * confidence, 1)
    breakdown["raw_total"] = raw_total
    breakdown["confidence_multiplier"] = confidence
    breakdown["total"] = final

    return final, breakdown


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

    source = listing.get("source", "?")
    confidence = breakdown.get("confidence_multiplier", 1.0)

    if score >= 70:
        parts.append("Oportunidade excelente")
    elif score >= 55:
        parts.append("Boa oportunidade")
    elif score >= 40:
        parts.append("Vale acompanhar")
    else:
        parts.append("Registro")

    parts.append(f"R$ {price:,.0f}")
    if area > 0:
        parts.append(f"{area:.0f}m²")
    if price_m2 > 0:
        parts.append(f"R$ {price_m2:,.0f}/m²")
    parts.append(f"Bairro: {neigh}")

    if breakdown.get("mcmv", 0) >= 7:
        parts.append("MCMV compativel")

    # Confidence tag
    if confidence >= 1.0:
        parts.append(f"[{source} alta confianca]")
    elif confidence >= 0.85:
        parts.append(f"[{source} media confianca]")
    else:
        parts.append(f"[{source} baixa confianca - validar dados]")

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

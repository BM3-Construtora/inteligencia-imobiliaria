"""Comparable listings analysis — find similar properties for each listing."""

from __future__ import annotations

import logging
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)


def find_comparables(
    listing_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find the most similar active listings to a given listing.

    Similarity based on: same property_type, area ±30%, same or nearby neighborhood.
    Returns sorted by price similarity.
    """
    db = get_client()

    # Get the target listing
    result = db.table("listings").select(
        "id, property_type, sale_price, total_area, neighborhood, price_per_m2"
    ).eq("id", listing_id).limit(1).execute()

    if not result.data:
        return []

    target = result.data[0]
    ptype = target.get("property_type")
    area = float(target.get("total_area") or 0)
    price = float(target.get("sale_price") or 0)
    neighborhood = target.get("neighborhood")

    if not ptype or area <= 0 or price <= 0:
        return []

    # Find candidates: same type, area ±30%
    area_min = area * 0.7
    area_max = area * 1.3

    query = (
        db.table("listings")
        .select("id, source, neighborhood, sale_price, total_area, price_per_m2, title, url")
        .eq("is_active", True)
        .eq("property_type", ptype)
        .neq("id", listing_id)
        .not_.is_("sale_price", "null")
        .gt("sale_price", 0)
        .not_.is_("total_area", "null")
        .gte("total_area", area_min)
        .lte("total_area", area_max)
        .limit(50)
    )
    candidates = query.execute()

    if not candidates.data:
        return []

    # Score each candidate
    scored = []
    for c in candidates.data:
        c_price = float(c.get("sale_price") or 0)
        c_area = float(c.get("total_area") or 0)
        if c_price <= 0 or c_area <= 0:
            continue

        # Similarity score: area closeness + neighborhood match + price closeness
        area_sim = 1.0 - abs(c_area - area) / max(c_area, area)
        price_sim = 1.0 - min(1.0, abs(c_price - price) / max(c_price, price))
        neigh_bonus = 0.2 if c.get("neighborhood") == neighborhood else 0.0

        sim_score = area_sim * 0.4 + price_sim * 0.4 + neigh_bonus

        scored.append({
            **c,
            "similarity": round(sim_score, 3),
        })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def run_comps_for_opportunities() -> dict[str, int]:
    """Find comparables for all top opportunities and store in score_breakdown."""
    db = get_client()
    stats = {"processed": 0, "with_comps": 0}

    # Get top 50 opportunities
    result = (
        db.table("opportunities")
        .select("id, listing_id, score_breakdown")
        .order("score", desc=True)
        .limit(50)
        .execute()
    )

    for opp in result.data:
        comps = find_comparables(opp["listing_id"], limit=5)
        stats["processed"] += 1

        if comps:
            stats["with_comps"] += 1
            # Store comp IDs and summary in breakdown
            breakdown = opp.get("score_breakdown") or {}
            breakdown["comps"] = [
                {
                    "id": c["id"],
                    "price": c.get("sale_price"),
                    "area": c.get("total_area"),
                    "neighborhood": c.get("neighborhood"),
                    "similarity": c["similarity"],
                }
                for c in comps
            ]
            try:
                db.table("opportunities").update(
                    {"score_breakdown": breakdown}
                ).eq("id", opp["id"]).execute()
            except Exception:
                pass

    logger.info(f"[comps] Done: {stats['processed']} processed, {stats['with_comps']} with comps")
    return stats

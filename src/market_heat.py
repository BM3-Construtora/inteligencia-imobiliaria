"""Market heat — composite score 0-100 per neighborhood indicating market activity."""

from __future__ import annotations

import logging
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)


def run_market_heat() -> dict[str, int]:
    """Calculate market heat score for each neighborhood and store."""
    db = get_client()
    stats = {"neighborhoods": 0, "hot": 0, "cold": 0}

    try:
        result = db.table("neighborhoods").select(
            "name, total_listings, absorption_rate, months_of_inventory, "
            "avg_days_on_market, removed_last_30d, new_last_30d, "
            "avg_price_m2_land, avg_risk_score"
        ).gt("total_listings", 0).execute()

        # Calculate all scores in memory
        updates: dict[int, list[str]] = {}  # score → list of neighborhood names
        for n in (result.data or []):
            score = _calc_heat(n)
            stats["neighborhoods"] += 1
            if score >= 70:
                stats["hot"] += 1
            elif score <= 30:
                stats["cold"] += 1
            updates.setdefault(score, []).append(n["name"])

        # Batch update: 1 query per unique score
        for score, names in updates.items():
            for i in range(0, len(names), 100):
                batch = names[i:i + 100]
                try:
                    db.table("neighborhoods").update(
                        {"market_heat_score": score}
                    ).in_("name", batch).execute()
                except Exception:
                    pass

        logger.info(
            f"[heat] Done: {stats['neighborhoods']} scored, "
            f"{stats['hot']} hot, {stats['cold']} cold"
        )

    except Exception:
        logger.exception("[heat] Failed")

    return stats


def _calc_heat(n: dict[str, Any]) -> int:
    """Calculate composite heat score 0-100.

    Components:
    - Absorption rate (30%): higher = hotter
    - Price trend proxy via new/removed ratio (25%)
    - Avg days on market (20%): lower = hotter
    - New listings velocity (15%): more new = more interest
    - Risk inverse (10%): lower risk = more attractive
    """
    score = 0.0

    # Absorption (30 pts): >10% = 30, 5-10% = 20, 1-5% = 10, <1% = 0
    absorption = float(n.get("absorption_rate") or 0)
    if absorption > 10:
        score += 30
    elif absorption > 5:
        score += 20
    elif absorption > 1:
        score += 10

    # Sales vs new ratio (25 pts): more removals than new = healthy demand
    removed = int(n.get("removed_last_30d") or 0)
    new = int(n.get("new_last_30d") or 0)
    if removed > 0 and new > 0:
        ratio = removed / new
        if ratio > 1.0:
            score += 25  # More selling than listing = hot
        elif ratio > 0.5:
            score += 15
        elif ratio > 0.2:
            score += 8

    # Days on market (20 pts): <30 = 20, 30-60 = 15, 60-120 = 8, >120 = 0
    dom = int(n.get("avg_days_on_market") or 999)
    if dom < 30:
        score += 20
    elif dom < 60:
        score += 15
    elif dom < 120:
        score += 8

    # New listings velocity (15 pts): >10/month = 15, 5-10 = 10, 1-5 = 5
    if new > 10:
        score += 15
    elif new > 5:
        score += 10
    elif new > 1:
        score += 5

    # Risk inverse (10 pts): risk <2 = 10, 2-3 = 6, 3-4 = 3, >4 = 0
    risk = float(n.get("avg_risk_score") or 3)
    if risk < 2:
        score += 10
    elif risk < 3:
        score += 6
    elif risk < 4:
        score += 3

    return min(100, max(0, int(score)))

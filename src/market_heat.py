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
        scored: list[tuple[str, int]] = []
        for n in (result.data or []):
            score = _calc_heat(n)
            scored.append((n["name"], score))
            stats["neighborhoods"] += 1

        # Percentile-based thresholds within current run, com floor
        # absoluto pra evitar degeneração (p33==p66 quando scores enviesados).
        scores_only = sorted(s for _, s in scored)
        p33 = _percentile(scores_only, 33)
        p66 = _percentile(scores_only, 66)
        cold_th = max(p33, 25)
        hot_th = max(p66, 50)
        if cold_th >= hot_th:
            cold_th, hot_th = 25, 50
        logger.info(
            f"[heat] thresholds: cold<{cold_th}, hot>={hot_th} "
            f"(p33={p33}, p66={p66}, n={len(scores_only)})"
        )

        updates: dict[int, list[str]] = {}
        for name, score in scored:
            if score >= hot_th:
                stats["hot"] += 1
            elif score < cold_th:
                stats["cold"] += 1
            updates.setdefault(score, []).append(name)

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
    """Calculate composite heat score 0-100 (continuous to avoid degenerate distribution).

    Components com pesos:
    - Absorption rate (30 pts): normalizado 0-10%+ → 0-30
    - Sales/new ratio (25 pts): normalizado 0-1.5x → 0-25
    - Days on market (20 pts): 0d=20, 180d=0 linear
    - New listings velocity (15 pts): 0-15 listings/mês → 0-15
    - Risk inverse (10 pts): risk 1=10, risk 4+=0 linear
    """
    absorption = float(n.get("absorption_rate") or 0)
    score_abs = 30 * min(absorption / 10.0, 1.0)

    removed = int(n.get("removed_last_30d") or 0)
    new = int(n.get("new_last_30d") or 0)
    if removed > 0 and new > 0:
        ratio = removed / new
        score_ratio = 25 * min(ratio / 1.5, 1.0)
    else:
        score_ratio = 0.0

    dom = int(n.get("avg_days_on_market") or 999)
    score_dom = 20 * max(0.0, 1.0 - dom / 180.0)

    score_new = 15 * min(new / 15.0, 1.0)

    risk = float(n.get("avg_risk_score") or 3)
    score_risk = 10 * max(0.0, 1.0 - (risk - 1) / 3.0)

    total = score_abs + score_ratio + score_dom + score_new + score_risk
    return min(100, max(0, int(round(total))))


def _percentile(sorted_vals: list[int], pct: float) -> int:
    """Returns percentile value from a sorted list (linear interpolation)."""
    if not sorted_vals:
        return 0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    frac = k - lo
    return int(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac)

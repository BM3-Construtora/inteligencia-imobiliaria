"""Quick AVM (Automated Valuation Model) for Track B — Ficha de Terreno.

Strategy:
1. Try to read pre-computed prediction from `avm_predictions` table (Track E). If absent or empty, fallback.
2. Fallback: quantile-based AVM from neighborhood comps in `listings`.

All DB calls are wrapped in try/except — never raises, returns empty/fallback dict.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _quantile(values: list[float], q: float) -> float:
    """Quantile by linear interpolation. Pure Python, no numpy."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def quick_avm(neighborhood: str, area: float, db: Any) -> dict[str, Any]:
    """Compute a quick AVM (P25/P50/P75 of price_per_m2) for a neighborhood.

    Returns dict with: p25, p50, p75, n_comps, method.
    On total failure returns {"p25":0,"p50":0,"p75":0,"n_comps":0,"method":"unavailable"}.
    """
    empty = {"p25": 0.0, "p50": 0.0, "p75": 0.0, "n_comps": 0, "method": "unavailable"}

    if not neighborhood:
        return empty

    # 1) Try pre-computed avm_predictions (Track E)
    try:
        result = (
            db.table("avm_predictions")
            .select("p25, p50, p75, n_comps")
            .ilike("neighborhood", neighborhood)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            p25 = float(row.get("p25") or 0)
            p50 = float(row.get("p50") or 0)
            p75 = float(row.get("p75") or 0)
            n = int(row.get("n_comps") or 0)
            if p50 > 0:
                return {
                    "p25": p25, "p50": p50, "p75": p75,
                    "n_comps": n, "method": "avm_predictions_table",
                }
    except Exception as exc:
        logger.debug(f"[avm] avm_predictions unavailable: {exc}")

    # 2) Fallback: compute from listings
    try:
        result = (
            db.table("listings")
            .select("price_per_m2, sale_price, total_area")
            .eq("is_active", True)
            .ilike("neighborhood", neighborhood)
            .not_.is_("price_per_m2", "null")
            .gt("price_per_m2", 0)
            .limit(200)
            .execute()
        )
        rows = result.data or []
        prices: list[float] = []
        for r in rows:
            try:
                v = float(r.get("price_per_m2") or 0)
                if v > 0:
                    prices.append(v)
            except (TypeError, ValueError):
                continue

        if len(prices) < 3:
            return empty

        return {
            "p25": round(_quantile(prices, 0.25), 2),
            "p50": round(statistics.median(prices), 2),
            "p75": round(_quantile(prices, 0.75), 2),
            "n_comps": len(prices),
            "method": "neighborhood_quantile",
        }
    except Exception as exc:
        logger.debug(f"[avm] fallback failed: {exc}")
        return empty

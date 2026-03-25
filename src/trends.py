"""Trends — detects price trends per neighborhood using linear regression."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)


def run_trends() -> dict[str, int]:
    """Calculate price trends for neighborhoods and update the neighborhoods table."""
    db = get_client()
    stats = {"neighborhoods": 0, "aquecendo": 0, "esfriando": 0, "estavel": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "trends", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Get neighborhoods with land
        neighs = (
            db.table("neighborhoods")
            .select("name")
            .gt("total_land", 0)
            .execute()
        )

        for neigh in neighs.data:
            name = neigh["name"]
            trend = _calc_trend(db, name, "land")

            if trend is None:
                continue

            slope, label = trend
            stats["neighborhoods"] += 1
            stats[label] += 1

            # Update neighborhood
            db.table("neighborhoods").update({
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("name", name).execute()

            # Store trend in market_snapshots metadata
            # For now we log it — trends need accumulated data over weeks
            if label != "estavel":
                logger.info(
                    f"[trends] {name}: {label} ({slope:+.1f}% variacao estimada)"
                )

        logger.info(
            f"[trends] Done: {stats['neighborhoods']} bairros analisados — "
            f"{stats['aquecendo']} aquecendo, {stats['esfriando']} esfriando, "
            f"{stats['estavel']} estavel"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[trends] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _calc_trend(
    db: Any, neighborhood: str, property_type: str
) -> Optional[tuple[float, str]]:
    """Calculate price trend for a neighborhood.

    Returns (slope_pct, label) where label is 'aquecendo'/'esfriando'/'estavel'.
    Returns None if insufficient data.
    """
    # Get snapshots for this neighborhood over time
    result = (
        db.table("market_snapshots")
        .select("snapshot_date, avg_price_m2, total_listings")
        .eq("property_type", property_type)
        .eq("neighborhood", neighborhood)
        .not_.is_("avg_price_m2", "null")
        .order("snapshot_date")
        .execute()
    )

    points = result.data
    if len(points) < 2:
        return None

    # Convert to numeric series
    dates = []
    values = []
    base_date = None

    for p in points:
        try:
            d = datetime.strptime(p["snapshot_date"], "%Y-%m-%d")
            v = float(p["avg_price_m2"])
            if base_date is None:
                base_date = d
            dates.append((d - base_date).days)
            values.append(v)
        except (ValueError, TypeError):
            continue

    if len(dates) < 2:
        return None

    # Linear regression (no dependencies)
    slope = _linear_slope(dates, values)

    # Convert slope to percentage change per 30 days
    avg_value = sum(values) / len(values)
    if avg_value <= 0:
        return None

    pct_per_30d = (slope * 30 / avg_value) * 100

    # Classify
    if pct_per_30d > 2.0:
        label = "aquecendo"
    elif pct_per_30d < -2.0:
        label = "esfriando"
    else:
        label = "estavel"

    return pct_per_30d, label


def _linear_slope(x: list[float], y: list[float]) -> float:
    """Simple linear regression slope. No external dependencies."""
    n = len(x)
    if n < 2:
        return 0.0

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    denominator = sum((xi - x_mean) ** 2 for xi in x)

    return numerator / denominator if denominator > 0 else 0.0


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
        "items_processed": stats["neighborhoods"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

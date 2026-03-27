"""Price prediction model — estimates fair market value for land listings.

Uses a simple Random Forest trained on current listing data to identify
undervalued properties. Stores predicted_price in opportunities.score_breakdown.
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)


def run_price_model() -> dict[str, int]:
    """Train a price model and score all land listings."""
    db = get_client()
    stats = {"trained_on": 0, "predicted": 0, "undervalued": 0, "failed": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "price_model", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Fetch training data: active land listings with price and area
        listings: list[dict] = []
        page_size = 1000
        offset = 0
        while True:
            result = (
                db.table("listings")
                .select("id, sale_price, total_area, price_per_m2, neighborhood, "
                        "latitude, longitude, is_mcmv, features")
                .eq("is_active", True)
                .eq("property_type", "land")
                .not_.is_("sale_price", "null")
                .gt("sale_price", 5000)
                .not_.is_("total_area", "null")
                .gt("total_area", 15)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if not result.data:
                break
            listings.extend(result.data)
            if len(result.data) < page_size:
                break
            offset += page_size

        if len(listings) < 20:
            logger.warning(f"[price_model] Only {len(listings)} listings, need at least 20")
            _finish_run(db, run_id, "completed", stats)
            return stats

        # Build neighborhood price index for encoding
        neigh_prices: dict[str, float] = {}
        for l in listings:
            n = l.get("neighborhood", "")
            pm2 = float(l.get("price_per_m2") or 0)
            if n and pm2 > 0:
                neigh_prices.setdefault(n, []).append(pm2)
        neigh_avg = {n: sum(ps) / len(ps) for n, ps in neigh_prices.items() if ps}

        # Feature extraction
        features = []
        prices = []
        listing_ids = []

        for l in listings:
            area = float(l.get("total_area") or 0)
            price = float(l.get("sale_price") or 0)
            if area <= 0 or price <= 0:
                continue

            n = l.get("neighborhood", "")
            neigh_price_avg = neigh_avg.get(n, 0)
            has_coords = 1 if l.get("latitude") and l.get("longitude") else 0
            is_mcmv = 1 if l.get("is_mcmv") else 0

            feat_data = l.get("features") or {}
            if isinstance(feat_data, str):
                try:
                    feat_data = json.loads(feat_data)
                except (json.JSONDecodeError, TypeError):
                    feat_data = {}
            infra_count = len(feat_data.get("infraestrutura") or [])
            prox_count = len(feat_data.get("proximidades") or [])

            features.append([
                area,
                neigh_price_avg,
                has_coords,
                is_mcmv,
                infra_count,
                prox_count,
            ])
            prices.append(price)
            listing_ids.append(l["id"])

        stats["trained_on"] = len(features)
        logger.info(f"[price_model] Training on {len(features)} listings")

        # Train model
        try:
            from sklearn.ensemble import RandomForestRegressor
            import numpy as np
        except ImportError:
            logger.warning("[price_model] scikit-learn not installed, skipping")
            _finish_run(db, run_id, "completed", stats)
            return stats

        X = np.array(features)
        y = np.array(prices)

        model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
        model.fit(X, y)

        # Predict and find undervalued
        predictions = model.predict(X)

        for i, (lid, actual, predicted) in enumerate(zip(listing_ids, prices, predictions)):
            stats["predicted"] += 1
            diff_pct = (predicted - actual) / predicted * 100

            # Store prediction in opportunities score_breakdown
            if diff_pct > 15:  # Predicted value 15%+ above asking = undervalued
                stats["undervalued"] += 1

            try:
                # Update opportunity if exists
                result = (
                    db.table("opportunities")
                    .select("id, score_breakdown")
                    .eq("listing_id", lid)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    breakdown = result.data[0].get("score_breakdown") or {}
                    breakdown["predicted_price"] = round(predicted, 0)
                    breakdown["price_diff_pct"] = round(diff_pct, 1)
                    db.table("opportunities").update(
                        {"score_breakdown": breakdown}
                    ).eq("id", result.data[0]["id"]).execute()
            except Exception:
                stats["failed"] += 1

        logger.info(
            f"[price_model] Done: trained on {stats['trained_on']}, "
            f"predicted {stats['predicted']}, "
            f"{stats['undervalued']} undervalued (>15% below fair value)"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[price_model] Failed")
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
        "items_processed": stats["trained_on"],
        "items_created": stats["predicted"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

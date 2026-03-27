"""Sales tracker — detect removed listings as sold estimates."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)


def run_sales_tracker() -> dict[str, int]:
    """Detect recently deactivated listings and record as sold estimates."""
    db = get_client()
    stats = {"detected": 0, "recorded": 0}

    try:
        # Find listings deactivated but not yet recorded as sold
        result = (
            db.table("listings")
            .select("id, sale_price, neighborhood, property_type, total_area, "
                    "first_seen_at, deactivated_at")
            .eq("is_active", False)
            .not_.is_("deactivated_at", "null")
            .not_.is_("sale_price", "null")
            .execute()
        )

        deactivated = result.data or []
        stats["detected"] = len(deactivated)

        # Check which are already tracked
        existing_ids = set()
        if deactivated:
            ids = [d["id"] for d in deactivated]
            for i in range(0, len(ids), 200):
                batch = ids[i:i+200]
                r = db.table("sold_estimates").select("listing_id").in_("listing_id", batch).execute()
                existing_ids.update(e["listing_id"] for e in (r.data or []))

        # Insert new sold estimates
        now = datetime.now(timezone.utc)
        batch = []
        for listing in deactivated:
            if listing["id"] in existing_ids:
                continue

            # Calculate days on market
            dom = None
            fs = listing.get("first_seen_at")
            da = listing.get("deactivated_at")
            if fs and da:
                try:
                    first = datetime.fromisoformat(str(fs).replace("Z", "+00:00"))
                    deact = datetime.fromisoformat(str(da).replace("Z", "+00:00"))
                    dom = (deact - first).days
                except (ValueError, TypeError):
                    pass

            batch.append({
                "listing_id": listing["id"],
                "last_price": listing.get("sale_price"),
                "neighborhood": listing.get("neighborhood"),
                "property_type": listing.get("property_type"),
                "total_area": listing.get("total_area"),
                "days_on_market": dom,
            })

            if len(batch) >= 100:
                _flush(db, batch, stats)
                batch = []

        if batch:
            _flush(db, batch, stats)

        logger.info(f"[sales] Done: {stats['detected']} detected, {stats['recorded']} new recorded")

    except Exception:
        logger.exception("[sales] Failed")

    return stats


def _flush(db: Any, batch: list[dict], stats: dict) -> None:
    for item in batch:
        try:
            db.table("sold_estimates").upsert(
                item, on_conflict="listing_id"
            ).execute()
            stats["recorded"] += 1
        except Exception:
            pass

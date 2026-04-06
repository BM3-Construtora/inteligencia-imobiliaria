"""Sales tracker — detect removed listings as sold estimates.

Lógica:
- Listing desaparece de todos os portais → deactivated_at setado (normalizer, 7 dias)
- Se reaparece, is_active volta a True (upsert do normalizer)
- Só considera VENDIDO se ficou inativo por 30+ dias sem reaparecer
- Se reativou, remove da tabela sold_estimates (falso positivo)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)

# Só considera vendido após 30 dias inativo
MIN_DAYS_INACTIVE = 30


def run_sales_tracker() -> dict[str, int]:
    """Detect sold listings (inactive 30+ days) and clean false positives."""
    db = get_client()
    stats = {"detected": 0, "recorded": 0, "reactivated": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "sales_tracker", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=MIN_DAYS_INACTIVE)).isoformat()

        # Phase 1: Find listings inativos há 30+ dias — candidatos a venda
        result = (
            db.table("listings")
            .select("id, sale_price, neighborhood, property_type, total_area, "
                    "first_seen_at, deactivated_at, last_seen_at")
            .eq("is_active", False)
            .not_.is_("deactivated_at", "null")
            .not_.is_("sale_price", "null")
            .lt("deactivated_at", cutoff)
            .execute()
        )

        candidates = result.data or []
        stats["detected"] = len(candidates)

        # Check which are already tracked
        existing_ids = set()
        if candidates:
            ids = [d["id"] for d in candidates]
            for i in range(0, len(ids), 200):
                batch_ids = ids[i:i + 200]
                r = (
                    db.table("sold_estimates")
                    .select("listing_id")
                    .in_("listing_id", batch_ids)
                    .execute()
                )
                existing_ids.update(e["listing_id"] for e in (r.data or []))

        # Insert new sold estimates
        batch = []
        for listing in candidates:
            if listing["id"] in existing_ids:
                continue

            dom = _calc_days_on_market(listing)

            batch.append({
                "listing_id": listing["id"],
                "last_price": listing.get("sale_price"),
                "neighborhood": listing.get("neighborhood"),
                "property_type": listing.get("property_type"),
                "total_area": listing.get("total_area"),
                "days_on_market": dom,
            })

            if len(batch) >= 100:
                _flush_inserts(db, batch, stats)
                batch = []

        if batch:
            _flush_inserts(db, batch, stats)

        # Phase 2: Clean false positives — listings that were in sold_estimates
        # but reappeared (is_active = True again)
        stats["reactivated"] = _clean_false_positives(db)

        logger.info(
            f"[sales] Done: {stats['detected']} candidates (30+ days inactive), "
            f"{stats['recorded']} new recorded, "
            f"{stats['reactivated']} false positives removed"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[sales] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _calc_days_on_market(listing: dict) -> int | None:
    """Calculate days on market from first_seen_at to deactivated_at."""
    fs = listing.get("first_seen_at")
    da = listing.get("deactivated_at")
    if not fs or not da:
        return None
    try:
        first = datetime.fromisoformat(str(fs).replace("Z", "+00:00"))
        deact = datetime.fromisoformat(str(da).replace("Z", "+00:00"))
        return max(0, (deact - first).days)
    except (ValueError, TypeError):
        return None


def _clean_false_positives(db: Any) -> int:
    """Remove sold_estimates for listings that reappeared (reactivated)."""
    try:
        # Find sold_estimates where the listing is now active again
        sold = db.table("sold_estimates").select("listing_id").execute()
        if not sold.data:
            return 0

        sold_ids = [s["listing_id"] for s in sold.data]
        reactivated_ids = []

        for i in range(0, len(sold_ids), 200):
            batch_ids = sold_ids[i:i + 200]
            r = (
                db.table("listings")
                .select("id")
                .in_("id", batch_ids)
                .eq("is_active", True)
                .execute()
            )
            reactivated_ids.extend(row["id"] for row in (r.data or []))

        if reactivated_ids:
            for i in range(0, len(reactivated_ids), 200):
                batch = reactivated_ids[i:i + 200]
                db.table("sold_estimates").delete().in_("listing_id", batch).execute()

        return len(reactivated_ids)

    except Exception:
        logger.exception("[sales] Failed to clean false positives")
        return 0


def _flush_inserts(db: Any, batch: list[dict], stats: dict) -> None:
    for item in batch:
        try:
            db.table("sold_estimates").upsert(
                item, on_conflict="listing_id"
            ).execute()
            stats["recorded"] += 1
        except Exception:
            pass


def _finish_run(db: Any, run_id: int | None, status: str, stats: dict,
                error: str | None = None) -> None:
    if not run_id:
        return
    update: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["detected"],
        "items_created": stats["recorded"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

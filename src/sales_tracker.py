"""Sales tracker — detect removed listings as sold estimates.

Lógica:
- Listing desaparece de todos os portais → deactivated_at setado (normalizer, 7 dias)
- Se reaparece, is_active volta a True (upsert do normalizer)
- Só considera VENDIDO se ficou inativo por 30+ dias sem reaparecer
- Se reativou, remove da tabela sold_estimates (falso positivo)

Confidence scoring:
- high: 2+ price drops nos 90d antes da desativação
- medium: 1 price drop ou sources confiáveis sem drops
- low: nenhum drop e fonte de alta-churn (chavesnamao/imovelweb only)
- skipped_churn: chavesnamao/imovelweb only com zero price changes
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from postgrest.exceptions import APIError

from src.db import get_client

logger = logging.getLogger(__name__)

MIN_DAYS_INACTIVE = 30
HIGH_CHURN_SOURCES = {"chavesnamao", "imovelweb"}


def run_sales_tracker() -> dict[str, int]:
    """Detect sold listings (inactive 30+ days) and clean false positives."""
    db = get_client()
    stats: dict[str, int] = {
        "detected": 0,
        "recorded": 0,
        "reactivated": 0,
        "high_conf": 0,
        "medium_conf": 0,
        "low_conf": 0,
        "skipped_churn": 0,
    }

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "sales_tracker", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        has_confidence_cols = _check_confidence_columns(db)
        if not has_confidence_cols:
            logger.warning(
                "[sales] Colunas 'confidence'/'signals' ausentes em sold_estimates. "
                "Inserindo apenas campos legados. Criar migration de follow-up."
            )

        cutoff = (datetime.now(timezone.utc) - timedelta(days=MIN_DAYS_INACTIVE)).isoformat()

        result = (
            db.table("listings")
            .select("id, sale_price, neighborhood, property_type, total_area, source, "
                    "first_seen_at, deactivated_at, last_seen_at")
            .eq("is_active", False)
            .not_.is_("deactivated_at", "null")
            .not_.is_("sale_price", "null")
            .lt("deactivated_at", cutoff)
            .execute()
        )

        candidates = result.data or []
        stats["detected"] = len(candidates)

        existing_ids: set[int] = set()
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

        new_candidates = [c for c in candidates if c["id"] not in existing_ids]
        sources_map = _fetch_sources_per_listing(db, [c["id"] for c in new_candidates])
        price_drops_map = _fetch_price_drops(db, new_candidates)

        batch: list[dict] = []
        for listing in new_candidates:
            sources = sources_map.get(listing["id"], {listing.get("source", "")})
            drops = price_drops_map.get(listing["id"], 0)

            non_churn_sources = sources - HIGH_CHURN_SOURCES
            if not non_churn_sources and drops == 0:
                stats["skipped_churn"] += 1
                continue

            if drops >= 2:
                confidence = "high"
                stats["high_conf"] += 1
            elif drops >= 1 or non_churn_sources:
                confidence = "medium"
                stats["medium_conf"] += 1
            else:
                confidence = "low"
                stats["low_conf"] += 1

            signals = {
                "price_drops_90d": drops,
                "sources": sorted(sources),
                "high_churn_only": not non_churn_sources,
            }

            payload: dict[str, Any] = {
                "listing_id": listing["id"],
                "last_price": listing.get("sale_price"),
                "neighborhood": listing.get("neighborhood"),
                "property_type": listing.get("property_type"),
                "total_area": listing.get("total_area"),
                "days_on_market": _calc_days_on_market(listing),
            }
            if has_confidence_cols:
                payload["confidence"] = confidence
                payload["signals"] = signals

            batch.append(payload)

            if len(batch) >= 100:
                _flush_inserts(db, batch, stats)
                batch = []

        if batch:
            _flush_inserts(db, batch, stats)

        stats["reactivated"] = _clean_false_positives(db)

        logger.info(
            f"[sales] Done: {stats['detected']} candidates, "
            f"{stats['recorded']} recorded "
            f"(high={stats['high_conf']}, med={stats['medium_conf']}, low={stats['low_conf']}, "
            f"skipped_churn={stats['skipped_churn']}), "
            f"{stats['reactivated']} false positives removed"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[sales] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _check_confidence_columns(db: Any) -> bool:
    """Probe sold_estimates to detect if confidence/signals columns exist."""
    try:
        db.table("sold_estimates").select("confidence, signals").limit(1).execute()
        return True
    except APIError:
        return False


def _fetch_sources_per_listing(db: Any, listing_ids: list[int]) -> dict[int, set[str]]:
    """Map canonical listing_id → set of source portals (via canonical_listing_id join)."""
    if not listing_ids:
        return {}
    out: dict[int, set[str]] = {}
    for i in range(0, len(listing_ids), 200):
        batch_ids = listing_ids[i:i + 200]
        try:
            r = (
                db.table("listings")
                .select("id, source")
                .in_("id", batch_ids)
                .execute()
            )
            for row in r.data or []:
                out.setdefault(row["id"], set()).add(row.get("source") or "")
            r2 = (
                db.table("listings")
                .select("canonical_listing_id, source")
                .in_("canonical_listing_id", batch_ids)
                .execute()
            )
            for row in r2.data or []:
                cid = row.get("canonical_listing_id")
                if cid is not None:
                    out.setdefault(cid, set()).add(row.get("source") or "")
        except APIError:
            continue
    return out


def _fetch_price_drops(db: Any, candidates: list[dict]) -> dict[int, int]:
    """Count price-decrease events in the 90 days before deactivation per listing."""
    out: dict[int, int] = {}
    ids = [c["id"] for c in candidates]
    if not ids:
        return out

    deact_map: dict[int, datetime] = {}
    for c in candidates:
        da = c.get("deactivated_at")
        if not da:
            continue
        try:
            deact_map[c["id"]] = datetime.fromisoformat(str(da).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

    for i in range(0, len(ids), 200):
        batch_ids = ids[i:i + 200]
        try:
            r = (
                db.table("price_history")
                .select("listing_id, new_price, detected_at")
                .in_("listing_id", batch_ids)
                .order("detected_at", desc=False)
                .execute()
            )
        except APIError:
            continue

        per_listing: dict[int, list[tuple[datetime, float]]] = {}
        for row in r.data or []:
            lid = row.get("listing_id")
            try:
                ts = datetime.fromisoformat(str(row["detected_at"]).replace("Z", "+00:00"))
                price = float(row["new_price"])
            except (ValueError, TypeError, KeyError):
                continue
            per_listing.setdefault(lid, []).append((ts, price))

        for lid, history in per_listing.items():
            deact = deact_map.get(lid)
            if not deact:
                continue
            window_start = deact - timedelta(days=90)
            drops = 0
            prev_price: float | None = None
            for ts, price in history:
                if ts < window_start or ts > deact:
                    prev_price = price
                    continue
                if prev_price is not None and price < prev_price:
                    drops += 1
                prev_price = price
            out[lid] = drops

    return out


def _calc_days_on_market(listing: dict) -> int | None:
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
    try:
        sold = db.table("sold_estimates").select("listing_id").execute()
        if not sold.data:
            return 0

        sold_ids = [s["listing_id"] for s in sold.data]
        reactivated_ids: list[int] = []

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

    except APIError:
        logger.exception("[sales] Failed to clean false positives")
        return 0


def _flush_inserts(db: Any, batch: list[dict], stats: dict) -> None:
    for item in batch:
        try:
            db.table("sold_estimates").upsert(
                item, on_conflict="listing_id"
            ).execute()
            stats["recorded"] += 1
        except APIError:
            continue


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

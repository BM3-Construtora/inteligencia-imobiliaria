"""Analyst — generates market snapshots and neighborhood aggregates."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

PROPERTY_TYPES = [
    "house", "apartment", "land", "condo_house", "commercial",
    "farm", "rural",
]


def run_analyst() -> dict[str, int]:
    """Generate market snapshots and update neighborhood stats."""
    db = get_client()
    stats = {"snapshots": 0, "neighborhoods": 0}

    # Log agent run
    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "analyst", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # 1. Market snapshots by property_type
        for ptype in PROPERTY_TYPES:
            snapshot = _calc_snapshot(db, ptype, None)
            if snapshot:
                _upsert_snapshot(db, snapshot)
                stats["snapshots"] += 1

        # 2. Market snapshots by property_type + neighborhood (land only for now)
        neighborhoods = _get_active_neighborhoods(db, "land")
        for neigh in neighborhoods:
            snapshot = _calc_snapshot(db, "land", neigh)
            if snapshot:
                _upsert_snapshot(db, snapshot)
                stats["snapshots"] += 1

        # 3. Overall snapshot (all types)
        snapshot = _calc_snapshot(db, None, None)
        if snapshot:
            _upsert_snapshot(db, snapshot)
            stats["snapshots"] += 1

        # 4. Update neighborhood aggregates (batch: 1 big query instead of N×12)
        stats["neighborhoods"] = _update_all_neighborhoods(db)

        logger.info(
            f"[analyst] Done: {stats['snapshots']} snapshots, "
            f"{stats['neighborhoods']} neighborhoods updated"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[analyst] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _get_active_neighborhoods(
    db: Any, property_type: Optional[str]
) -> list[str]:
    """Get list of neighborhoods with active listings."""
    query = (
        db.table("listings")
        .select("neighborhood")
        .eq("is_active", True)
        .is_("canonical_listing_id", "null")
        .not_.is_("neighborhood", "null")
    )
    if property_type:
        query = query.eq("property_type", property_type)

    result = query.execute()
    # Deduplicate
    seen = set()
    neighborhoods = []
    for row in result.data:
        n = row["neighborhood"]
        if n and n not in seen:
            seen.add(n)
            neighborhoods.append(n)
    return neighborhoods


def _calc_snapshot(
    db: Any,
    property_type: Optional[str],
    neighborhood: Optional[str],
) -> Optional[dict[str, Any]]:
    """Calculate aggregate metrics for a given type/neighborhood combo."""
    query = (
        db.table("listings")
        .select("sale_price, total_area, price_per_m2, first_seen_at")
        .eq("is_active", True)
        .is_("canonical_listing_id", "null")
        .not_.is_("sale_price", "null")
        .gt("sale_price", 0)
    )

    if property_type:
        query = query.eq("property_type", property_type)
    if neighborhood:
        query = query.eq("neighborhood", neighborhood)

    result = query.execute()
    rows = result.data

    if not rows:
        return None

    prices = [float(r["sale_price"]) for r in rows if r["sale_price"]]
    areas = [float(r["total_area"]) for r in rows if r.get("total_area")]
    price_m2s = [float(r["price_per_m2"]) for r in rows if r.get("price_per_m2")]

    if not prices:
        return None

    prices.sort()
    n = len(prices)
    median = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2

    # Count new listings (first_seen today)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc)
    new_count = sum(
        1 for r in rows
        if r.get("first_seen_at", "").startswith(today)
    )

    # Calculate average days on market
    days_list = []
    for r in rows:
        fs = r.get("first_seen_at")
        if fs:
            try:
                first = datetime.fromisoformat(fs.replace("Z", "+00:00"))
                days_list.append((now - first).days)
            except (ValueError, TypeError):
                pass
    avg_dom = round(sum(days_list) / len(days_list)) if days_list else None

    return {
        "snapshot_date": today,
        "property_type": property_type,
        "neighborhood": neighborhood,
        "total_listings": n,
        "new_listings": new_count,
        "removed_listings": 0,
        "avg_price": round(sum(prices) / n, 2),
        "median_price": round(median, 2),
        "avg_price_m2": round(sum(price_m2s) / len(price_m2s), 2) if price_m2s else None,
        "min_price": round(min(prices), 2),
        "max_price": round(max(prices), 2),
        "avg_area": round(sum(areas) / len(areas), 2) if areas else None,
        "avg_days_on_market": avg_dom,
    }


def _upsert_snapshot(db: Any, snapshot: dict[str, Any]) -> None:
    """Upsert a market snapshot."""
    db.table("market_snapshots").upsert(
        snapshot,
        on_conflict="snapshot_date,property_type,neighborhood",
    ).execute()


def _update_all_neighborhoods(db: Any) -> int:
    """Update all neighborhood aggregates in bulk (few queries instead of N×12)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)
    thirty_days_ago = (now_dt - timedelta(days=30)).isoformat()

    # 1. Fetch ALL active listings in one query (paginate)
    all_listings: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            db.table("listings")
            .select("neighborhood, property_type, market_tier, price_per_m2, "
                    "latitude, longitude, first_seen_at, is_active")
            .eq("is_active", True)
            .is_("canonical_listing_id", "null")
            .not_.is_("neighborhood", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        all_listings.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size

    # 2. Fetch deactivated listings for absorption
    deactivated: list[dict] = []
    result = (
        db.table("listings")
        .select("neighborhood, deactivated_at, first_seen_at")
        .eq("is_active", False)
        .not_.is_("deactivated_at", "null")
        .not_.is_("neighborhood", "null")
        .gte("deactivated_at", thirty_days_ago)
        .execute()
    )
    deactivated = result.data or []

    # 3. Fetch new listings (last 30 days)
    new_listings: list[dict] = []
    result = (
        db.table("listings")
        .select("neighborhood, first_seen_at")
        .not_.is_("neighborhood", "null")
        .gte("first_seen_at", thirty_days_ago)
        .execute()
    )
    new_listings = result.data or []

    logger.info(f"[analyst] Loaded {len(all_listings)} active, {len(deactivated)} deactivated, {len(new_listings)} new")

    # 4. Aggregate in Python (zero additional queries)
    from collections import defaultdict

    neighs: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "land": 0, "houses": 0,
        "land_prices": [], "house_prices": [], "apt_prices": [],
        "tiers": defaultdict(int),
        "lats": [], "lngs": [],
        "days_on_market": [],
        "removed_30d": 0, "new_30d": 0,
    })

    for l in all_listings:
        n = l["neighborhood"]
        d = neighs[n]
        d["total"] += 1
        ptype = l.get("property_type")
        pm2 = l.get("price_per_m2")

        if ptype == "land":
            d["land"] += 1
            if pm2: d["land_prices"].append(float(pm2))
        elif ptype in ("house", "condo_house"):
            d["houses"] += 1
            if pm2: d["house_prices"].append(float(pm2))
        elif ptype == "apartment":
            if pm2: d["apt_prices"].append(float(pm2))

        tier = l.get("market_tier")
        if tier:
            d["tiers"][tier] += 1

        lat, lng = l.get("latitude"), l.get("longitude")
        if lat and lng:
            d["lats"].append(float(lat))
            d["lngs"].append(float(lng))

        fs = l.get("first_seen_at")
        if fs:
            try:
                first = datetime.fromisoformat(str(fs).replace("Z", "+00:00"))
                d["days_on_market"].append((now_dt - first).days)
            except (ValueError, TypeError):
                pass

    # Count removals and new per neighborhood
    for l in deactivated:
        n = l.get("neighborhood")
        if n:
            neighs[n]["removed_30d"] += 1

    for l in new_listings:
        n = l.get("neighborhood")
        if n:
            neighs[n]["new_30d"] += 1

    # 5. Build upsert batch
    count = 0
    batch: list[dict] = []

    for name, d in neighs.items():
        avg_land = round(sum(d["land_prices"]) / len(d["land_prices"]), 2) if d["land_prices"] else None
        avg_house = round(sum(d["house_prices"]) / len(d["house_prices"]), 2) if d["house_prices"] else None
        avg_apt = round(sum(d["apt_prices"]) / len(d["apt_prices"]), 2) if d["apt_prices"] else None
        avg_dom = round(sum(d["days_on_market"]) / len(d["days_on_market"])) if d["days_on_market"] else None
        lat = round(sum(d["lats"]) / len(d["lats"]), 6) if d["lats"] else None
        lng = round(sum(d["lngs"]) / len(d["lngs"]), 6) if d["lngs"] else None

        total = d["total"]
        removed = d["removed_30d"]
        absorption = round(removed / total * 100, 2) if total > 0 and removed > 0 else None
        months_inv = round(total / removed, 1) if removed > 0 else None

        row: dict[str, Any] = {
            "name": name,
            "avg_price_m2_land": avg_land,
            "avg_price_m2_house": avg_house,
            "avg_price_m2_apt": avg_apt,
            "total_listings": total,
            "total_land": d["land"],
            "total_houses": d["houses"],
            "total_listings_by_tier": dict(d["tiers"]),
            "avg_days_on_market": avg_dom,
            "absorption_rate": absorption,
            "months_of_inventory": months_inv,
            "removed_last_30d": removed,
            "new_last_30d": d["new_30d"],
            "updated_at": now_iso,
        }
        if lat is not None:
            row["latitude"] = lat
            row["longitude"] = lng

        batch.append(row)
        count += 1

        # Flush in batches of 50
        if len(batch) >= 50:
            db.table("neighborhoods").upsert(batch, on_conflict="name").execute()
            batch = []

    if batch:
        db.table("neighborhoods").upsert(batch, on_conflict="name").execute()

    logger.info(f"[analyst] Updated {count} neighborhoods in bulk")
    return count


def _update_neighborhood(db: Any, name: str) -> None:
    """Update aggregate stats for a neighborhood."""
    now = datetime.now(timezone.utc).isoformat()

    def _avg_price_m2(ptype: str) -> Optional[float]:
        result = (
            db.table("listings")
            .select("price_per_m2")
            .eq("is_active", True)
            .eq("neighborhood", name)
            .eq("property_type", ptype)
            .not_.is_("price_per_m2", "null")
            .execute()
        )
        vals = [float(r["price_per_m2"]) for r in result.data if r["price_per_m2"]]
        return round(sum(vals) / len(vals), 2) if vals else None

    # Total counts
    total = (
        db.table("listings")
        .select("id", count="exact")
        .eq("is_active", True)
        .eq("neighborhood", name)
        .execute()
    )
    total_land = (
        db.table("listings")
        .select("id", count="exact")
        .eq("is_active", True)
        .eq("neighborhood", name)
        .eq("property_type", "land")
        .execute()
    )
    total_houses = (
        db.table("listings")
        .select("id", count="exact")
        .eq("is_active", True)
        .eq("neighborhood", name)
        .in_("property_type", ["house", "condo_house"])
        .execute()
    )

    # Tier breakdown
    tier_data = (
        db.table("listings")
        .select("market_tier")
        .eq("is_active", True)
        .eq("neighborhood", name)
        .not_.is_("market_tier", "null")
        .execute()
    )
    tier_counts: dict[str, int] = {}
    for r in tier_data.data:
        t = r["market_tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1

    # Centroid coordinates
    coords = (
        db.table("listings")
        .select("latitude, longitude")
        .eq("is_active", True)
        .eq("neighborhood", name)
        .not_.is_("latitude", "null")
        .not_.is_("longitude", "null")
        .execute()
    )
    lat_avg = None
    lng_avg = None
    if coords.data:
        lats = [float(r["latitude"]) for r in coords.data]
        lngs = [float(r["longitude"]) for r in coords.data]
        lat_avg = round(sum(lats) / len(lats), 6)
        lng_avg = round(sum(lngs) / len(lngs), 6)

    # Absorption: listings removed (sold proxy) and new in last 30 days
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    removed_30d = (
        db.table("listings")
        .select("id", count="exact")
        .eq("is_active", False)
        .eq("neighborhood", name)
        .not_.is_("deactivated_at", "null")
        .gte("deactivated_at", thirty_days_ago)
        .execute()
    )
    new_30d = (
        db.table("listings")
        .select("id", count="exact")
        .eq("neighborhood", name)
        .gte("first_seen_at", thirty_days_ago)
        .execute()
    )

    removed_count = removed_30d.count or 0
    new_count = new_30d.count or 0
    total_count = total.count or 0

    # Absorption rate: % of inventory sold per month
    absorption = round(removed_count / total_count * 100, 2) if total_count > 0 else None
    # Months of inventory: how many months to sell all current stock
    months_inv = round(total_count / removed_count, 1) if removed_count > 0 else None

    # Deal velocity: avg days on market
    dom_data = (
        db.table("listings")
        .select("first_seen_at")
        .eq("is_active", True)
        .eq("neighborhood", name)
        .not_.is_("first_seen_at", "null")
        .execute()
    )
    avg_dom = None
    if dom_data.data:
        now_dt = datetime.now(timezone.utc)
        days_list = []
        for r in dom_data.data:
            try:
                fs = datetime.fromisoformat(str(r["first_seen_at"]).replace("Z", "+00:00"))
                days_list.append((now_dt - fs).days)
            except (ValueError, TypeError):
                pass
        if days_list:
            avg_dom = round(sum(days_list) / len(days_list))

    # Risk aggregation from opportunities
    risk_data = (
        db.table("opportunities")
        .select("score_breakdown, listing:listings!inner(neighborhood)")
        .execute()
    )
    risk_scores = []
    risk_dims: dict[str, list[float]] = {}
    for r in (risk_data.data or []):
        listing = r.get("listing")
        if isinstance(listing, list):
            listing = listing[0] if listing else {}
        if not listing or listing.get("neighborhood") != name:
            continue
        bd = r.get("score_breakdown") or {}
        for dim in ("risco_zoneamento", "risco_ambiental", "risco_infraestrutura", "risco_legal", "risco_mercado"):
            val = bd.get(dim)
            if val is not None:
                risk_dims.setdefault(dim, []).append(float(val))
                risk_scores.append(float(val))

    avg_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else None
    risk_breakdown = {k: round(sum(v) / len(v), 2) for k, v in risk_dims.items()} if risk_dims else {}

    data: dict[str, Any] = {
        "name": name,
        "avg_price_m2_land": _avg_price_m2("land"),
        "avg_price_m2_house": _avg_price_m2("house"),
        "avg_price_m2_apt": _avg_price_m2("apartment"),
        "total_listings": total.count or 0,
        "total_land": total_land.count or 0,
        "total_houses": total_houses.count or 0,
        "total_listings_by_tier": tier_counts,
        "avg_days_on_market": avg_dom,
        "absorption_rate": absorption,
        "months_of_inventory": months_inv,
        "removed_last_30d": removed_count,
        "new_last_30d": new_count,
        "avg_risk_score": avg_risk,
        "risk_breakdown": risk_breakdown,
        "updated_at": now,
    }
    if lat_avg is not None:
        data["latitude"] = lat_avg
        data["longitude"] = lng_avg

    db.table("neighborhoods").upsert(data, on_conflict="name").execute()


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
        "items_processed": stats["snapshots"] + stats["neighborhoods"],
        "items_created": stats["snapshots"],
        "items_updated": stats["neighborhoods"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

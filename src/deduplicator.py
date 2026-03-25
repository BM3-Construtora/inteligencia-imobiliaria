"""Deduplicator — finds duplicate listings across portals."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

# Thresholds
PRICE_TOLERANCE = 0.10  # 10% price difference
AREA_TOLERANCE = 0.15   # 15% area difference
MIN_MATCH_SCORE = 0.60  # Minimum score to record a match


def run_deduplicator() -> dict[str, int]:
    """Find and record duplicate listings across different sources."""
    db = get_client()
    stats = {"compared": 0, "matches": 0, "high_confidence": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "deduplicator", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Fetch all active listings with useful fields (paginate to bypass 1000 limit)
        listings: list[dict] = []
        page_size = 1000
        offset = 0
        while True:
            result = (
                db.table("listings")
                .select("id, source, neighborhood, address, street, sale_price, "
                        "total_area, latitude, longitude, property_type, title")
                .eq("is_active", True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if not result.data:
                break
            listings.extend(result.data)
            if len(result.data) < page_size:
                break
            offset += page_size
        logger.info(f"[dedup] Loaded {len(listings)} active listings")

        # Group by neighborhood for efficiency
        by_neighborhood: dict[str, list[dict]] = {}
        for l in listings:
            n = _normalize_neighborhood(l.get("neighborhood") or "")
            if n:
                by_neighborhood.setdefault(n, []).append(l)

        # Clear existing matches and re-compute
        db.table("listing_matches").delete().neq("id", 0).execute()

        # Compare within each neighborhood
        for neigh, group in by_neighborhood.items():
            if len(group) < 2:
                continue

            # Only compare across different sources
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if a["source"] == b["source"]:
                        continue
                    if a["property_type"] != b["property_type"]:
                        continue

                    stats["compared"] += 1
                    score, method = _compare(a, b)

                    if score >= MIN_MATCH_SCORE:
                        # Ensure a_id < b_id for the CHECK constraint
                        a_id, b_id = sorted([a["id"], b["id"]])
                        try:
                            db.table("listing_matches").insert({
                                "listing_a_id": a_id,
                                "listing_b_id": b_id,
                                "match_score": round(score, 2),
                                "match_method": method,
                            }).execute()
                            stats["matches"] += 1
                            if score >= 0.85:
                                stats["high_confidence"] += 1
                        except Exception:
                            pass  # Skip duplicate constraint violations

        logger.info(
            f"[dedup] Done: {stats['compared']} compared, "
            f"{stats['matches']} matches, "
            f"{stats['high_confidence']} high confidence"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[dedup] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _compare(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, str]:
    """Compare two listings and return (score, method_description)."""
    signals: list[tuple[float, str]] = []

    # 1. Price similarity (weight: 0.30)
    price_a = float(a.get("sale_price") or 0)
    price_b = float(b.get("sale_price") or 0)
    if price_a > 0 and price_b > 0:
        diff = abs(price_a - price_b) / max(price_a, price_b)
        if diff <= PRICE_TOLERANCE:
            signals.append((0.30, "price_match"))
        elif diff <= PRICE_TOLERANCE * 2:
            signals.append((0.15, "price_close"))

    # 2. Area similarity (weight: 0.25)
    area_a = float(a.get("total_area") or 0)
    area_b = float(b.get("total_area") or 0)
    if area_a > 0 and area_b > 0:
        diff = abs(area_a - area_b) / max(area_a, area_b)
        if diff <= 0.02:
            signals.append((0.25, "area_exact"))
        elif diff <= AREA_TOLERANCE:
            signals.append((0.15, "area_close"))

    # 3. Address similarity (weight: 0.25)
    addr_a = _normalize_address(a.get("address") or a.get("street") or "")
    addr_b = _normalize_address(b.get("address") or b.get("street") or "")
    if addr_a and addr_b:
        sim = _string_similarity(addr_a, addr_b)
        if sim >= 0.80:
            signals.append((0.25, "address_match"))
        elif sim >= 0.60:
            signals.append((0.15, "address_similar"))

    # 4. Geographic proximity (weight: 0.20)
    lat_a = a.get("latitude")
    lng_a = a.get("longitude")
    lat_b = b.get("latitude")
    lng_b = b.get("longitude")
    if lat_a and lng_a and lat_b and lng_b:
        dist = _haversine(float(lat_a), float(lng_a), float(lat_b), float(lng_b))
        if dist <= 50:  # 50 meters
            signals.append((0.20, "geo_exact"))
        elif dist <= 200:  # 200 meters
            signals.append((0.10, "geo_close"))

    score = sum(s for s, _ in signals)
    methods = "+".join(m for _, m in signals)
    return score, methods or "no_match"


def _normalize_neighborhood(name: str) -> str:
    """Normalize neighborhood name for comparison."""
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    # Remove common prefixes
    for prefix in ["jardim ", "jd ", "parque ", "pq ", "residencial ", "res ",
                    "nucleo habitacional ", "vila "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def _normalize_address(addr: str) -> str:
    """Normalize address for comparison."""
    addr = addr.lower().strip()
    addr = re.sub(r"[^\w\s]", "", addr)
    addr = re.sub(r"\s+", " ", addr)
    # Remove common prefixes
    for prefix in ["rua ", "r ", "avenida ", "av ", "alameda ", "al ",
                    "travessa ", "tv "]:
        if addr.startswith(prefix):
            addr = addr[len(prefix):]
    return addr


def _string_similarity(a: str, b: str) -> float:
    """Simple bigram similarity (Dice coefficient)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    def bigrams(s: str) -> set[str]:
        return {s[i:i+2] for i in range(len(s) - 1)}

    bg_a = bigrams(a)
    bg_b = bigrams(b)
    if not bg_a or not bg_b:
        return 0.0

    intersection = len(bg_a & bg_b)
    return (2 * intersection) / (len(bg_a) + len(bg_b))


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two points."""
    import math
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
        "items_processed": stats["compared"],
        "items_created": stats["matches"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

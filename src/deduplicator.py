"""Deduplicator — finds duplicate listings across portals with continuous scoring."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.address import address_similarity, normalize_neighborhood
from src.db import get_client

logger = logging.getLogger(__name__)

MIN_MATCH_SCORE = 0.55
HIGH_CONFIDENCE = 0.80
SAME_SOURCE_MIN_SCORE = 0.85  # stricter bar to call two listings from same portal the same property
FINGERPRINT_SCORE = 0.92

_SOURCE_TIEBREAK = {
    "uniao": 4,
    "toca": 3,
    "vivareal": 2,
    "zapimoveis": 2,
    "chavesnamao": 1,
    "imovelweb": 0,
}


def _canonical_priority(listing: dict[str, Any]) -> tuple:
    return (
        listing.get("last_seen_at") or "",
        1 if listing.get("main_image_url") else 0,
        1 if listing.get("description") else 0,
        _SOURCE_TIEBREAK.get(listing.get("source"), 0),
    )


def run_deduplicator() -> dict[str, int]:
    """Find and record duplicate listings across different sources."""
    db = get_client()
    stats: dict[str, int] = {
        "compared": 0,
        "matches": 0,
        "high_confidence": 0,
        "canonical_set": 0,
        "canonical_groups_formed": 0,
        "existing_promotions": 0,
        "comparisons_skipped_by_blocking": 0,
    }

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "deduplicator", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        SELECT_FIELDS = ("id, source, source_id, neighborhood, address, street, number, "
                         "sale_price, total_area, latitude, longitude, "
                         "property_type, bedrooms, bathrooms, title, zip_code, "
                         "built_area, last_seen_at, main_image_url, description, "
                         "listing_fingerprint")
        listings: list[dict] = []
        page_size = 1000
        offset = 0
        while True:
            result = (
                db.table("listings")
                .select(SELECT_FIELDS)
                .eq("is_active", True)
                .is_("canonical_listing_id", "null")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if not result.data:
                break
            listings.extend(result.data)
            if len(result.data) < page_size:
                break
            offset += page_size

        # Also include recently-deactivated listings (last 90 days) that were
        # never deduped — they may match active listings across portals.
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        offset = 0
        inactive_seen: set[int] = {l["id"] for l in listings}
        while True:
            result = (
                db.table("listings")
                .select(SELECT_FIELDS)
                .eq("is_active", False)
                .is_("canonical_listing_id", "null")
                .gte("last_seen_at", ninety_days_ago)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if not result.data:
                break
            for row in result.data:
                if row["id"] not in inactive_seen:
                    listings.append(row)
                    inactive_seen.add(row["id"])
            if len(result.data) < page_size:
                break
            offset += page_size

        logger.info(f"[dedup] Loaded {len(listings)} listings (active + inactive 90d)")

        by_neighborhood: dict[str, list[dict]] = {}
        for l in listings:
            n = normalize_neighborhood(l.get("neighborhood") or "")
            if n:
                by_neighborhood.setdefault(n, []).append(l)

        existing_pairs: set[tuple[int, int]] = set()
        try:
            em_offset = 0
            while True:
                em = (
                    db.table("listing_matches")
                    .select("listing_a_id, listing_b_id")
                    .range(em_offset, em_offset + page_size - 1)
                    .execute()
                )
                if not em.data:
                    break
                for row in em.data:
                    existing_pairs.add((row["listing_a_id"], row["listing_b_id"]))
                if len(em.data) < page_size:
                    break
                em_offset += page_size
        except (KeyError, AttributeError) as e:
            logger.warning(f"[dedup] Failed to preload existing pairs: {e}")

        match_pairs: list[dict] = []
        stats["fingerprint_matches"] = 0

        # Pass 0: deterministic fingerprint match (cheap, runs before scoring).
        # Two listings sharing a non-null fingerprint are almost certainly the
        # same property (same street+number+area bucket). Works across portals
        # AND within the same portal (relistings with new source_id).
        by_fingerprint: dict[str, list[dict]] = {}
        for l in listings:
            fp = l.get("listing_fingerprint")
            if fp:
                by_fingerprint.setdefault(fp, []).append(l)

        for fp, fp_group in by_fingerprint.items():
            if len(fp_group) < 2:
                continue
            # Guard: if fp has empty number (typical for land in loteamentos),
            # do not collapse 4+ same-source listings — likely distinct lots
            # with identical area/price/street rather than a single relisting.
            fp_parts = fp.split("|")
            number_empty = len(fp_parts) >= 3 and not fp_parts[2]
            same_source_counts: dict[str, int] = {}
            if number_empty:
                for x in fp_group:
                    same_source_counts[x["source"]] = same_source_counts.get(x["source"], 0) + 1

            for i, a in enumerate(fp_group):
                for b in fp_group[i + 1:]:
                    if a["property_type"] != b["property_type"]:
                        continue
                    if (
                        number_empty
                        and a["source"] == b["source"]
                        and same_source_counts.get(a["source"], 0) > 3
                    ):
                        stats["fingerprint_guard_skipped"] = stats.get("fingerprint_guard_skipped", 0) + 1
                        continue
                    a_id, b_id = (a["id"], b["id"]) if a["id"] < b["id"] else (b["id"], a["id"])
                    pk = (a_id, b_id)
                    if pk in existing_pairs:
                        continue
                    match_pairs.append({
                        "listing_a_id": a_id,
                        "listing_b_id": b_id,
                        "match_score": FINGERPRINT_SCORE,
                        "match_method": "fingerprint",
                        "decision_rule": "fingerprint",
                        "addr_score": None,
                        "geo_distance_m": None,
                        "price_diff_pct": None,
                        "area_diff_pct": None,
                        "bed_match": None,
                        "bath_match": None,
                    })
                    existing_pairs.add(pk)
                    stats["matches"] += 1
                    stats["high_confidence"] += 1
                    stats["fingerprint_matches"] += 1

        for _, group in by_neighborhood.items():
            if len(group) < 2:
                continue

            buckets: dict[tuple[int, int, Optional[int]], list[dict]] = {}
            for l in group:
                price = float(l.get("sale_price") or 0)
                area = float(l.get("total_area") or 0)
                pb = int(price // 50000) if price > 0 else 0
                ab = int(area // 50) if area > 0 else 0
                bed = l.get("bedrooms")
                buckets.setdefault((pb, ab, bed), []).append(l)

            seen_pairs: set[tuple[int, int]] = set()

            # Pre-compute per-bucket loteamento guard: count same-source, no-number
            # land listings per bucket. If > 3 exist, same-source pairs in that
            # bucket are almost certainly distinct lots (loteamento), not relistings.
            loteamento_sources: dict[tuple, set[str]] = {}
            for (pb, ab, bed), bucket_items in buckets.items():
                src_counts: dict[str, int] = {}
                for x in bucket_items:
                    if (
                        x.get("property_type") == "land"
                        and not _extract_street_number(x.get("address") or x.get("street") or "")
                    ):
                        src_counts[x["source"]] = src_counts.get(x["source"], 0) + 1
                loteamento_sources[(pb, ab, bed)] = {s for s, cnt in src_counts.items() if cnt > 3}

            for (pb, ab, bed), bucket_items in buckets.items():
                # WHY: ±1 neighbors handle items sitting at bucket boundaries.
                neighbors: list[dict] = []
                for dpb in (-1, 0, 1):
                    for dab in (-1, 0, 1):
                        key = (pb + dpb, ab + dab, bed)
                        if key in buckets:
                            neighbors.extend(buckets[key])

                for i, a in enumerate(bucket_items):
                    a_id_raw = a["id"]
                    for b in neighbors:
                        b_id_raw = b["id"]
                        if a_id_raw == b_id_raw:
                            continue
                        pk = (a_id_raw, b_id_raw) if a_id_raw < b_id_raw else (b_id_raw, a_id_raw)
                        if pk in seen_pairs:
                            continue
                        seen_pairs.add(pk)

                        # Same-source comparison is allowed only when source_id
                        # differs — catches relistings of the same property under
                        # a new ad id within the same portal. We hold these to a
                        # stricter score bar below (SAME_SOURCE_MIN_SCORE).
                        same_source = a["source"] == b["source"]
                        if same_source and (a.get("source_id") or "") == (b.get("source_id") or ""):
                            continue
                        if a["property_type"] != b["property_type"]:
                            continue

                        # Loteamento guard: same-source land pairs with no street
                        # numbers in a bucket that has 4+ same-source entries are
                        # almost certainly distinct lots, not relistings.
                        if (
                            same_source
                            and a.get("property_type") == "land"
                            and not _extract_street_number(a.get("address") or a.get("street") or "")
                            and not _extract_street_number(b.get("address") or b.get("street") or "")
                            and a["source"] in loteamento_sources.get((pb, ab, bed), set())
                        ):
                            stats["comparisons_skipped_by_blocking"] = stats.get("comparisons_skipped_by_blocking", 0) + 1
                            continue

                        price_a = float(a.get("sale_price") or 0)
                        price_b = float(b.get("sale_price") or 0)
                        if price_a > 0 and price_b > 0:
                            if max(price_a, price_b) / min(price_a, price_b) > 2.0:
                                stats["comparisons_skipped_by_blocking"] += 1
                                continue
                        area_a = float(a.get("total_area") or 0)
                        area_b = float(b.get("total_area") or 0)
                        if area_a > 0 and area_b > 0:
                            if max(area_a, area_b) / min(area_a, area_b) > 2.0:
                                stats["comparisons_skipped_by_blocking"] += 1
                                continue

                        stats["compared"] += 1
                        cmp_result = _compare(a, b)

                        if cmp_result is None:
                            continue

                        score = cmp_result["match_score"]
                        threshold = SAME_SOURCE_MIN_SCORE if same_source else MIN_MATCH_SCORE
                        if score < threshold:
                            continue

                        a_id, b_id = pk
                        if pk in existing_pairs:
                            continue

                        decision_rule = cmp_result["decision_rule"]
                        payload = {
                            "listing_a_id": a_id,
                            "listing_b_id": b_id,
                            "match_score": round(score, 3),
                            "match_method": decision_rule,
                            "decision_rule": decision_rule,
                            "addr_score": cmp_result["addr_score"],
                            "geo_distance_m": cmp_result["geo_distance_m"],
                            "price_diff_pct": cmp_result["price_diff_pct"],
                            "area_diff_pct": cmp_result["area_diff_pct"],
                            "bed_match": cmp_result["bed_match"],
                            "bath_match": cmp_result["bath_match"],
                        }
                        match_pairs.append(payload)
                        existing_pairs.add(pk)
                        stats["matches"] += 1
                        if score >= HIGH_CONFIDENCE:
                            stats["high_confidence"] += 1

        for i in range(0, len(match_pairs), 100):
            batch = match_pairs[i:i + 100]
            try:
                db.table("listing_matches").insert(batch).execute()
            except Exception as e:
                logger.warning(f"[dedup] Batch insert failed ({e}); retrying one-by-one")
                for m in batch:
                    try:
                        db.table("listing_matches").insert(m).execute()
                    except Exception:
                        pass

        stats["canonical_set"] = _set_canonical_listings(db, match_pairs)
        stats["existing_promotions"] = _promote_existing_canonicals(db)
        stats["canonical_groups_formed"] = _transitive_closure(db)

        logger.info(
            f"[dedup] Done: {stats['compared']} compared, "
            f"{stats['comparisons_skipped_by_blocking']} skipped by blocking, "
            f"{stats['matches']} matches, "
            f"{stats['high_confidence']} high confidence, "
            f"{stats['canonical_set']} canonical set, "
            f"{stats['existing_promotions']} legacy promotions, "
            f"{stats['canonical_groups_formed']} groups"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[dedup] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _compare(a: dict[str, Any], b: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Compare two listings. Returns dict with split signals or None."""
    src_a = a.get("source", "")
    src_b = b.get("source", "")
    sid_a = a.get("source_id") or ""
    sid_b = b.get("source_id") or ""

    if sid_a and sid_b:
        if sid_a == sid_b:
            return {
                "match_score": 1.0,
                "addr_score": None,
                "geo_distance_m": None,
                "price_diff_pct": None,
                "area_diff_pct": None,
                "bed_match": None,
                "bath_match": None,
                "decision_rule": "source_id_match",
            }
        shared_id_portals = {"vivareal", "zapimoveis"}
        if src_a in shared_id_portals and src_b in shared_id_portals:
            return None

    # Different street numbers = definitely different properties.
    # Extract numbers from address fields for a lightweight check.
    num_a = _extract_street_number(a.get("address") or a.get("street") or "")
    num_b = _extract_street_number(b.get("address") or b.get("street") or "")
    if num_a and num_b and num_a != num_b:
        return None

    geo_distance_m: Optional[float] = None
    geo_match = False
    lat_a, lng_a = a.get("latitude"), a.get("longitude")
    lat_b, lng_b = b.get("latitude"), b.get("longitude")
    if lat_a and lng_a and lat_b and lng_b:
        geo_distance_m = round(_haversine(float(lat_a), float(lng_a), float(lat_b), float(lng_b)), 1)
        if geo_distance_m <= 50:
            geo_match = True

    addr_score: Optional[float] = None
    addr_match = False
    addr_a = a.get("address") or a.get("street") or ""
    addr_b = b.get("address") or b.get("street") or ""
    if addr_a and addr_b:
        addr_score = round(address_similarity(addr_a, addr_b), 3)
        if addr_score >= 0.70:
            addr_match = True

    price_diff_pct: Optional[float] = None
    price_match = False
    price_a = float(a.get("sale_price") or 0)
    price_b = float(b.get("sale_price") or 0)
    if price_a > 0 and price_b > 0:
        price_diff_pct = round(abs(price_a - price_b) / max(price_a, price_b), 3)
        if price_diff_pct <= 0.10:
            price_match = True

    area_diff_pct: Optional[float] = None
    area_match = False
    area_a = float(a.get("total_area") or 0)
    area_b = float(b.get("total_area") or 0)
    if area_a > 0 and area_b > 0:
        area_diff_pct = round(abs(area_a - area_b) / max(area_a, area_b), 3)
        if area_diff_pct <= 0.10:
            area_match = True

    bed_a, bed_b = a.get("bedrooms"), b.get("bedrooms")
    bath_a, bath_b = a.get("bathrooms"), b.get("bathrooms")
    bed_match_val: Optional[bool] = None
    bath_match_val: Optional[bool] = None
    if bed_a is not None and bed_b is not None:
        bed_match_val = bed_a == bed_b
    if bath_a is not None and bath_b is not None:
        bath_match_val = bath_a == bath_b
    bed_match = bed_match_val is True
    bath_match = bath_match_val is True
    bed_mismatch = bed_match_val is False
    bath_mismatch = bath_match_val is False

    location_confirmed = addr_match or geo_match
    financials_confirmed = price_match and area_match
    is_land = a.get("property_type") == "land"

    if (bed_mismatch or bath_mismatch) and not (location_confirmed and financials_confirmed):
        return None

    decision_rule: str
    score: float
    if location_confirmed and financials_confirmed:
        score = 0.95
        decision_rule = "loc+financial"
    elif is_land and location_confirmed and price_match:
        # Land has no bed/bath signal; address+price is the strongest available
        score = 0.88 if addr_match else 0.85
        decision_rule = "land_loc+price"
    elif is_land and location_confirmed and area_match:
        score = 0.86 if addr_match else 0.83
        decision_rule = "land_loc+area"
    elif is_land and financials_confirmed:
        tight = (
            (price_diff_pct if price_diff_pct is not None else 1) <= 0.05
            and (area_diff_pct if area_diff_pct is not None else 1) <= 0.05
        )
        score = 0.84 if tight else 0.80
        decision_rule = "land_financial"
    elif location_confirmed and price_match and (bed_match or bath_match):
        score = 0.90
        decision_rule = "loc+price+attrs"
    elif location_confirmed and area_match and (bed_match or bath_match):
        score = 0.88
        decision_rule = "loc+area+attrs"
    elif financials_confirmed and (bed_match or bath_match):
        tight = (
            (price_diff_pct if price_diff_pct is not None else 1) <= 0.05
            and (area_diff_pct if area_diff_pct is not None else 1) <= 0.05
        )
        score = 0.85 if tight else 0.82
        decision_rule = "financial+attrs"
    elif geo_match and (bed_match and bath_match):
        score = 0.80
        decision_rule = "geo_tight+attrs"
    else:
        return None

    if bed_match:
        score = min(1.0, score + 0.02)
    if bath_match:
        score = min(1.0, score + 0.02)

    return {
        "match_score": round(score, 3),
        "addr_score": addr_score,
        "geo_distance_m": geo_distance_m,
        "price_diff_pct": price_diff_pct,
        "area_diff_pct": area_diff_pct,
        "bed_match": bed_match_val,
        "bath_match": bath_match_val,
        "decision_rule": decision_rule,
    }


def _set_canonical_listings(db: Any, match_pairs: list[dict]) -> int:
    """For high-confidence matches in this run, set canonical_listing_id."""
    high_conf = [m for m in match_pairs if m["match_score"] >= HIGH_CONFIDENCE]
    if not high_conf:
        return 0

    ids_needed: set[int] = set()
    for m in high_conf:
        ids_needed.add(m["listing_a_id"])
        ids_needed.add(m["listing_b_id"])

    listing_map = _fetch_listing_map(db, ids_needed)

    count = 0
    for m in high_conf:
        a_id = m["listing_a_id"]
        b_id = m["listing_b_id"]
        if _promote_pair(db, a_id, b_id, listing_map):
            count += 1
    return count


def _promote_existing_canonicals(db: Any) -> int:
    """Iterate ALL high-confidence listing_matches and ensure canonical_listing_id is set."""
    page_size = 1000
    offset = 0
    pairs: list[tuple[int, int]] = []
    while True:
        try:
            res = (
                db.table("listing_matches")
                .select("listing_a_id, listing_b_id, match_score")
                .gte("match_score", HIGH_CONFIDENCE)
                .range(offset, offset + page_size - 1)
                .execute()
            )
        except Exception as e:
            logger.warning(f"[dedup] Failed loading existing matches: {e}")
            break
        if not res.data:
            break
        for row in res.data:
            pairs.append((row["listing_a_id"], row["listing_b_id"]))
        if len(res.data) < page_size:
            break
        offset += page_size

    if not pairs:
        return 0

    ids_needed: set[int] = set()
    for a_id, b_id in pairs:
        ids_needed.add(a_id)
        ids_needed.add(b_id)

    listing_map = _fetch_listing_map(db, ids_needed)
    canonical_map = _fetch_canonical_map(db, ids_needed)

    count = 0
    for a_id, b_id in pairs:
        if canonical_map.get(a_id) is not None and canonical_map.get(b_id) is not None:
            continue
        if _promote_pair(db, a_id, b_id, listing_map, canonical_map):
            count += 1
    return count


def _transitive_closure(db: Any) -> int:
    """Union-find across high-confidence pairs; converge each group on one canonical."""
    page_size = 1000
    offset = 0
    pairs: list[tuple[int, int]] = []
    while True:
        try:
            res = (
                db.table("listing_matches")
                .select("listing_a_id, listing_b_id")
                .gte("match_score", HIGH_CONFIDENCE)
                .range(offset, offset + page_size - 1)
                .execute()
            )
        except Exception as e:
            logger.warning(f"[dedup] Closure load failed: {e}")
            break
        if not res.data:
            break
        for row in res.data:
            pairs.append((row["listing_a_id"], row["listing_b_id"]))
        if len(res.data) < page_size:
            break
        offset += page_size

    if not pairs:
        return 0

    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent.get(x, x), parent.get(x, x))
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    ids_needed: set[int] = set()
    for a_id, b_id in pairs:
        parent.setdefault(a_id, a_id)
        parent.setdefault(b_id, b_id)
        ids_needed.add(a_id)
        ids_needed.add(b_id)
        union(a_id, b_id)

    groups: dict[int, list[int]] = {}
    for node in list(parent.keys()):
        root = find(node)
        groups.setdefault(root, []).append(node)

    groups = {r: members for r, members in groups.items() if len(members) >= 2}
    if not groups:
        return 0

    listing_map = _fetch_listing_map(db, ids_needed)
    canonical_map = _fetch_canonical_map(db, ids_needed)

    formed = 0
    for members in groups.values():
        canonical_id = max(
            members,
            key=lambda lid: (_canonical_priority(listing_map.get(lid, {"id": lid})), -lid),
        )
        for lid in members:
            if lid == canonical_id:
                continue
            current = canonical_map.get(lid)
            if current == canonical_id:
                continue
            try:
                db.table("listings").update(
                    {"canonical_listing_id": canonical_id}
                ).eq("id", lid).execute()
                canonical_map[lid] = canonical_id
            except Exception:
                continue
        formed += 1
    return formed


def _fetch_listing_map(db: Any, ids: set[int]) -> dict[int, dict[str, Any]]:
    listing_map: dict[int, dict[str, Any]] = {}
    id_list = list(ids)
    for i in range(0, len(id_list), 200):
        batch_ids = id_list[i:i + 200]
        try:
            result = (
                db.table("listings")
                .select("id, source, last_seen_at, main_image_url, description")
                .in_("id", batch_ids)
                .execute()
            )
            for r in result.data or []:
                listing_map[r["id"]] = r
        except Exception:
            continue
    return listing_map


def _fetch_canonical_map(db: Any, ids: set[int]) -> dict[int, Optional[int]]:
    cmap: dict[int, Optional[int]] = {}
    id_list = list(ids)
    for i in range(0, len(id_list), 200):
        batch_ids = id_list[i:i + 200]
        try:
            result = (
                db.table("listings")
                .select("id, canonical_listing_id")
                .in_("id", batch_ids)
                .execute()
            )
            for r in result.data or []:
                cmap[r["id"]] = r.get("canonical_listing_id")
        except Exception:
            continue
    return cmap


def _promote_pair(
    db: Any,
    a_id: int,
    b_id: int,
    listing_map: dict[int, dict[str, Any]],
    canonical_map: Optional[dict[int, Optional[int]]] = None,
) -> bool:
    la = listing_map.get(a_id, {"id": a_id})
    lb = listing_map.get(b_id, {"id": b_id})
    prio_a = _canonical_priority(la)
    prio_b = _canonical_priority(lb)

    if prio_a > prio_b or (prio_a == prio_b and a_id < b_id):
        canonical_id, duplicate_id = a_id, b_id
    else:
        canonical_id, duplicate_id = b_id, a_id

    if canonical_map is not None and canonical_map.get(duplicate_id) == canonical_id:
        return False

    try:
        db.table("listings").update(
            {"canonical_listing_id": canonical_id}
        ).eq("id", duplicate_id).is_("canonical_listing_id", "null").execute()
        if canonical_map is not None:
            canonical_map[duplicate_id] = canonical_id
        return True
    except Exception:
        return False


def _extract_street_number(address: str) -> str | None:
    """Return the first numeric token from an address string that looks like a
    street number (1–6 digits, optionally followed by a letter suffix).
    Returns None when the address has no parseable number.
    """
    import re
    m = re.search(r"\b(\d{1,6}[a-zA-Z]?)\b", address)
    return m.group(1).lower() if m else None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
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
    update: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["compared"],
        "items_created": stats["matches"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

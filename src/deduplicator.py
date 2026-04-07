"""Deduplicator — finds duplicate listings across portals with continuous scoring."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from src.address import normalize_address, address_similarity, normalize_neighborhood
from src.db import get_client

logger = logging.getLogger(__name__)

# Thresholds — scores are normalized by max achievable weight,
# so 0.55 means "55% of available evidence matches".
MIN_MATCH_SCORE = 0.55  # Record match (on normalized scale)
HIGH_CONFIDENCE = 0.80  # Auto-merge candidate

# Source priority for canonical selection (higher = preferred)
SOURCE_PRIORITY = {
    "uniao": 5,
    "toca": 4,
    "vivareal": 3,
    "zapimoveis": 3,
    "imovelweb": 2,
    "chavesnamao": 1,
}


def run_deduplicator() -> dict[str, int]:
    """Find and record duplicate listings across different sources."""
    db = get_client()
    stats = {"compared": 0, "matches": 0, "high_confidence": 0, "canonical_set": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "deduplicator", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Fetch all active listings with useful fields (paginate)
        listings: list[dict] = []
        page_size = 1000
        offset = 0
        while True:
            result = (
                db.table("listings")
                .select("id, source, source_id, neighborhood, address, street, number, "
                        "sale_price, total_area, latitude, longitude, "
                        "property_type, bedrooms, bathrooms, title, zip_code, "
                        "built_area")
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
        logger.info(f"[dedup] Loaded {len(listings)} active listings")

        # Group by normalized neighborhood
        by_neighborhood: dict[str, list[dict]] = {}
        for l in listings:
            n = normalize_neighborhood(l.get("neighborhood") or "")
            if n:
                by_neighborhood.setdefault(n, []).append(l)

        # Note: we no longer wipe listing_matches on each run.
        # Instead we skip pairs that already have a match recorded.
        existing_pairs: set[tuple[int, int]] = set()
        try:
            em = db.table("listing_matches").select("listing_a_id, listing_b_id").execute()
            for row in (em.data or []):
                existing_pairs.add((row["listing_a_id"], row["listing_b_id"]))
        except Exception:
            pass

        # Compare within each neighborhood
        match_pairs: list[dict] = []
        for neigh, group in by_neighborhood.items():
            if len(group) < 2:
                continue

            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if a["source"] == b["source"]:
                        continue
                    if a["property_type"] != b["property_type"]:
                        continue

                    stats["compared"] += 1
                    score, method = _compare(a, b)

                    if score >= MIN_MATCH_SCORE:
                        a_id, b_id = sorted([a["id"], b["id"]])
                        pair_key = (a_id, b_id)
                        if pair_key in existing_pairs:
                            continue  # Already recorded
                        match_pairs.append({
                            "listing_a_id": a_id,
                            "listing_b_id": b_id,
                            "match_score": round(score, 3),
                            "match_method": method,
                        })
                        existing_pairs.add(pair_key)
                        stats["matches"] += 1
                        if score >= HIGH_CONFIDENCE:
                            stats["high_confidence"] += 1

        # Batch insert matches
        for i in range(0, len(match_pairs), 100):
            batch = match_pairs[i:i + 100]
            try:
                db.table("listing_matches").insert(batch).execute()
            except Exception:
                # Insert one by one to skip constraint violations
                for m in batch:
                    try:
                        db.table("listing_matches").insert(m).execute()
                    except Exception:
                        pass

        # Set canonical listings for high-confidence matches
        stats["canonical_set"] = _set_canonical_listings(db, match_pairs)

        logger.info(
            f"[dedup] Done: {stats['compared']} compared, "
            f"{stats['matches']} matches, "
            f"{stats['high_confidence']} high confidence, "
            f"{stats['canonical_set']} canonical set"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[dedup] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _clean_tokens(text: str) -> set[str]:
    """Extract meaningful tokens from a listing title, stripping noise."""
    import re
    from src.address import remove_accents
    # Lowercase, remove accents, strip non-alphanumeric (except spaces)
    text = re.sub(r"[^\w\s]", " ", remove_accents(text.lower()))
    tokens = set(text.split())
    # Remove stopwords AND portal-generic format tokens that cause false positives
    stop = {
        "de", "do", "da", "dos", "das", "em", "no", "na", "com", "e", "a", "o",
        "para", "por", "um", "uma", "venda", "aluguel", "marilia", "sp",
        "comprar", "alugar", "quartos", "quarto", "banheiros", "banheiro",
        "vagas", "vaga", "suites", "suite", "m2", "m",
        "casa", "apartamento", "terreno", "comercial", "sobrado", "kitnet",
        "imovel", "lote", "area", "chacara", "sitio", "galpao", "sala",
        "condominio", "residencial", "residencia",
    }
    tokens -= stop
    # Remove pure numbers (area values, room counts)
    tokens = {t for t in tokens if not t.isdigit()}
    return tokens


def _title_similarity(a: str, b: str) -> float:
    """Token-based Jaccard similarity between two titles."""
    if not a or not b:
        return 0.0
    tokens_a = _clean_tokens(a)
    tokens_b = _clean_tokens(b)
    if len(tokens_a) < 2 or len(tokens_b) < 2:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _compare(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, str]:
    """Compare two listings. Returns (score, method).

    Strategy:
    - source_id match = definitive (vivareal↔zapimoveis share IDs)
    - source_id MISMATCH between vivareal↔zapimoveis = definitive NOT a match
    - For other pairs: require address/geo match OR (price AND area) match.
      Title/bed/bath alone are NEVER enough — too many similar listings per neighborhood.
    """
    src_a = a.get("source", "")
    src_b = b.get("source", "")
    sid_a = a.get("source_id") or ""
    sid_b = b.get("source_id") or ""

    # --- Definitive: source_id match/mismatch ---
    if sid_a and sid_b:
        if sid_a == sid_b:
            return 1.0, "source_id_match"
        # Same portal family with different IDs = different listings
        shared_id_portals = {"vivareal", "zapimoveis"}
        if src_a in shared_id_portals and src_b in shared_id_portals:
            return 0.0, "source_id_mismatch"

    # --- Collect identity signals (things that identify a SPECIFIC property) ---
    methods: list[str] = []

    # 1. Geographic proximity
    geo_match = False
    lat_a, lng_a = a.get("latitude"), a.get("longitude")
    lat_b, lng_b = b.get("latitude"), b.get("longitude")
    if lat_a and lng_a and lat_b and lng_b:
        dist = _haversine(float(lat_a), float(lng_a), float(lat_b), float(lng_b))
        if dist <= 50:
            geo_match = True
            methods.append(f"geo_{int(dist)}m")

    # 2. Address match
    addr_match = False
    addr_a = a.get("address") or a.get("street") or ""
    addr_b = b.get("address") or b.get("street") or ""
    if addr_a and addr_b:
        sim = address_similarity(addr_a, addr_b)
        if sim >= 0.70:
            addr_match = True
            methods.append(f"addr_{sim:.0%}")

    # 3. Price similarity
    price_match = False
    price_a = float(a.get("sale_price") or 0)
    price_b = float(b.get("sale_price") or 0)
    price_diff = None
    if price_a > 0 and price_b > 0:
        price_diff = abs(price_a - price_b) / max(price_a, price_b)
        if price_diff <= 0.10:
            price_match = True
            methods.append(f"price_{price_diff:.0%}")

    # 4. Area similarity
    area_match = False
    area_a = float(a.get("total_area") or 0)
    area_b = float(b.get("total_area") or 0)
    area_diff = None
    if area_a > 0 and area_b > 0:
        area_diff = abs(area_a - area_b) / max(area_a, area_b)
        if area_diff <= 0.10:
            area_match = True
            methods.append(f"area_{area_diff:.0%}")

    # --- Bed/bath signals (used in decision logic below) ---
    bed_a, bed_b = a.get("bedrooms"), b.get("bedrooms")
    bath_a, bath_b = a.get("bathrooms"), b.get("bathrooms")
    bed_match = bed_a is not None and bed_b is not None and bed_a == bed_b
    bath_match = bath_a is not None and bath_b is not None and bath_a == bath_b
    bed_mismatch = (bed_a is not None and bed_b is not None and bed_a != bed_b)
    bath_mismatch = (bath_a is not None and bath_b is not None and bath_a != bath_b)

    # --- Decision: require strong cross-domain evidence ---
    # Same street ≠ same property (many units per street/building).
    # Need LOCATION + FINANCIAL confirmation. Bed/bath mismatch vetoes weak matches.
    location_confirmed = addr_match or geo_match
    financials_confirmed = price_match and area_match

    if (bed_mismatch or bath_mismatch) and not (location_confirmed and financials_confirmed):
        # Different bedroom/bathroom count = almost certainly different property
        # unless BOTH location AND financials match perfectly
        return 0.0, "bed_bath_mismatch"

    if location_confirmed and financials_confirmed:
        score = 0.95
    elif location_confirmed and price_match and (bed_match or bath_match):
        # Location + price + bed/bath = strong
        score = 0.90
    elif location_confirmed and area_match and (bed_match or bath_match):
        # Location + area + bed/bath = decent
        score = 0.88
    elif financials_confirmed and (bed_match or bath_match):
        # Price+area match with bed/bath but no location
        tight = (price_diff if price_diff is not None else 1) <= 0.05 and (area_diff if area_diff is not None else 1) <= 0.05
        score = 0.85 if tight else 0.82
    elif geo_match and (bed_match and bath_match):
        # Geo < 50m with matching bed AND bath
        score = 0.80
    else:
        return 0.0, "insufficient_evidence"

    # Small bonus for bed/bath match
    if bed_match:
        score = min(1.0, score + 0.02)
        methods.append("bed")
    if bath_match:
        score = min(1.0, score + 0.02)
        methods.append("bath")

    return round(score, 3), "+".join(methods)


def _set_canonical_listings(db: Any, match_pairs: list[dict]) -> int:
    """For high-confidence matches, set canonical_listing_id on the inferior listing."""
    high_conf = [m for m in match_pairs if m["match_score"] >= HIGH_CONFIDENCE]
    if not high_conf:
        return 0

    # Collect all listing IDs involved
    ids_needed = set()
    for m in high_conf:
        ids_needed.add(m["listing_a_id"])
        ids_needed.add(m["listing_b_id"])

    # Batch fetch source info (avoid N+1)
    source_map: dict[int, str] = {}
    id_list = list(ids_needed)
    for i in range(0, len(id_list), 200):
        batch_ids = id_list[i:i + 200]
        try:
            result = db.table("listings").select("id, source").in_("id", batch_ids).execute()
            for r in result.data:
                source_map[r["id"]] = r["source"]
        except Exception:
            pass

    count = 0
    for m in high_conf:
        a_id = m["listing_a_id"]
        b_id = m["listing_b_id"]
        src_a = source_map.get(a_id, "")
        src_b = source_map.get(b_id, "")
        prio_a = SOURCE_PRIORITY.get(src_a, 0)
        prio_b = SOURCE_PRIORITY.get(src_b, 0)

        # Higher priority = canonical. On tie, lower ID wins.
        if prio_a >= prio_b:
            canonical_id, duplicate_id = a_id, b_id
        else:
            canonical_id, duplicate_id = b_id, a_id

        try:
            db.table("listings").update(
                {"canonical_listing_id": canonical_id}
            ).eq("id", duplicate_id).is_("canonical_listing_id", "null").execute()
            count += 1
        except Exception:
            pass

    return count


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two points."""
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

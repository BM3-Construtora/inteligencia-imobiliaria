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
                .select("id, source, neighborhood, address, street, number, "
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
    """Compare two listings with continuous scoring. Returns (score, method).

    Scores are normalized by max achievable weight so that listings with
    sparse data (no address, no coords) can still be matched when the
    available signals (price, area, title) strongly agree.
    """
    signals: list[tuple[float, float, str]] = []  # (score, weight, method)

    # 1. Geographic proximity (weight: 0.25)
    lat_a, lng_a = a.get("latitude"), a.get("longitude")
    lat_b, lng_b = b.get("latitude"), b.get("longitude")
    if lat_a and lng_a and lat_b and lng_b:
        dist = _haversine(float(lat_a), float(lng_a), float(lat_b), float(lng_b))
        geo_score = max(0, 1.0 - dist / 200) if dist <= 200 else 0.0
        signals.append((geo_score, 0.25, f"geo_{int(dist)}m"))

    # 2. Address similarity (weight: 0.20)
    addr_a = a.get("address") or a.get("street") or ""
    addr_b = b.get("address") or b.get("street") or ""
    if addr_a and addr_b:
        sim = address_similarity(addr_a, addr_b)
        signals.append((sim if sim >= 0.3 else 0.0, 0.20, f"addr_{sim:.0%}"))

    # 2b. ZIP code bonus (weight: 0.05)
    zip_a = a.get("zip_code")
    zip_b = b.get("zip_code")
    if zip_a and zip_b:
        signals.append((1.0 if zip_a == zip_b else 0.0, 0.05, "zip"))

    # 3. Price similarity (weight: 0.25)
    price_a = float(a.get("sale_price") or 0)
    price_b = float(b.get("sale_price") or 0)
    if price_a > 0 and price_b > 0:
        diff = abs(price_a - price_b) / max(price_a, price_b)
        price_score = max(0, 1.0 - diff / 0.20) if diff <= 0.20 else 0.0
        signals.append((price_score, 0.25, f"price_{diff:.0%}"))

    # 4. Area similarity (weight: 0.15)
    area_a = float(a.get("total_area") or 0)
    area_b = float(b.get("total_area") or 0)
    if area_a > 0 and area_b > 0:
        diff = abs(area_a - area_b) / max(area_a, area_b)
        area_score = max(0, 1.0 - diff / 0.15) if diff <= 0.15 else 0.0
        signals.append((area_score, 0.15, f"area_{diff:.0%}"))

    # 5. Bedrooms/bathrooms match (weight: 0.05 each)
    bed_a = a.get("bedrooms")
    bed_b = b.get("bedrooms")
    if bed_a is not None and bed_b is not None:
        signals.append((1.0 if bed_a == bed_b else 0.0, 0.05, "bed"))
    bath_a = a.get("bathrooms")
    bath_b = b.get("bathrooms")
    if bath_a is not None and bath_b is not None:
        signals.append((1.0 if bath_a == bath_b else 0.0, 0.05, "bath"))

    # 6. Title similarity (weight: 0.15) — critical when address/geo are missing
    title_a = a.get("title") or ""
    title_b = b.get("title") or ""
    if title_a and title_b:
        tsim = _title_similarity(title_a, title_b)
        signals.append((tsim if tsim >= 0.25 else 0.0, 0.15, f"title_{tsim:.0%}"))

    if not signals:
        return 0.0, "no_signals"

    # Normalize: score = weighted_sum / total_weight_of_available_signals
    total_weight = sum(w for _, w, _ in signals)
    if total_weight == 0:
        return 0.0, "no_weight"
    raw_score = sum(s * w for s, w, _ in signals)
    normalized = raw_score / total_weight

    methods = "+".join(m for s, _, m in signals if s > 0)
    return round(normalized, 3), methods or "no_match"


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

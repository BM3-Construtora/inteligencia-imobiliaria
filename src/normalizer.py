"""Normalizer — transforms raw_listings into listings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.area_parser import extract_area
from src.db import get_client
from src.fingerprint import compute_fingerprint

logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # Keep small to avoid Supabase statement timeout (8s on free tier)

# ============================================================
# Type mapping
# ============================================================

TOCA_TYPE_MAP = {
    # Residencial
    "Apartamento": "apartment",
    "Casa": "house",
    "Fora De Condomínio": "house",
    "Dentro De Condomínio": "condo_house",
    "Casa Em Condomínio": "condo_house",
    # Terrenos
    "Área": "land",
    "Terreno": "land",
    "Terreno em Condomínio": "land",
    # Comercial
    "Comercial": "commercial",
    "Sala Comercial": "commercial",
    "Sala Em Condomínio": "commercial",
    "Sala": "commercial",
    "Barracão": "commercial",
    "Galpãobarracão": "commercial",
    "Lojasalão": "commercial",
    "Loja Em Shopping": "commercial",
    "Prédio Comercial": "commercial",
    "Prédio De Apartamentos": "commercial",
    "Misto": "commercial",
    # Rural
    "Chácara": "farm",
    "Chácara Em Condomínio": "farm",
    "Sítio": "rural",
    "Sítiofazenda": "rural",
    "Fazenda": "rural",
}

UNIAO_TYPE_MAP = {
    "apartment": "apartment",
    "house": "house",
    "land": "land",
    "commercial": "commercial",
    "rural": "rural",
    "condo_house": "condo_house",
    "farm": "farm",
}


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _calc_price_per_m2(
    price: Optional[float], area: Optional[float]
) -> Optional[float]:
    if price and area and area > 0:
        result = round(price / area, 2)
        # Sanity check: R$0.01-50000/m² is plausible for Marília
        # Anything outside this range is likely bad data
        if result < 0.01 or result > 50000:
            return None
        return result
    return None


def _validate_area(area: Optional[float]) -> Optional[float]:
    """Discard implausible area values."""
    if area is None:
        return None
    if area <= 15:
        return None  # Likely parsing artifact (e.g., "12m²" placeholder)
    if area > 10_000_000:
        return None  # > 10km², clearly wrong
    return area


def _apply_area_fallback(n: dict[str, Any]) -> None:
    """Fill total_area from title/description when source didn't provide it.

    Mutates n in place. Recomputes price_per_m2 if a value was filled.
    Restricted to property_type='land' to avoid over-claiming areas for houses
    where "350m²" in the title usually means built area, not total.
    """
    if n.get("total_area") or n.get("property_type") != "land":
        return
    area = extract_area(n.get("title")) or extract_area(n.get("description"))
    if not area:
        return
    n["total_area"] = area
    n["area_inferred"] = True
    price = n.get("sale_price") or n.get("rent_price")
    if price and area:
        n["price_per_m2"] = _calc_price_per_m2(price, area)


ACCEPTED_CITIES = {"marilia", "marília"}


def _normalize_city_key(city: Optional[str]) -> str:
    if not city:
        return ""
    return (
        city.strip()
        .lower()
        .replace("í", "i")
        .replace("?", "i")
    )


def _is_marilia(city: Optional[str]) -> bool:
    key = _normalize_city_key(city)
    if not key:
        return False
    return key in {"marilia"} or "marilia" in key


def _log_quality(
    db: Any,
    raw_id: Optional[int],
    source: Optional[str],
    source_id: Optional[str],
    severity: str,
    rule: str,
    details: dict[str, Any],
) -> None:
    try:
        db.table("data_quality_log").insert({
            "raw_listing_id": raw_id,
            "source": source,
            "source_id": source_id,
            "severity": severity,
            "rule": rule,
            "details": details,
        }).execute()
    except Exception:
        logger.warning(f"[normalizer] Failed to log quality issue {rule} for {source}:{source_id}")


def _validate_listing(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Apply semantic validations. Returns None to reject, or dict (possibly quarantined)."""
    ptype = data.get("property_type")
    price = _safe_float(data.get("sale_price"))
    total = _safe_float(data.get("total_area"))
    built = _safe_float(data.get("built_area"))

    if built and total and built > total:
        data["built_area"], data["total_area"] = total, built
        total = data["total_area"]
        data["price_per_m2"] = _calc_price_per_m2(price, total)

    if ptype == "apartment" and data.get("bedrooms") == 0:
        data["bedrooms"] = None

    if price is None and total is None:
        return None

    residential = ptype in ("house", "apartment", "condo_house")
    rural = ptype in ("farm", "rural")
    ppm2 = _safe_float(data.get("price_per_m2"))

    quarantine_reason: Optional[str] = None
    details: dict[str, Any] = {"price": price, "area": total}

    if residential and price is not None and price < 30_000:
        quarantine_reason = "price_too_low"
    elif price is not None and price > 50_000_000:
        quarantine_reason = "price_too_high"
    elif total is not None and total > 0 and ppm2 is not None and ppm2 < 300:
        quarantine_reason = "ppm2_too_low"
    elif ppm2 is not None and ppm2 > 30_000:
        quarantine_reason = "ppm2_too_high"
    elif not rural and total is not None and total > 50_000:
        quarantine_reason = "area_implausible"

    if quarantine_reason:
        data["quarantined"] = True
        data["quarantine_reason"] = quarantine_reason
        data["_quarantine_details"] = details
    else:
        data["quarantined"] = False
        data["quarantine_reason"] = None

    return data


# ============================================================
# União normalizer
# ============================================================

def normalize_uniao(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw União (DreamKeys) listing."""
    prop_type = UNIAO_TYPE_MAP.get(raw.get("type", ""), "other")
    sale_price = _safe_float(raw.get("salePrice"))
    rent_price = _safe_float(raw.get("rentPrice"))
    total_area = _validate_area(_safe_float(raw.get("totalArea")))
    built_area = _safe_float(raw.get("builtArea"))

    # Business type
    if sale_price and rent_price:
        biz = "both"
    elif rent_price:
        biz = "rent"
    else:
        biz = "sale"

    # Main image
    main_img = raw.get("mainImage", {})
    main_image_url = main_img.get("url") if isinstance(main_img, dict) else None

    # Images list
    images = [
        img.get("url") for img in (raw.get("images") or []) if img.get("url")
    ]

    # Features
    features = raw.get("features") or []

    code = raw.get("code")
    url = f"https://www.imobiliariauniao.com.br/imovel/{code}" if code else None

    return {
        "source": "uniao",
        "source_id": raw["id"],
        "url": url,
        "property_type": prop_type,
        "business_type": biz,
        "title": raw.get("title"),
        "address": raw.get("address"),
        "street": raw.get("street"),
        "number": raw.get("number"),
        "complement": raw.get("complement") or None,
        "neighborhood": raw.get("neighborhood"),
        "city": raw.get("city", "Marília"),
        "state": raw.get("state", "SP"),
        "zip_code": raw.get("zipCode"),
        "latitude": _safe_float(raw.get("latitude")),
        "longitude": _safe_float(raw.get("longitude")),
        "sale_price": sale_price,
        "rent_price": rent_price,
        "condominium_fee": _safe_float(raw.get("condominiumFee")),
        "iptu": _safe_float(raw.get("iptu")),
        "price_per_m2": _calc_price_per_m2(sale_price or rent_price, total_area),
        "total_area": total_area,
        "built_area": built_area,
        "bedrooms": _safe_int(raw.get("bedrooms")),
        "bathrooms": _safe_int(raw.get("bathrooms")),
        "suites": None,
        "parking_spaces": _safe_int(raw.get("parkingSpaces")),
        "description": raw.get("description"),
        "features": features,
        "is_featured": raw.get("isFeatured", False),
        "is_active": raw.get("isActive", True),
        "main_image_url": main_image_url,
        "images": images,
    }


# ============================================================
# Toca normalizer
# ============================================================

def normalize_toca(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw Toca listing."""
    tipo = raw.get("tipo_imovel", "")
    prop_type = TOCA_TYPE_MAP.get(tipo, "other")

    sale_price = _safe_float(raw.get("valor"))
    rent_price = _safe_float(raw.get("valor_aluguel"))
    total_area = _validate_area(_safe_float(raw.get("a_terreno")))
    built_area = _safe_float(raw.get("a_construida"))

    # Business type
    flag_ven = raw.get("flag_mostra_site_ven") == 1
    flag_loc = raw.get("flag_mostra_site_loc") == 1
    if flag_ven and flag_loc:
        biz = "both"
    elif flag_loc:
        biz = "rent"
    else:
        biz = "sale"

    # Main image
    main_image_url = raw.get("foto_thumb")

    # Images list
    fotos = raw.get("imovel_fotos") or []
    images = []
    for f in fotos:
        url = f.get("foto_OK") or f.get("_public_url_backup")
        if url:
            images.append(url)

    # Features (characteristics array)
    features = raw.get("caracteristicas") or []

    return {
        "source": "toca",
        "source_id": str(raw["id"]),
        "url": None,
        "property_type": prop_type,
        "business_type": biz,
        "title": raw.get("titulo"),
        "address": raw.get("endereco"),
        "street": None,
        "number": None,
        "complement": None,
        "neighborhood": raw.get("bairro_nome"),
        "city": raw.get("cidade", "Marília"),
        "state": "SP",
        "zip_code": None,
        "latitude": _safe_float(raw.get("lati")),
        "longitude": _safe_float(raw.get("longi")),
        "sale_price": sale_price,
        "rent_price": rent_price,
        "condominium_fee": None,
        "iptu": None,
        "price_per_m2": _calc_price_per_m2(sale_price or rent_price, total_area),
        "total_area": total_area,
        "built_area": built_area,
        "bedrooms": _safe_int(raw.get("dormitorios")),
        "bathrooms": _safe_int(raw.get("banheiros")),
        "suites": _safe_int(raw.get("suites")),
        "parking_spaces": _safe_int(raw.get("garagem")),
        "description": raw.get("descricao"),
        "features": features,
        "is_featured": raw.get("destaque") == "1" or raw.get("destaque_venda") == "1",
        "is_active": True,
        "main_image_url": main_image_url,
        "images": images,
    }


# ============================================================
# HTML scrapers normalizer (VivaReal, Chaves na Mão, Imovelweb)
# ============================================================

def normalize_html_scraper(source: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw listing from any HTML scraper.

    All three HTML scrapers (vivareal, chavesnamao, imovelweb) produce
    a similar flat dict with: id, url, name/title, type, price, area,
    bedrooms, bathrooms, parking, neighborhood, city, state, images/image_url.
    """
    prop_type = raw.get("type", "other")
    if prop_type not in (
        "house", "apartment", "land", "commercial", "rural",
        "condo_house", "farm", "other",
    ):
        prop_type = "other"

    sale_price = _safe_float(raw.get("price"))
    total_area = _validate_area(_safe_float(raw.get("area")))

    # Images
    images = raw.get("images", [])
    main_image_url = raw.get("image_url")
    if not main_image_url and images:
        main_image_url = images[0]

    return {
        "source": source,
        "source_id": str(raw["id"]),
        "url": raw.get("url"),
        "property_type": prop_type,
        "business_type": "sale",
        "title": raw.get("name") or raw.get("title"),
        "address": raw.get("street"),
        "street": raw.get("street"),
        "number": None,
        "complement": None,
        "neighborhood": raw.get("neighborhood"),
        "city": raw.get("city", "Marília"),
        "state": raw.get("state", "SP"),
        "zip_code": None,
        "latitude": None,
        "longitude": None,
        "sale_price": sale_price,
        "rent_price": None,
        "condominium_fee": None,
        "iptu": None,
        "price_per_m2": _calc_price_per_m2(sale_price, total_area),
        "total_area": total_area,
        "built_area": None,
        "bedrooms": _safe_int(raw.get("bedrooms")),
        "bathrooms": _safe_int(raw.get("bathrooms")),
        "suites": None,
        "parking_spaces": _safe_int(raw.get("parking")),
        "description": raw.get("description", ""),
        "features": [],
        "is_featured": False,
        "is_active": True,
        "main_image_url": main_image_url,
        "images": images if images else ([main_image_url] if main_image_url else []),
    }


def normalize_vivareal(raw: dict[str, Any]) -> dict[str, Any]:
    return normalize_html_scraper("vivareal", raw)


def normalize_chavesnamao(raw: dict[str, Any]) -> dict[str, Any]:
    return normalize_html_scraper("chavesnamao", raw)


def normalize_imovelweb(raw: dict[str, Any]) -> dict[str, Any]:
    return normalize_html_scraper("imovelweb", raw)


def normalize_zapimoveis(raw: dict[str, Any]) -> dict[str, Any]:
    return normalize_html_scraper("zapimoveis", raw)


# ============================================================
# Dispatcher
# ============================================================

NORMALIZERS = {
    "uniao": normalize_uniao,
    "toca": normalize_toca,
    "vivareal": normalize_vivareal,
    "chavesnamao": normalize_chavesnamao,
    "imovelweb": normalize_imovelweb,
    "zapimoveis": normalize_zapimoveis,
}


# ============================================================
# Main normalization pipeline
# ============================================================

def run_normalizer() -> dict[str, int]:
    """Process all unprocessed raw_listings and upsert into listings.

    Optimized for speed: batch upserts instead of per-item requests.
    ~2 API calls per batch of 100 (instead of 3 per item).
    """
    db = get_client()
    stats = {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "failed": 0,
        "price_changes": 0,
    }

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "normalizer", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        while True:
            batch = (
                db.table("raw_listings")
                .select("id, source, source_id, raw_data")
                .eq("processed", False)
                .order("collected_at")
                .limit(BATCH_SIZE)
                .execute()
            )

            if not batch.data:
                break

            logger.info(
                f"[normalizer] Processing batch of {len(batch.data)} "
                f"(total so far: {stats['processed']})"
            )

            # Phase 1: Normalize all items in memory (no API calls)
            normalized_batch = []
            raw_ids = []
            processed_raw_ids: list[int] = []
            now = datetime.now(timezone.utc).isoformat()

            for raw_row in batch.data:
                try:
                    source = raw_row["source"]
                    raw_id = raw_row["id"]
                    src_id = raw_row.get("source_id")
                    normalizer_fn = NORMALIZERS.get(source)
                    if not normalizer_fn:
                        stats["failed"] += 1
                        continue

                    normalized = normalizer_fn(raw_row["raw_data"])
                    _apply_area_fallback(normalized)
                    fp = compute_fingerprint(normalized)
                    if fp:
                        normalized["listing_fingerprint"] = fp

                    if not _is_marilia(normalized.get("city")):
                        _log_quality(
                            db, raw_id, source, src_id, "reject", "wrong_city",
                            {"city": normalized.get("city")},
                        )
                        processed_raw_ids.append(raw_id)
                        continue

                    validated = _validate_listing(normalized)
                    if validated is None:
                        _log_quality(
                            db, raw_id, source, src_id, "reject", "missing_price_and_area",
                            {"price": normalized.get("sale_price"), "area": normalized.get("total_area")},
                        )
                        processed_raw_ids.append(raw_id)
                        continue

                    if validated.get("quarantined"):
                        q_details = validated.pop("_quarantine_details", {})
                        _log_quality(
                            db, raw_id, source, src_id, "quarantine",
                            validated["quarantine_reason"], q_details,
                        )

                    validated["last_seen_at"] = now
                    validated["updated_at"] = now

                    normalized_batch.append(validated)
                    raw_ids.append(raw_id)

                except Exception:
                    stats["failed"] += 1
                    logger.exception(
                        f"[normalizer] Failed to normalize "
                        f"{raw_row.get('source')}:{raw_row.get('source_id')}"
                    )

            # Mark rejected raw_listings as processed too (don't reprocess)
            if processed_raw_ids:
                try:
                    db.table("raw_listings").update({
                        "processed": True,
                    }).in_("id", processed_raw_ids).execute()
                except Exception:
                    logger.exception("[normalizer] Failed to mark rejected as processed")

            if not normalized_batch:
                if stats["failed"] > 0 and not processed_raw_ids:
                    break
                continue

            # Phase 1b: Batched lookup grouped by source (collapses N queries → ~6)
            existing_map: dict[str, dict] = {}
            by_source: dict[str, list[str]] = {}
            for n in normalized_batch:
                by_source.setdefault(n["source"], []).append(n["source_id"])

            for source, ids_for_source in by_source.items():
                try:
                    r = (
                        db.table("listings")
                        .select("id, source, source_id, first_seen_at, sale_price")
                        .eq("source", source)
                        .in_("source_id", ids_for_source)
                        .execute()
                    )
                    for row in r.data or []:
                        existing_map[f"{row['source']}:{row['source_id']}"] = row
                except Exception:
                    logger.exception(f"[normalizer] Lookup failed for source {source}")

            # Set first_seen_at: preserve for existing, set NOW for new
            for normalized in normalized_batch:
                key = f"{normalized['source']}:{normalized['source_id']}"
                existing = existing_map.get(key)
                if existing:
                    normalized["first_seen_at"] = existing["first_seen_at"]
                    # Detect price changes
                    _detect_price_change(
                        db, existing, normalized, stats
                    )
                else:
                    normalized["first_seen_at"] = now

            # Phase 2: Batch upsert listings (1 API call for entire batch)
            try:
                result = (
                    db.table("listings")
                    .upsert(normalized_batch, on_conflict="source,source_id")
                    .execute()
                )
                stats["processed"] += len(normalized_batch)
                stats["created"] += len(result.data) if result.data else 0
            except Exception:
                logger.exception("[normalizer] Batch upsert failed")
                stats["failed"] += len(normalized_batch)
                continue

            # Phase 3: Batch mark raw_listings as processed (1 API call)
            try:
                db.table("raw_listings").update({
                    "processed": True,
                }).in_("id", raw_ids).execute()
            except Exception:
                logger.exception("[normalizer] Failed to mark batch as processed")

        # Phase 4: Deactivate stale listings (not seen in 7+ days)
        stale_result = _deactivate_stale_listings(db)
        stats["deactivated"] = stale_result.get("deactivated", 0)
        stats["siblings_kept_alive"] = stale_result.get("siblings_kept_alive", 0)
        if stats["deactivated"] > 0 or stats["siblings_kept_alive"] > 0:
            logger.info(
                f"[normalizer] Deactivated {stats['deactivated']} stale listings, "
                f"kept {stats['siblings_kept_alive']} alive via canonical siblings"
            )

        logger.info(
            f"[normalizer] Done: {stats['processed']} processed, "
            f"{stats['created']} created, {stats['updated']} updated, "
            f"{stats['price_changes']} price changes, {stats['failed']} failed, "
            f"{stats.get('deactivated', 0)} deactivated, "
            f"{stats.get('siblings_kept_alive', 0)} siblings kept alive"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _detect_price_change(
    db: Any,
    old: dict[str, Any],
    new: dict[str, Any],
    stats: dict[str, int],
) -> None:
    """Record a price change if sale_price changed."""
    old_price = _safe_float(old.get("sale_price"))
    new_price = _safe_float(new.get("sale_price"))

    if old_price is None or new_price is None:
        return
    if old_price == new_price:
        return
    if old_price <= 0:
        return

    change_pct = round(((new_price - old_price) / old_price) * 100, 2)

    # Absurd deltas (>2000% jump or <-95% crash) indicate bad data, not real edits.
    # Skip recording — quarantine path will catch the underlying outlier.
    if change_pct > 2000 or change_pct < -95:
        logger.warning(
            f"[normalizer] Skipped implausible price change on listing {old['id']}: "
            f"{old_price} → {new_price} ({change_pct:+.1f}%)"
        )
        return

    record: dict[str, Any] = {
        "listing_id": old["id"],
        "old_price": old_price,
        "new_price": new_price,
        "change_pct": change_pct,
    }
    # Add source if column exists (migration 012)
    if new.get("source"):
        record["source"] = new["source"]

    try:
        db.table("price_history").insert(record).execute()
    except Exception:
        # source column may not exist yet
        db.table("price_history").insert({
            "listing_id": old["id"],
            "old_price": old_price,
            "new_price": new_price,
            "change_pct": change_pct,
        }).execute()

    stats["price_changes"] += 1
    logger.info(
        f"[normalizer] Price change detected for listing {old['id']}: "
        f"{old_price} → {new_price} ({change_pct:+.1f}%)"
    )


def _deactivate_stale_listings(db: Any) -> dict[str, int]:
    """Deactivate listings not seen in last 7 days, respecting canonical siblings.

    A listing only gets deactivated when no sibling (same canonical_listing_id,
    or pointing to it) has been seen within the cutoff. If a sibling is alive,
    the stale listing's last_seen_at is bumped to the sibling's max and it stays
    active — prevents false-positive "sold" signals when one portal drops the ad
    but another keeps it live.
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    now = datetime.now(timezone.utc).isoformat()

    result_stats = {"deactivated": 0, "siblings_kept_alive": 0}

    try:
        # 1. Fetch candidates that would be deactivated
        stale_resp = (
            db.table("listings")
            .select("id, canonical_listing_id, last_seen_at")
            .eq("is_active", True)
            .lt("last_seen_at", cutoff)
            .execute()
        )
        stale = stale_resp.data or []
        if not stale:
            return result_stats

        # 2. Collect all canonical_ids in play (own id if it IS the canonical,
        #    or canonical_listing_id if it points elsewhere)
        canonical_ids: set[Any] = set()
        for row in stale:
            cid = row.get("canonical_listing_id") or row["id"]
            canonical_ids.add(cid)

        # 3. Fetch the freshest last_seen_at across the canonical family.
        #    A family member is any listing whose id ∈ canonical_ids OR
        #    whose canonical_listing_id ∈ canonical_ids.
        family_rows: list[dict] = []
        canonical_list = list(canonical_ids)
        CHUNK = 200
        for i in range(0, len(canonical_list), CHUNK):
            chunk = canonical_list[i:i + CHUNK]
            try:
                by_id = (
                    db.table("listings")
                    .select("id, canonical_listing_id, last_seen_at, is_active")
                    .in_("id", chunk)
                    .execute()
                )
                family_rows.extend(by_id.data or [])
            except Exception:
                logger.exception("[normalizer] Failed family lookup by id")
            try:
                by_canon = (
                    db.table("listings")
                    .select("id, canonical_listing_id, last_seen_at, is_active")
                    .in_("canonical_listing_id", chunk)
                    .execute()
                )
                family_rows.extend(by_canon.data or [])
            except Exception:
                logger.exception("[normalizer] Failed family lookup by canonical_listing_id")

        # 4. Build canonical_id → max(last_seen_at)
        max_seen: dict[Any, str] = {}
        for row in family_rows:
            cid = row.get("canonical_listing_id") or row["id"]
            ls = row.get("last_seen_at")
            if not ls:
                continue
            cur = max_seen.get(cid)
            if cur is None or ls > cur:
                max_seen[cid] = ls

        # 5. Partition stale candidates
        to_deactivate: list[Any] = []
        to_bump: list[tuple[Any, str]] = []
        for row in stale:
            cid = row.get("canonical_listing_id") or row["id"]
            fresh = max_seen.get(cid)
            if fresh and fresh >= cutoff:
                to_bump.append((row["id"], fresh))
            else:
                to_deactivate.append(row["id"])

        # 6. Deactivate the truly stale
        if to_deactivate:
            for i in range(0, len(to_deactivate), 500):
                chunk = to_deactivate[i:i + 500]
                try:
                    upd = (
                        db.table("listings")
                        .update({"is_active": False, "deactivated_at": now})
                        .in_("id", chunk)
                        .execute()
                    )
                    result_stats["deactivated"] += len(upd.data) if upd.data else len(chunk)
                except Exception:
                    logger.exception("[normalizer] Failed to deactivate stale chunk")

        # 7. Bump last_seen_at for siblings-alive cases.
        #    Group by target timestamp to minimize round trips.
        if to_bump:
            by_ts: dict[str, list[Any]] = {}
            for lid, ts in to_bump:
                by_ts.setdefault(ts, []).append(lid)
            for ts, ids in by_ts.items():
                for i in range(0, len(ids), 500):
                    chunk = ids[i:i + 500]
                    try:
                        db.table("listings").update(
                            {"last_seen_at": ts}
                        ).in_("id", chunk).execute()
                        result_stats["siblings_kept_alive"] += len(chunk)
                    except Exception:
                        logger.exception("[normalizer] Failed to bump sibling-alive chunk")

        return result_stats
    except Exception:
        logger.exception("[normalizer] Failed to deactivate stale listings")
        return result_stats


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
        "items_processed": stats["processed"],
        "items_created": stats["created"],
        "items_updated": stats["updated"],
        "items_failed": stats["failed"],
        "metadata": {
            "price_changes": stats["price_changes"],
            "deactivated": stats.get("deactivated", 0),
            "siblings_kept_alive": stats.get("siblings_kept_alive", 0),
        },
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

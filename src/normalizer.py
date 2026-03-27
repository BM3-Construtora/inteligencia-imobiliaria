"""Normalizer — transforms raw_listings into listings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

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


def _validate_listing(data: dict[str, Any]) -> dict[str, Any]:
    """Apply semantic validations and fix inconsistencies."""
    ptype = data.get("property_type")
    price = data.get("sale_price")
    total = data.get("total_area")
    built = data.get("built_area")

    # built_area > total_area is impossible — swap or discard
    if built and total and built > total:
        data["built_area"], data["total_area"] = total, built
        data["price_per_m2"] = _calc_price_per_m2(price, data["total_area"])

    # Suspiciously low prices for residential
    if price is not None and price < 1000 and ptype in ("house", "apartment", "condo_house"):
        data["sale_price"] = None
        data["price_per_m2"] = None

    # Bedrooms = 0 for apartment is likely missing data, not studio
    if ptype == "apartment" and data.get("bedrooms") == 0:
        data["bedrooms"] = None

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

    return {
        "source": "uniao",
        "source_id": raw["id"],
        "url": None,  # DreamKeys doesn't expose public URLs
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
        "is_mcmv": raw.get("isAvailableForMCMV", False),
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
        "is_mcmv": False,
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
        "is_mcmv": False,
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
            now = datetime.now(timezone.utc).isoformat()

            for raw_row in batch.data:
                try:
                    source = raw_row["source"]
                    normalizer_fn = NORMALIZERS.get(source)
                    if not normalizer_fn:
                        stats["failed"] += 1
                        continue

                    normalized = normalizer_fn(raw_row["raw_data"])
                    normalized = _validate_listing(normalized)
                    normalized["last_seen_at"] = now
                    normalized["updated_at"] = now
                    normalized["first_seen_at"] = now

                    normalized_batch.append(normalized)
                    raw_ids.append(raw_row["id"])

                except Exception:
                    stats["failed"] += 1
                    logger.exception(
                        f"[normalizer] Failed to normalize "
                        f"{raw_row.get('source')}:{raw_row.get('source_id')}"
                    )

            if not normalized_batch:
                if stats["failed"] > 0:
                    break
                continue

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
        stale_count = _deactivate_stale_listings(db)
        stats["deactivated"] = stale_count
        if stale_count > 0:
            logger.info(f"[normalizer] Deactivated {stale_count} stale listings")

        logger.info(
            f"[normalizer] Done: {stats['processed']} processed, "
            f"{stats['created']} created, {stats['updated']} updated, "
            f"{stats['price_changes']} price changes, {stats['failed']} failed, "
            f"{stats.get('deactivated', 0)} deactivated"
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

    change_pct = round(((new_price - old_price) / old_price) * 100, 2)

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


def _deactivate_stale_listings(db: Any) -> int:
    """Deactivate listings not seen in last 7 days (proxy: removed from portal = sold)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    now = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            db.table("listings")
            .update({"is_active": False, "deactivated_at": now})
            .eq("is_active", True)
            .lt("last_seen_at", cutoff)
            .execute()
        )
        return len(result.data) if result.data else 0
    except Exception:
        logger.exception("[normalizer] Failed to deactivate stale listings")
        return 0


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
        "metadata": {"price_changes": stats["price_changes"]},
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

"""Enricher — geocodes listings with cache-first strategy + Nominatim fallback."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "MariliaBot/1.0 (inteligencia-imobiliaria)"}
REQUEST_DELAY = 1.1  # Nominatim: max 1 req/sec

OPENCAGE_URL = "https://api.opencagedata.com/geocode/v1/json"
# Set OPENCAGE_API_KEY in .env to use OpenCage (2500 req/day free) before Nominatim
MARILIA_LAT = -22.21
MARILIA_LNG = -49.95
MAX_DISTANCE_KM = 50.0
VIEWBOX = "-50.0,-22.4,-49.8,-22.1"
NOISE_VALUES = {"endereço indisponível", "endereco indisponivel", "não informado",
                "nao informado", "0", "-", "", "marília", "marilia"}
MAX_ATTEMPTS = 3
BACKOFF = [2, 4, 8]
TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


def run_enricher() -> dict[str, int]:
    db = get_client()
    max_items = int(os.getenv("ENRICHER_MAX_ITEMS", "5000"))
    stats = {
        "processed": 0, "geocoded": 0, "failed": 0, "skipped": 0,
        "cache_hits": 0, "cache_misses": 0,
        "precise_matches": 0, "neighborhood_matches": 0, "city_fallback": 0,
    }

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "enricher", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        listings = _fetch_listings(db, max_items)
        logger.info(f"[enricher] Found {len(listings)} listings without coordinates (cap={max_items})")

        to_geocode = [
            l for l in listings
            if l.get("address") or l.get("street") or l.get("neighborhood")
        ]
        logger.info(f"[enricher] {len(to_geocode)} have address info to geocode")

        for listing in to_geocode:
            stats["processed"] += 1
            candidates = _build_candidates(listing)

            if not candidates:
                stats["skipped"] += 1
                continue

            result = _geocode_with_candidates(db, candidates, stats)

            if result:
                lat, lng, tier = result
                db.table("listings").update({
                    "latitude": lat,
                    "longitude": lng,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", listing["id"]).execute()
                stats["geocoded"] += 1
                stats[f"{tier}_matches" if tier != "city_fallback" else "city_fallback"] += 1
                logger.debug(f"[enricher] Geocoded #{listing['id']} ({tier}): {lat},{lng}")
            else:
                stats["failed"] += 1

            if stats["processed"] % 50 == 0:
                total_lookups = stats["cache_hits"] + stats["cache_misses"]
                pct = (stats["cache_hits"] / total_lookups * 100) if total_lookups else 0
                logger.info(
                    f"[enricher] Progress: {stats['processed']}/{len(to_geocode)} "
                    f"({stats['geocoded']} geocoded, cache {pct:.0f}%)"
                )

        total_lookups = stats["cache_hits"] + stats["cache_misses"]
        pct = (stats["cache_hits"] / total_lookups * 100) if total_lookups else 0
        logger.info(f"[enricher] cache hits: {stats['cache_hits']}/{total_lookups} ({pct:.1f}%)")
        logger.info(
            f"[enricher] Done: processed={stats['processed']} geocoded={stats['geocoded']} "
            f"failed={stats['failed']} skipped={stats['skipped']} "
            f"precise={stats['precise_matches']} neigh={stats['neighborhood_matches']} "
            f"city={stats['city_fallback']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[enricher] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _fetch_listings(db: Any, max_items: int) -> list[dict]:
    listings: list[dict] = []
    page_size = 1000
    offset = 0
    while len(listings) < max_items:
        result = (
            db.table("listings")
            .select("id, address, street, number, neighborhood, city, state, zip_code")
            .eq("is_active", True)
            .is_("latitude", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        listings.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return listings[:max_items]


def _normalize(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.lower().strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def _hash_query(query: str) -> str:
    return hashlib.sha256(_normalize(query).encode("utf-8")).hexdigest()


def _clean(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip()
    if _normalize(v) in NOISE_VALUES:
        return None
    return v


def _build_candidates(listing: dict[str, Any]) -> list[tuple[str, str]]:
    """Return list of (tier, query) ordered by precision."""
    street = _clean(listing.get("street") or listing.get("address"))
    number = _clean(str(listing.get("number") or ""))
    neigh = _clean(listing.get("neighborhood"))
    city = _clean(listing.get("city")) or "Marília"
    state = _clean(listing.get("state")) or "SP"

    out: list[tuple[str, str]] = []

    if street and neigh:
        head = f"{street} {number}".strip() if number else street
        out.append(("precise", f"{head}, {neigh}, {city}, {state}, Brasil"))

    if street:
        head = f"{street} {number}".strip() if number else street
        out.append(("precise", f"{head}, {city}, {state}, Brasil"))

    if neigh:
        out.append(("neighborhood", f"{neigh}, {city}, {state}, Brasil"))

    # Skip city centroid: collapses everything onto Marília center, which
    # falsely satisfies geo_match in the deduplicator. Only geocode when we
    # have street- or neighborhood-level signal.
    return out


def _geocode_with_candidates(
    db: Any, candidates: list[tuple[str, str]], stats: dict[str, int]
) -> Optional[tuple[float, float, str]]:
    opencage_key = os.getenv("OPENCAGE_API_KEY")
    for tier, query in candidates:
        coords = _lookup_cache(db, query, stats)
        if coords:
            return coords[0], coords[1], tier

        if opencage_key:
            coords = _opencage_request(query, opencage_key)
            provider = "opencage"
        else:
            coords = _nominatim_request(query)
            provider = "nominatim"

        if coords:
            _store_cache(db, query, coords, provider)
            return coords[0], coords[1], tier
    return None


def _lookup_cache(
    db: Any, query: str, stats: dict[str, int]
) -> Optional[tuple[float, float]]:
    qhash = _hash_query(query)
    result = (
        db.table("geocode_cache")
        .select("latitude, longitude, hit_count")
        .eq("query_hash", qhash)
        .limit(1)
        .execute()
    )
    if result.data:
        row = result.data[0]
        stats["cache_hits"] += 1
        db.table("geocode_cache").update({
            "hit_count": (row.get("hit_count") or 0) + 1,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }).eq("query_hash", qhash).execute()
        return float(row["latitude"]), float(row["longitude"])
    stats["cache_misses"] += 1
    return None


def _store_cache(
    db: Any, query: str, coords: tuple[float, float], provider: str
) -> None:
    qhash = _hash_query(query)
    now = datetime.now(timezone.utc).isoformat()
    db.table("geocode_cache").upsert({
        "query_hash": qhash,
        "query_text": query[:500],
        "latitude": coords[0],
        "longitude": coords[1],
        "provider": provider,
        "hit_count": 1,
        "last_used_at": now,
        "created_at": now,
    }, on_conflict="query_hash").execute()


def _opencage_request(query: str, api_key: str) -> Optional[tuple[float, float]]:
    params = {
        "q": query,
        "key": api_key,
        "limit": 1,
        "countrycode": "br",
        "language": "pt",
        "no_annotations": 1,
    }
    try:
        resp = httpx.get(OPENCAGE_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return None
        geom = results[0]["geometry"]
        lat, lon = float(geom["lat"]), float(geom["lng"])
        if _haversine(lat, lon, MARILIA_LAT, MARILIA_LNG) > MAX_DISTANCE_KM:
            logger.debug(f"[enricher] OpenCage far result discarded: {query}")
            return None
        return lat, lon
    except Exception as e:
        logger.debug(f"[enricher] OpenCage error: {e}")
        return None


def _nominatim_request(query: str) -> Optional[tuple[float, float]]:
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "br",
        "viewbox": VIEWBOX,
        "bounded": "0",
    }
    for attempt in range(MAX_ATTEMPTS):
        time.sleep(REQUEST_DELAY)
        try:
            resp = httpx.get(
                NOMINATIM_URL, params=params,
                headers=NOMINATIM_HEADERS, timeout=TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json()
            if not results:
                return None
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            if _haversine(lat, lon, MARILIA_LAT, MARILIA_LNG) > MAX_DISTANCE_KM:
                logger.debug(f"[enricher] Discarded far result for: {query}")
                return None
            return lat, lon
        except httpx.TimeoutException:
            logger.debug(f"[enricher] timeout attempt {attempt+1} for: {query}")
        except httpx.HTTPError as e:
            logger.debug(f"[enricher] http error attempt {attempt+1}: {e}")
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF[attempt])
    return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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
        "items_created": stats["geocoded"],
        "items_failed": stats["failed"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

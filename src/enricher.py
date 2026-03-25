"""Enricher — geocodes listings without coordinates using Nominatim (OSM)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "MariliaBot/1.0 (inteligencia-imobiliaria)"}
BATCH_SIZE = 50
REQUEST_DELAY = 1.1  # Nominatim requires max 1 req/sec


def run_enricher() -> dict[str, int]:
    """Geocode listings that have address but no coordinates."""
    db = get_client()
    stats = {"processed": 0, "geocoded": 0, "failed": 0, "skipped": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "enricher", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Fetch listings without coordinates (paginate to bypass 1000 limit)
        listings: list[dict] = []
        page_size = 1000
        offset = 0
        while True:
            result = (
                db.table("listings")
                .select("id, address, street, neighborhood, city, state, zip_code")
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
        logger.info(f"[enricher] Found {len(listings)} listings without coordinates")

        # Filter to only those with enough address info
        to_geocode = [
            l for l in listings
            if l.get("address") or l.get("street") or l.get("neighborhood")
        ]
        logger.info(f"[enricher] {len(to_geocode)} have address info to geocode")

        for listing in to_geocode:
            stats["processed"] += 1
            query = _build_query(listing)

            if not query:
                stats["skipped"] += 1
                continue

            coords = _geocode(query)

            if coords:
                lat, lng = coords
                db.table("listings").update({
                    "latitude": lat,
                    "longitude": lng,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", listing["id"]).execute()
                stats["geocoded"] += 1
                logger.debug(
                    f"[enricher] Geocoded #{listing['id']}: {query} → {lat},{lng}"
                )
            else:
                stats["failed"] += 1

            if stats["processed"] % 50 == 0:
                logger.info(
                    f"[enricher] Progress: {stats['processed']}/{len(to_geocode)} "
                    f"({stats['geocoded']} geocoded)"
                )

        logger.info(
            f"[enricher] Done: {stats['processed']} processed, "
            f"{stats['geocoded']} geocoded, "
            f"{stats['failed']} failed, "
            f"{stats['skipped']} skipped"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[enricher] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _build_query(listing: dict[str, Any]) -> Optional[str]:
    """Build a geocoding query string from listing address fields."""
    parts = []

    # Street address
    addr = listing.get("address") or listing.get("street")
    if addr and addr.lower() not in ("endereço indisponível", "não informado"):
        parts.append(addr)

    # Neighborhood
    neigh = listing.get("neighborhood")
    if neigh:
        parts.append(neigh)

    # City + State
    city = listing.get("city", "Marília")
    state = listing.get("state", "SP")
    parts.append(f"{city}, {state}")

    # Need at least neighborhood + city
    if len(parts) < 2:
        return None

    return ", ".join(parts)


def _geocode(query: str) -> Optional[tuple[float, float]]:
    """Geocode an address using Nominatim. Returns (lat, lng) or None."""
    time.sleep(REQUEST_DELAY)

    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "br",
            },
            headers=NOMINATIM_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()

        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            return lat, lon

    except Exception:
        logger.debug(f"[enricher] Geocoding failed for: {query}", exc_info=True)

    # Fallback: try with just neighborhood + city
    parts = query.split(",")
    if len(parts) > 2:
        fallback = ", ".join(parts[-2:]).strip()
        time.sleep(REQUEST_DELAY)
        try:
            resp = httpx.get(
                NOMINATIM_URL,
                params={
                    "q": fallback,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "br",
                },
                headers=NOMINATIM_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception:
            pass

    return None


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

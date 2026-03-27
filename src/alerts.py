"""Alerts — match new listings against saved searches and notify."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)


def run_alerts() -> dict[str, int]:
    """Check saved searches against recent listings and send notifications."""
    db = get_client()
    stats = {"searches": 0, "matches": 0, "notified": 0}

    # Get active saved searches
    result = db.table("saved_searches").select("*").eq("is_active", True).execute()
    searches = result.data or []
    stats["searches"] = len(searches)

    if not searches:
        logger.info("[alerts] No active saved searches")
        return stats

    # Get listings from last 24h
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent = (
        db.table("listings")
        .select("id, source, property_type, neighborhood, sale_price, "
                "total_area, market_tier, title, url, is_mcmv")
        .eq("is_active", True)
        .gte("first_seen_at", yesterday)
        .execute()
    )
    new_listings = recent.data or []
    logger.info(f"[alerts] {len(new_listings)} new listings in last 24h")

    if not new_listings:
        return stats

    for search in searches:
        criteria = search.get("criteria", {})
        matches = _match_listings(new_listings, criteria)

        if not matches:
            continue

        stats["matches"] += len(matches)

        # Send Telegram notification
        if search.get("notify_telegram"):
            sent = _send_alert(search, matches)
            if sent:
                stats["notified"] += len(matches)
                # Update last_notified
                db.table("saved_searches").update(
                    {"last_notified": datetime.now(timezone.utc).isoformat()}
                ).eq("id", search["id"]).execute()

    logger.info(
        f"[alerts] Done: {stats['searches']} searches, "
        f"{stats['matches']} matches, {stats['notified']} notified"
    )
    return stats


def _match_listings(listings: list[dict], criteria: dict) -> list[dict]:
    """Filter listings that match the saved search criteria."""
    matches = []
    for l in listings:
        if not _listing_matches(l, criteria):
            continue
        matches.append(l)
    return matches


def _listing_matches(listing: dict, criteria: dict) -> bool:
    """Check if a single listing matches all criteria."""
    # Property type filter
    ptypes = criteria.get("property_type", [])
    if ptypes and listing.get("property_type") not in ptypes:
        return False

    # Neighborhood filter
    neighborhoods = criteria.get("neighborhoods", [])
    if neighborhoods and listing.get("neighborhood") not in neighborhoods:
        return False

    # Market tier filter
    tiers = criteria.get("market_tier", [])
    if tiers and listing.get("market_tier") not in tiers:
        return False

    # Price range
    price = float(listing.get("sale_price") or 0)
    if criteria.get("price_min") and price < criteria["price_min"]:
        return False
    if criteria.get("price_max") and price > criteria["price_max"]:
        return False

    # Area range
    area = float(listing.get("total_area") or 0)
    if criteria.get("area_min") and area < criteria["area_min"]:
        return False
    if criteria.get("area_max") and area > criteria["area_max"]:
        return False

    # MCMV filter
    if criteria.get("is_mcmv") is not None:
        if listing.get("is_mcmv") != criteria["is_mcmv"]:
            return False

    return True


def _send_alert(search: dict, matches: list[dict]) -> bool:
    """Send alert via Telegram."""
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("[alerts] No Telegram credentials configured")
        return False

    name = search.get("name", "Busca")
    lines = [f"🔔 Alerta: {name} — {len(matches)} novo(s) imovel(is)\n"]

    for m in matches[:5]:
        price = float(m.get("sale_price") or 0)
        area = float(m.get("total_area") or 0)
        neigh = m.get("neighborhood", "?")
        tier = m.get("market_tier", "")
        url = m.get("url", "")

        lines.append(
            f"• {neigh} — R${price:,.0f} | {area:.0f}m²"
            + (f" | {tier}" if tier else "")
            + (f"\n  {url}" if url else "")
        )

    if len(matches) > 5:
        lines.append(f"\n... e mais {len(matches) - 5} imovel(is)")

    text = "\n".join(lines)

    try:
        import httpx
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        logger.exception("[alerts] Failed to send Telegram alert")
        return False

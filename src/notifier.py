"""Notifier — sends Telegram alerts for top opportunities."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org/bot{token}"

MIN_SCORE_NOTIFY = float(os.getenv("MIN_SCORE_NOTIFY", "70"))


def run_notifier() -> dict[str, int]:
    """Send Telegram alerts for unnotified opportunities with score >= threshold."""
    db = get_client()
    stats = {"checked": 0, "notified": 0, "failed": 0}

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("[notifier] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return stats

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "notifier", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Fetch unnotified opportunities above threshold
        result = (
            db.table("opportunities")
            .select(
                "id, listing_id, score, score_breakdown, reason, "
                "listing:listings(id, source, title, neighborhood, address, "
                "sale_price, total_area, price_per_m2, bedrooms, is_mcmv, "
                "main_image_url, url, latitude, longitude)"
            )
            .eq("is_notified", False)
            .gte("score", MIN_SCORE_NOTIFY)
            .order("score", desc=True)
            .limit(10)
            .execute()
        )

        opportunities = result.data
        stats["checked"] = len(opportunities)
        logger.info(f"[notifier] Found {len(opportunities)} unnotified opportunities")

        # Pre-fetch viability status for all listing_ids
        listing_ids = [o["listing_id"] for o in opportunities]
        viable_set: set[int] = set()
        if listing_ids:
            for i in range(0, len(listing_ids), 100):
                batch_ids = listing_ids[i:i + 100]
                vr = (
                    db.table("viability_studies")
                    .select("listing_id")
                    .in_("listing_id", batch_ids)
                    .eq("is_viable", True)
                    .execute()
                )
                viable_set.update(v["listing_id"] for v in (vr.data or []))

        for opp in opportunities:
            listing = opp.get("listing")
            if isinstance(listing, list):
                listing = listing[0] if listing else None
            if not listing:
                continue

            # Skip opportunities where viability was assessed and ALL scenarios failed
            lid = opp["listing_id"]
            has_viability = lid in listing_ids
            is_viable = lid in viable_set
            if has_viability and not is_viable:
                # Viability assessed but no scenario is viable — don't notify
                logger.info(
                    f"[notifier] Skipping #{opp['id']} (score={opp['score']}) "
                    f"— no viable scenario"
                )
                # Mark as notified to avoid re-checking
                db.table("opportunities").update({
                    "is_notified": True,
                    "notified_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", opp["id"]).execute()
                continue

            try:
                message = _format_message(opp, listing, is_viable)
                image_url = listing.get("main_image_url")

                if image_url:
                    _send_photo(image_url, message)
                else:
                    _send_message(message)

                # Mark as notified
                db.table("opportunities").update({
                    "is_notified": True,
                    "notified_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", opp["id"]).execute()

                stats["notified"] += 1
                logger.info(f"[notifier] Sent alert for opportunity #{opp['id']} (score={opp['score']})")

            except Exception:
                stats["failed"] += 1
                logger.exception(f"[notifier] Failed to send alert for #{opp['id']}")

        logger.info(
            f"[notifier] Done: {stats['notified']} sent, {stats['failed']} failed"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[notifier] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _format_message(opp: dict[str, Any], listing: dict[str, Any],
                    is_viable: bool = False) -> str:
    """Format a Telegram message for an opportunity."""
    score = opp["score"]
    price = float(listing.get("sale_price") or 0)
    area = float(listing.get("total_area") or 0)
    pm2 = float(listing.get("price_per_m2") or 0)
    neigh = listing.get("neighborhood") or "?"
    source = listing.get("source", "?")
    address = listing.get("address") or ""
    title = listing.get("title") or "Terreno"
    is_mcmv = listing.get("is_mcmv", False)
    url = listing.get("url") or ""
    lat = listing.get("latitude")
    lng = listing.get("longitude")

    # Score emoji
    if score >= 80 and is_viable:
        header = "🔴 OPORTUNIDADE QUENTE — VIÁVEL"
    elif score >= 80:
        header = "🔴 OPORTUNIDADE QUENTE"
    elif score >= 70 and is_viable:
        header = "🟡 BOA OPORTUNIDADE — VIÁVEL"
    elif score >= 70:
        header = "🟡 BOA OPORTUNIDADE"
    else:
        header = "⚪ MONITORAR"

    # Breakdown
    bd = opp.get("score_breakdown", {})

    lines = [
        f"*{header}*",
        f"Score: *{score:.0f}/100*",
        "",
        f"📍 *{neigh}*",
    ]

    if address:
        lines.append(f"   {address}")

    lines.append("")
    lines.append(f"💰 Preço: *R$ {price:,.0f}*")

    if area > 0:
        lines.append(f"📐 Área: *{area:,.0f} m²*")
    if pm2 > 0:
        lines.append(f"📊 R$/m²: *R$ {pm2:,.0f}*")

    if is_mcmv:
        lines.append("✅ *MCMV compatível*")
    elif price <= 264000:
        lines.append("🏠 Preço dentro do teto MCMV")

    lines.append("")
    lines.append(f"Fonte: {source}")

    # Score breakdown compact
    parts = []
    if bd.get("price", 0) > 0:
        parts.append(f"preço={bd['price']}")
    if bd.get("price_m2", 0) > 0:
        parts.append(f"m²={bd['price_m2']}")
    if bd.get("area", 0) > 0:
        parts.append(f"área={bd['area']}")
    if bd.get("mcmv", 0) > 0:
        parts.append(f"mcmv={bd['mcmv']}")
    if bd.get("location", 0) > 0:
        parts.append(f"loc={bd['location']}")
    if bd.get("data_quality", 0) > 0:
        parts.append(f"dq={bd['data_quality']}")
    if parts:
        lines.append(f"Scoring: {' | '.join(parts)}")

    # Google Maps link if we have coordinates
    if lat and lng:
        lines.append(f"\n[📍 Ver no mapa](https://maps.google.com/?q={lat},{lng})")

    if url:
        lines.append(f"[🔗 Ver anúncio]({url})")

    return "\n".join(lines)


def _send_message(text: str) -> None:
    """Send a text message via Telegram."""
    url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendMessage"
    resp = httpx.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=15)
    resp.raise_for_status()


def _send_photo(photo_url: str, caption: str) -> None:
    """Send a photo with caption via Telegram."""
    url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendPhoto"
    # Telegram caption limit is 1024 chars
    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    resp = httpx.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown",
    }, timeout=15)

    if resp.status_code != 200:
        # Fallback to text if photo fails
        logger.warning(f"[notifier] Photo send failed ({resp.status_code}), falling back to text")
        _send_message(caption)


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
        "items_processed": stats["checked"],
        "items_created": stats["notified"],
        "items_failed": stats["failed"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

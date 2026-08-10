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
PRICE_DROP_PCT = float(os.getenv("PRICE_DROP_RENOTIFY_PCT", "5"))


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
                "main_image_url, url, latitude, longitude, canonical_listing_id)"
            )
            .eq("is_notified", False)
            .gte("score", MIN_SCORE_NOTIFY)
            .order("score", desc=True)
            .limit(10)
            .execute()
        )

        opportunities = list(result.data or [])

        # Inclui price-drop renotifications: opps já notificadas onde
        # sale_price atual caiu >= PRICE_DROP_PCT% vs last_notified_price.
        price_drops = _fetch_price_drops(db)
        if price_drops:
            logger.info(f"[notifier] {len(price_drops)} price-drop renotifications")
            opportunities.extend(price_drops)
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

        canonical_already_notified: set[int] = set()
        for opp in opportunities:
            listing = opp.get("listing")
            if isinstance(listing, list):
                listing = listing[0] if listing else None
            if not listing:
                continue

            # Anti-ruído: pula listings canônicos (cópias) — se já notifiquei o
            # canônico nesta batch ou em batch anterior, este aqui é redundante.
            canon_id = listing.get("canonical_listing_id")
            if canon_id:
                if canon_id in canonical_already_notified:
                    logger.info(
                        f"[notifier] Skipping #{opp['id']} — duplicata do canônico {canon_id}"
                    )
                    db.table("opportunities").update({
                        "is_notified": True,
                        "notified_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", opp["id"]).execute()
                    continue
                canonical_already_notified.add(canon_id)

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
                # Price-drop banner se aplicável
                price_drop = opp.get("_price_drop")
                image_url = listing.get("main_image_url")
                kb = _build_inline_kb(opp.get("id"), listing.get("id"), listing.get("url"))
                if image_url:
                    caption = _format_caption(opp, listing, is_viable, price_drop=price_drop)
                    msg_id = _send_photo(image_url, caption, reply_markup=kb)
                else:
                    message = _format_message(opp, listing, is_viable, price_drop=price_drop)
                    msg_id = _send_message(message, reply_markup=kb)
                _store_opp_message(db, opp["id"], msg_id)

                # Persist last_notified_price em score_breakdown pra detectar drops futuros
                bd = opp.get("score_breakdown") or {}
                if isinstance(bd, dict):
                    bd["last_notified_price"] = float(listing.get("sale_price") or 0)
                db.table("opportunities").update({
                    "is_notified": True,
                    "notified_at": datetime.now(timezone.utc).isoformat(),
                    "score_breakdown": bd,
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
                    is_viable: bool = False,
                    price_drop: Optional[dict[str, Any]] = None) -> str:
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
    ]
    if price_drop:
        lines.append(
            f"🔻 *Preço CAIU {price_drop['pct']}%* "
            f"(R$ {price_drop['from']:,.0f} → R$ {price_drop['to']:,.0f})"
        )
    lines.extend(["", f"📍 *{neigh}*"])

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

    # Links (sempre no fim, antes da assinatura). URL do anúncio é prioritário.
    lines.append("")
    if url:
        lines.append(f"🔗 *Ver anúncio:* {url}")
    else:
        lines.append("_(anúncio sem URL cadastrada)_")
    if lat and lng:
        lines.append(f"📍 *Mapa:* https://maps.google.com/?q={lat},{lng}")

    return "\n".join(lines)


def _fetch_price_drops(db: Any) -> list[dict[str, Any]]:
    """Opps já notificadas onde preço atual caiu PRICE_DROP_PCT% vs last_notified_price.

    Retorna mesma estrutura de `opportunities` mas com `_price_drop` = % de queda
    pra renderizar banner no card.
    """
    try:
        r = (
            db.table("opportunities")
            .select(
                "id, listing_id, score, score_breakdown, reason, "
                "listing:listings(id, source, title, neighborhood, address, "
                "sale_price, total_area, price_per_m2, bedrooms, is_mcmv, "
                "main_image_url, url, latitude, longitude, canonical_listing_id)"
            )
            .eq("is_notified", True)
            .gte("score", MIN_SCORE_NOTIFY)
            .order("notified_at", desc=True)
            .limit(200)
            .execute()
        )
    except Exception:
        return []
    drops = []
    for opp in r.data or []:
        bd = opp.get("score_breakdown") or {}
        if not isinstance(bd, dict):
            continue
        last = bd.get("last_notified_price")
        if not last or last <= 0:
            continue
        listing = opp.get("listing")
        if isinstance(listing, list):
            listing = listing[0] if listing else None
        if not listing:
            continue
        cur = float(listing.get("sale_price") or 0)
        if cur <= 0 or cur >= last:
            continue
        drop_pct = (last - cur) / last * 100
        if drop_pct < PRICE_DROP_PCT:
            continue
        opp["_price_drop"] = {
            "pct": round(drop_pct, 1),
            "from": float(last),
            "to": cur,
        }
        # Não reseta is_notified aqui: o opp já entra na lista processada pelo
        # loop principal, que grava is_notified=True + novo last_notified_price
        # só após o envio confirmado. Resetar antes deixaria a opp presa em
        # is_notified=False (renotificável) caso o envio falhasse.
        drops.append(opp)
    return drops


def _fetch_avm(listing_id: int) -> Optional[dict[str, Any]]:
    """Busca avm_predictions p/ esse listing. None se não existir."""
    try:
        from src.db import get_client
        r = (
            get_client()
            .table("avm_predictions")
            .select("p25, p50, p75, mispricing_pct, is_undervalued")
            .eq("listing_id", listing_id)
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None
    except Exception:
        return None


def _format_caption(opp: dict[str, Any], listing: dict[str, Any],
                    is_viable: bool = False,
                    price_drop: Optional[dict[str, Any]] = None) -> str:
    """Versão compacta para sendPhoto caption (limite Telegram = 1024 chars).

    Inclui AVM (P25/P50/P75) + mispricing % quando disponível.
    """
    score = opp["score"]
    price = float(listing.get("sale_price") or 0)
    area = float(listing.get("total_area") or 0)
    pm2 = float(listing.get("price_per_m2") or 0)
    neigh = listing.get("neighborhood") or "?"
    source = listing.get("source", "?")
    is_mcmv = listing.get("is_mcmv", False)
    url = listing.get("url") or ""
    lat = listing.get("latitude")
    lng = listing.get("longitude")

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

    # AVM lookup
    avm = _fetch_avm(opp.get("listing_id") or listing.get("id"))
    price_line = f"💰 R$ {price:,.0f}"
    if avm and avm.get("mispricing_pct") is not None:
        mp = float(avm["mispricing_pct"])
        if mp >= 5:
            price_line += f" (📉 {mp:.0f}% *abaixo do justo*)"
        elif mp <= -5:
            price_line += f" (📈 {abs(mp):.0f}% acima do justo)"

    lines = [f"*{header}* — Score *{score:.0f}/100*"]
    if price_drop:
        lines.append(
            f"🔻 *Preço CAIU {price_drop['pct']}%* "
            f"(R$ {price_drop['from']:,.0f} → R$ {price_drop['to']:,.0f})"
        )
    lines.extend([
        f"📍 *{neigh}*",
        price_line + (f" | 📐 {area:,.0f}m²" if area > 0 else ""),
    ])
    if pm2 > 0:
        lines.append(f"   R$ {pm2:,.0f}/m²")

    # AVM detalhado (uma linha)
    if avm and avm.get("p50"):
        p25 = avm.get("p25") or 0
        p50 = avm.get("p50") or 0
        p75 = avm.get("p75") or 0
        lines.append(
            f"🎯 AVM: P25 R${p25/1000:.0f}k | P50 R${p50/1000:.0f}k | P75 R${p75/1000:.0f}k"
        )
        if avm.get("is_undervalued"):
            lines.append(f"💡 *Teto de oferta:* R$ {p25:,.0f}")

    if is_mcmv:
        lines.append("✅ MCMV compatível")
    lines.append(f"_Fonte: {source}_")

    # Link sempre no fim — prioritário
    if url:
        lines.append(f"🔗 {url}")
    else:
        lines.append("_(sem URL cadastrada)_")
    if lat and lng:
        lines.append(f"📍 https://maps.google.com/?q={lat},{lng}")

    text = "\n".join(lines)
    # Hard cap em 1000 chars deixando margem segura
    if len(text) > 1000:
        # Preserva o link no fim: corta do meio
        url_line = f"\n🔗 {url}" if url else ""
        head = text[:1000 - len(url_line) - 4].rsplit("\n", 1)[0]
        text = f"{head}\n...{url_line}"
    return text


def _build_inline_kb(opp_id: Optional[int], listing_id: Optional[int],
                     listing_url: Optional[str]) -> Optional[dict]:
    """Inline keyboard com Visitar/Ignorar/Ficha. None se faltar dado."""
    if not opp_id or not listing_id:
        return None
    buttons = [[
        {"text": "✅ Vou visitar", "callback_data": f"deal:visit:{listing_id}:{opp_id}"},
        {"text": "🚫 Ignorar", "callback_data": f"deal:ignore:{listing_id}:{opp_id}"},
    ], [
        {"text": "📋 Ficha completa", "callback_data": f"ficha:{listing_id}"},
    ]]
    if listing_url:
        buttons.append([{"text": "🔗 Abrir anúncio", "url": listing_url}])
    return {"inline_keyboard": buttons}


def _send_message(text: str, reply_markup: Optional[dict] = None) -> Optional[int]:
    """Send a text message via Telegram. Returns message_id or None on failure."""
    url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendMessage"
    body: dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    resp = httpx.post(url, json=body, timeout=15)
    resp.raise_for_status()
    return resp.json().get("result", {}).get("message_id")


def _send_photo(photo_url: str, caption: str,
                reply_markup: Optional[dict] = None) -> Optional[int]:
    """Send a photo with caption via Telegram. Returns message_id or None on failure."""
    url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendPhoto"
    if len(caption) > 1024:
        caption = caption[:1020] + "..."
    body: dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    resp = httpx.post(url, json=body, timeout=15)

    if resp.status_code != 200:
        logger.warning(f"[notifier] Photo send failed ({resp.status_code}), falling back to text")
        return _send_message(caption, reply_markup=reply_markup)
    return resp.json().get("result", {}).get("message_id")


def _store_opp_message(db: Any, opp_id: int, message_id: Optional[int]) -> None:
    """Persiste (opp_id, chat_id, message_id) para sincronizar botões futuramente."""
    if not message_id:
        return
    try:
        db.table("opp_messages").insert({
            "opp_id": opp_id,
            "chat_id": str(TELEGRAM_CHAT_ID),
            "message_id": message_id,
        }).execute()
    except Exception as exc:
        logger.debug(f"[notifier] opp_messages insert falhou: {exc}")


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

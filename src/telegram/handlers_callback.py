"""Callback query handlers — botões inline em cards de oportunidade.

Callback data formats:
  deal:visit:<listing_id>:<opp_id>     → cria bm3_deal stage=visited
  deal:ignore:<listing_id>:<opp_id>    → marca opp como ignored
  ficha:<listing_id>                   → gera ficha completa
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Roteador de callback queries (inline button clicks)."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()  # remove spinner do botão

    data = query.data
    try:
        if data.startswith("deal:visit:"):
            await _handle_deal_visit(query, data)
        elif data.startswith("deal:ignore:"):
            await _handle_deal_ignore(query, data)
        elif data.startswith("ficha:"):
            await _handle_ficha(query, data)
        else:
            await query.message.reply_text(f"Callback desconhecido: `{data}`",
                                            parse_mode="Markdown")
    except Exception as exc:
        logger.exception(f"[callback] handler failed for {data}")
        await query.message.reply_text(f"Erro: {exc}")


async def _handle_deal_visit(query, data: str) -> None:
    """deal:visit:<listing_id>:<opp_id> → cria bm3_deal stage=visited."""
    parts = data.split(":")
    if len(parts) < 4:
        await query.message.reply_text("Callback inválido.")
        return
    listing_id = int(parts[2])
    opp_id = int(parts[3])
    try:
        from src.feedback_loop import record_deal
        deal_id = record_deal(listing_id=listing_id, stage="visited",
                              notes=f"via Telegram (opp #{opp_id})")
        await query.message.reply_text(
            f"✅ *Deal #{deal_id} criado* — stage=visited\n"
            f"Próximo: `/deal_update {deal_id} offered <preço>` ao fazer oferta",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[callback] record_deal failed")
        await query.message.reply_text(f"Erro ao registrar deal: {exc}")


async def _handle_deal_ignore(query, data: str) -> None:
    """deal:ignore:<listing_id>:<opp_id> → marca opp como ignorada."""
    parts = data.split(":")
    if len(parts) < 4:
        await query.message.reply_text("Callback inválido.")
        return
    opp_id = int(parts[3])
    try:
        from src.db import get_client
        get_client().table("opportunities").update({
            "is_ignored": True,
        }).eq("id", opp_id).execute()
        await query.message.reply_text(f"🚫 Opp #{opp_id} ignorada.")
    except Exception as exc:
        # Se coluna is_ignored não existir, registra deal stage='abandoned'
        try:
            listing_id = int(parts[2])
            from src.feedback_loop import record_deal
            record_deal(listing_id=listing_id, stage="abandoned",
                        notes=f"ignored via Telegram (opp #{opp_id})")
            await query.message.reply_text(
                f"🚫 Registrado como abandonado (opp #{opp_id})"
            )
        except Exception:
            logger.exception("[callback] ignore failed")
            await query.message.reply_text(f"Erro: {exc}")


async def _handle_ficha(query, data: str) -> None:
    """ficha:<listing_id> → gera ficha completa."""
    parts = data.split(":")
    if len(parts) < 2:
        return
    listing_id = int(parts[1])
    await query.message.reply_text("🔎 Gerando ficha completa...")
    try:
        from src.db import get_client
        from src.telegram.ficha import generate_ficha
        r = (
            get_client()
            .table("listings")
            .select("url, latitude, longitude")
            .eq("id", listing_id)
            .limit(1)
            .execute()
        )
        if not r.data:
            await query.message.reply_text(f"Listing #{listing_id} não encontrado.")
            return
        l = r.data[0]
        # Prioriza URL → coord → fallback
        if l.get("url"):
            text = generate_ficha(l["url"])
        elif l.get("latitude") and l.get("longitude"):
            text = generate_ficha(f"{l['latitude']},{l['longitude']}")
        else:
            await query.message.reply_text("Sem URL ou coord no listing.")
            return
        # Pode passar de 4096
        for i in range(0, len(text), 4000):
            await query.message.reply_text(
                text[i:i + 4000], parse_mode="Markdown",
                disable_web_page_preview=True,
            )
    except Exception as exc:
        logger.exception("[callback] ficha failed")
        await query.message.reply_text(f"Erro: {exc}")


# =========================== INTEGRATION ============================
# Em src/telegram_bot.py, dentro de run_bot(), adicione:
#   from telegram.ext import CallbackQueryHandler
#   from src.telegram.handlers_callback import handle_callback
#   app.add_handler(CallbackQueryHandler(handle_callback))
# ====================================================================

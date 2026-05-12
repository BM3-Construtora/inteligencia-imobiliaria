"""Telegram handlers for Track B — Ficha de Terreno.

Async handlers for /ficha <query> and location pin messages.
Designed to be wired in src/telegram_bot.py WITHOUT modifying that file.
See INTEGRATION INSTRUCTIONS at the bottom.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

USAGE = (
    "Use: `/ficha <endereço/CEP/coord/URL> [área m²] [R$ preço]`\n\n"
    "Exemplos:\n"
    "• `/ficha Rua das Flores, 123, Palmital 250m² R$ 180000`\n"
    "• `/ficha 17500-000 300m²`\n"
    "• `/ficha -22.21,-49.95 500m² R$200000`\n"
    "• `/ficha https://www.olx.com.br/...` (URL cadastrada)\n\n"
    "Ou envie um *pin de localização* pelo Telegram."
)

MAX_CHARS = 4000


def _split_message(text: str, max_len: int = MAX_CHARS) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks


async def _run_generate(query: str) -> str:
    """Run the synchronous generate_ficha off the event loop with hard timeout."""
    from src.telegram.ficha import generate_ficha
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, generate_ficha, query),
            timeout=32.0,
        )
    except asyncio.TimeoutError:
        return (
            "⏱ Tempo esgotado ao gerar a ficha (>30s).\n"
            "Tente novamente ou simplifique a consulta.\n\n"
            "_Recomendação — decisão final é sua._"
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("[handlers_ficha] generate_ficha crashed")
        return (
            f"❌ Erro ao gerar a ficha: `{exc}`\n\n"
            "_Recomendação — decisão final é sua._"
        )


async def cmd_ficha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ficha <endereço|CEP|coord|URL> — ficha completa do terreno."""
    if not update.message:
        return
    if not context.args:
        await update.message.reply_text(USAGE, parse_mode="Markdown", disable_web_page_preview=True)
        return

    query = " ".join(context.args).strip()
    await update.message.reply_text("🔎 Gerando ficha (até 30s)...")

    text = await _run_generate(query)
    for chunk in _split_message(text):
        try:
            await update.message.reply_text(
                chunk, parse_mode="Markdown", disable_web_page_preview=True
            )
        except Exception:
            # Markdown parse failure → resend plain
            await update.message.reply_text(chunk, disable_web_page_preview=True)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle location pin → /ficha equivalent using lat,lng."""
    if not update.message or not update.message.location:
        return
    loc = update.message.location
    query = f"{loc.latitude},{loc.longitude}"
    await update.message.reply_text(
        f"📍 Pin recebido (`{query}`). Gerando ficha...",
        parse_mode="Markdown",
    )
    text = await _run_generate(query)
    for chunk in _split_message(text):
        try:
            await update.message.reply_text(
                chunk, parse_mode="Markdown", disable_web_page_preview=True
            )
        except Exception:
            await update.message.reply_text(chunk, disable_web_page_preview=True)


# ============ INTEGRATION INSTRUCTIONS ============
# Em src/telegram_bot.py, dentro de run_bot(), adicione:
#
#   from src.telegram.handlers_ficha import cmd_ficha, handle_location
#   app.add_handler(CommandHandler("ficha", cmd_ficha))
#   app.add_handler(MessageHandler(filters.LOCATION, handle_location))
#
# IMPORTANTE: registre estes handlers ANTES do MessageHandler genérico
# de texto livre (handle_message), pois CommandHandler já tem prioridade
# sobre TEXT & ~COMMAND, mas o LOCATION precisa estar registrado
# explicitamente — filters.TEXT não captura location messages.
#
# Também atualize cmd_start() (texto de boas-vindas) acrescentando:
#   "/ficha <endereço/CEP/coord/URL> — Ficha completa do terreno\n"
# ==================================================

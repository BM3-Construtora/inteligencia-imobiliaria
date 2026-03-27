"""MariliaBot Telegram — conversational bot with slash commands + AI chat."""

from __future__ import annotations

import logging
import os
import re

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


# --- Command Handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with command list."""
    text = (
        "🏗 *MariliaBot — Inteligencia Imobiliaria*\n\n"
        "Sou seu assistente para decisoes de construcao em Marilia-SP.\n\n"
        "*Comandos:*\n"
        "/top — Top 10 oportunidades de terrenos\n"
        "/bairro <nome> — Analise completa de um bairro\n"
        "/viabilidade <preco> <area> — Simular projeto MCMV\n"
        "/mercado — Resumo geral do mercado\n"
        "/relatorio — Relatorio semanal completo\n\n"
        "Ou simplesmente *me faca uma pergunta* sobre o mercado imobiliario de Marilia!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Top opportunities."""
    await update.message.reply_text("Buscando oportunidades...")
    from src.telegram.queries import get_top_opportunities
    text = get_top_opportunities(10)
    # Split if too long (Telegram max 4096 chars)
    for chunk in _split_message(text):
        await update.message.reply_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_bairro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Neighborhood analysis."""
    if not context.args:
        await update.message.reply_text("Use: /bairro <nome>\nExemplo: /bairro Palmital")
        return

    name = " ".join(context.args)
    await update.message.reply_text(f"Analisando {name}...")
    from src.telegram.queries import get_neighborhood_analysis
    text = get_neighborhood_analysis(name)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_viabilidade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Viability simulation."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Use: /viabilidade <preco> <area>\n"
            "Exemplo: /viabilidade 200000 500\n"
            "(terreno de R$200k com 500m²)"
        )
        return

    try:
        price = float(context.args[0].replace(",", "").replace(".", ""))
        area = float(context.args[1].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text("Valores invalidos. Use numeros: /viabilidade 200000 500")
        return

    await update.message.reply_text(f"Simulando viabilidade para R$ {price:,.0f} / {area:,.0f}m²...")
    from src.telegram.queries import simulate_viability_text
    text = simulate_viability_text(price, area)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_mercado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Market summary."""
    await update.message.reply_text("Buscando dados do mercado...")
    from src.telegram.queries import get_market_summary
    text = get_market_summary()
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send weekly report."""
    await update.message.reply_text("Gerando relatorio semanal...")
    from src.reporter import _gather_report_data, _build_static_report
    from src.db import get_client
    db = get_client()
    data = _gather_report_data(db)
    text = _build_static_report(data)
    for chunk in _split_message(text):
        await update.message.reply_text(chunk)


# --- Free-text / AI Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any text message — pass to Gemini AI with market context."""
    user_msg = update.message.text
    if not user_msg:
        return

    await update.message.reply_text("🤔 Analisando...")

    from src.telegram.ai import answer_question
    response = answer_question(user_msg)

    for chunk in _split_message(response):
        await update.message.reply_text(chunk)


# --- Helpers ---

def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split long messages into chunks for Telegram's 4096 char limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Find last newline before limit
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks


# --- Main ---

def run_bot() -> None:
    """Start the Telegram bot in polling mode."""
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    logger.info("Starting MariliaBot Telegram (polling)...")

    app = Application.builder().token(TOKEN).build()

    # Slash commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("bairro", cmd_bairro))
    app.add_handler(CommandHandler("viabilidade", cmd_viabilidade))
    app.add_handler(CommandHandler("mercado", cmd_mercado))
    app.add_handler(CommandHandler("relatorio", cmd_relatorio))

    # Free-text messages → AI
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

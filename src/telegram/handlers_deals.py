"""Telegram handlers para Track D — bm3_deals + calibration.

Não modifica `telegram_bot.py`. Veja INTEGRATION INSTRUCTIONS no fim do arquivo.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from src.feedback_loop import (
    VALID_STAGES,
    record_deal,
    record_outcome,
    weekly_drift_report,
)

logger = logging.getLogger(__name__)


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > max_len:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


async def cmd_deal_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/deal_add <listing_id> <stage>  — registra visita/etapa de um deal.

    Use listing_id=0 para deal off-market.
    """
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Uso: /deal_add <listing_id> <stage>\n"
            f"Stages: {', '.join(sorted(VALID_STAGES))}\n"
            "Use listing_id=0 para off-market."
        )
        return
    try:
        listing_id_raw = int(args[0])
        listing_id = None if listing_id_raw == 0 else listing_id_raw
        stage = args[1]
        if stage not in VALID_STAGES:
            await update.message.reply_text(f"Stage inválido. Valores: {sorted(VALID_STAGES)}")
            return
        notes = " ".join(args[2:]) if len(args) > 2 else None
        deal_id = record_deal(listing_id=listing_id, stage=stage, notes=notes)
    except Exception as exc:
        logger.exception("[handlers_deals] /deal_add falhou")
        await update.message.reply_text(f"Erro: {exc}")
        return

    await update.message.reply_text(
        f"OK — deal *id={deal_id}* criado (stage={stage}).\n"
        f"Próximo: /deal_update {deal_id} offered <preço>",
        parse_mode="Markdown",
    )


async def cmd_deal_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/deal_update <deal_id> <stage> [<preço>]"""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Uso: /deal_update <deal_id> <stage> [<preço>]\n"
            "Ex: /deal_update 42 offered 195000"
        )
        return
    try:
        from src.db import get_client
        deal_id = int(args[0])
        stage = args[1]
        if stage not in VALID_STAGES:
            await update.message.reply_text(f"Stage inválido. Valores: {sorted(VALID_STAGES)}")
            return

        fields: dict[str, Any] = {}
        if len(args) >= 3:
            try:
                price = float(args[2].replace(",", "."))
            except ValueError:
                await update.message.reply_text("Preço inválido (use número, ex: 195000)")
                return
            if stage in {"offered", "negotiating"}:
                fields["offered_price"] = price
            elif stage in {"accepted", "closed_won"}:
                fields["accepted_price"] = price
            else:
                fields["offered_price"] = price

        db = get_client()
        res = db.table("bm3_deals").select("listing_id").eq("id", deal_id).limit(1).execute()
        if not res.data:
            await update.message.reply_text(f"Deal id={deal_id} não encontrado")
            return
        listing_id = res.data[0].get("listing_id")
        record_deal(listing_id=listing_id, stage=stage, deal_id=deal_id, **fields)
    except Exception as exc:
        logger.exception("[handlers_deals] /deal_update falhou")
        await update.message.reply_text(f"Erro: {exc}")
        return

    await update.message.reply_text(
        f"OK — deal *id={deal_id}* atualizado para *{stage}*.",
        parse_mode="Markdown",
    )


async def cmd_deal_outcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/deal_outcome <deal_id> <margem%> <payback_meses>"""
    args = context.args or []
    if len(args) < 3:
        await update.message.reply_text(
            "Uso: /deal_outcome <deal_id> <margem%> <payback_meses>\n"
            "Ex: /deal_outcome 42 22.5 18"
        )
        return
    try:
        deal_id = int(args[0])
        margin = float(args[1].replace(",", "."))
        payback = int(args[2])
        record_outcome(deal_id, margin, payback)
    except Exception as exc:
        logger.exception("[handlers_deals] /deal_outcome falhou")
        await update.message.reply_text(f"Erro: {exc}")
        return

    await update.message.reply_text(
        f"OK — outcome registrado: id={deal_id} margem={margin}% payback={payback}m"
    )


async def cmd_calibration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/calibration — roda run_calibration e envia drift report."""
    await update.message.reply_text("Rodando calibração...")
    try:
        text = weekly_drift_report()
    except Exception as exc:
        logger.exception("[handlers_deals] /calibration falhou")
        await update.message.reply_text(f"Erro: {exc}")
        return
    for chunk in _split_message(text):
        await update.message.reply_text(chunk, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# INTEGRATION INSTRUCTIONS — Track D
# ---------------------------------------------------------------------------
# Para registrar estes handlers em `src/telegram_bot.py`, adicione DENTRO da
# função que constrói a Application (junto dos outros `app.add_handler`):
#
#     from src.telegram.handlers_deals import (
#         cmd_deal_add,
#         cmd_deal_update,
#         cmd_deal_outcome,
#         cmd_calibration,
#     )
#     app.add_handler(CommandHandler("deal_add",     cmd_deal_add))
#     app.add_handler(CommandHandler("deal_update",  cmd_deal_update))
#     app.add_handler(CommandHandler("deal_outcome", cmd_deal_outcome))
#     app.add_handler(CommandHandler("calibration",  cmd_calibration))
#
# E inclua no `cmd_start` (help) as linhas:
#     /deal_add <listing_id> <stage> — registrar visita/etapa
#     /deal_update <deal_id> <stage> [preço]
#     /deal_outcome <deal_id> <margem%> <payback_meses>
#     /calibration — drift report (Hunter/AVM/Viability vs realidade)
# ---------------------------------------------------------------------------

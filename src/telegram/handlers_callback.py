"""Callback query handlers — botões inline em cards de oportunidade.

Callback data formats:
  deal:visit:<listing_id>:<opp_id>     → registra voto "visitar" por usuário
  deal:ignore:<listing_id>:<opp_id>    → registra voto "ignorar" por usuário
  ficha:<listing_id>                   → gera ficha completa

Votos são por usuário (opp_votes). Primeiro voto que escolhe "visit" cria o
bm3_deal; votos subsequentes apenas atualizam o label dos botões. Cada usuário
vê toast privado e os botões mostram quem votou o quê.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de voto
# ---------------------------------------------------------------------------

def _get_username(user) -> str:
    return user.first_name or user.username or str(user.id)


def _load_votes(db: Any, opp_id: int) -> dict[str, list[str]]:
    """Retorna {'visit': [names], 'ignore': [names]} para o opp."""
    res = (
        db.table("opp_votes")
        .select("username, action")
        .eq("opp_id", opp_id)
        .execute()
    )
    result: dict[str, list[str]] = {"visit": [], "ignore": []}
    for row in res.data or []:
        action = row.get("action")
        if action in result:
            result[action].append(row["username"])
    return result


def _names_label(names: list[str], limit: int = 2) -> str:
    if not names:
        return ""
    label = ", ".join(names[:limit])
    if len(names) > limit:
        label += f" +{len(names) - limit}"
    return label


def _build_keyboard(opp_id: int, listing_id: int, votes: dict[str, list[str]]) -> InlineKeyboardMarkup:
    visit_names = _names_label(votes["visit"])
    ignore_names = _names_label(votes["ignore"])

    visit_label = f"✅ {visit_names}" if visit_names else "✅ Vou visitar"
    ignore_label = f"🚫 {ignore_names}" if ignore_names else "🚫 Ignorar"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(visit_label, callback_data=f"deal:visit:{listing_id}:{opp_id}"),
            InlineKeyboardButton(ignore_label, callback_data=f"deal:ignore:{listing_id}:{opp_id}"),
        ],
        [InlineKeyboardButton("📋 Ficha completa", callback_data=f"ficha:{listing_id}")],
    ])


async def _edit_keyboard(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    opp_id: int,
    listing_id: int,
    votes: dict[str, list[str]],
) -> None:
    """Edita o reply_markup em TODOS os cards conhecidos para este opp_id.

    Atualiza a mensagem clicada diretamente via query, e busca outros
    message_ids em opp_messages para manter todos sincronizados.
    """
    from src.db import get_client
    keyboard = _build_keyboard(opp_id, listing_id, votes)

    # Edita a mensagem que gerou o callback
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except Exception as exc:
        if "message is not modified" not in str(exc).lower():
            logger.debug(f"[callback] edit_keyboard (clicked) opp={opp_id}: {exc}")

    # Edita todos os outros cards do mesmo opp
    try:
        db = get_client()
        rows = (
            db.table("opp_messages")
            .select("chat_id, message_id")
            .eq("opp_id", opp_id)
            .execute()
        )
        clicked_msg_id = query.message.message_id
        for row in rows.data or []:
            if row["message_id"] == clicked_msg_id:
                continue  # já editado acima
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=row["chat_id"],
                    message_id=row["message_id"],
                    reply_markup=keyboard,
                )
            except Exception as exc:
                if "message is not modified" not in str(exc).lower():
                    logger.debug(f"[callback] edit_keyboard msg={row['message_id']}: {exc}")
    except Exception as exc:
        logger.debug(f"[callback] edit_keyboard bulk opp={opp_id}: {exc}")


def _upsert_vote(db: Any, opp_id: int, user_id: int, username: str, action: str) -> tuple[bool, bool]:
    """Grava ou atualiza voto.

    Retorna (is_new, changed):
      is_new  — True se o usuário ainda não tinha votado nessa opp
      changed — True se o estado mudou (novo voto ou troca de ação)
    """
    existing = (
        db.table("opp_votes")
        .select("action")
        .eq("opp_id", opp_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if not existing.data:
        db.table("opp_votes").insert({
            "opp_id": opp_id,
            "user_id": user_id,
            "username": username,
            "action": action,
        }).execute()
        return True, True

    if existing.data[0]["action"] == action:
        return False, False  # mesmo voto, nada a fazer

    db.table("opp_votes").update({
        "action": action,
        "username": username,
    }).eq("opp_id", opp_id).eq("user_id", user_id).execute()
    return False, True


def _deal_already_open(db: Any, listing_id: int) -> bool:
    res = (
        db.table("bm3_deals")
        .select("id")
        .eq("listing_id", listing_id)
        .not_.in_("stage", ["abandoned", "closed_lost", "rejected"])
        .limit(1)
        .execute()
    )
    return bool(res.data)


# ---------------------------------------------------------------------------
# Roteador principal
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    try:
        if data.startswith("deal:visit:"):
            await _handle_deal_visit(query, context, data)
        elif data.startswith("deal:ignore:"):
            await _handle_deal_ignore(query, context, data)
        elif data.startswith("ficha:"):
            await query.answer()
            await _handle_ficha(query, data)
        else:
            await query.answer()
            await query.message.reply_text(f"Callback desconhecido: `{data}`",
                                            parse_mode="Markdown")
    except Exception as exc:
        logger.exception(f"[callback] handler failed for {data}")
        try:
            await query.answer(f"Erro: {exc}", show_alert=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# deal:visit
# ---------------------------------------------------------------------------

async def _handle_deal_visit(query, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    parts = data.split(":")
    if len(parts) < 4:
        await query.answer("Callback inválido.", show_alert=True)
        return

    listing_id = int(parts[2])
    opp_id = int(parts[3])
    user = query.from_user
    username = _get_username(user)

    from src.db import get_client
    db = get_client()

    is_new, changed = _upsert_vote(db, opp_id, user.id, username, "visit")

    if not changed:
        await query.answer("Você já votou nessa ✅", show_alert=False)
        return

    votes = _load_votes(db, opp_id)
    await _edit_keyboard(query, context, opp_id, listing_id, votes)

    # Cria deal apenas se é primeiro voto "visit" e não existe deal aberto
    if is_new and not _deal_already_open(db, listing_id):
        try:
            from src.feedback_loop import record_deal
            deal_id = record_deal(
                listing_id=listing_id,
                stage="visited",
                notes=f"via Telegram (opp #{opp_id})",
                created_by=username,
            )
            await query.answer(f"✅ Visita registrada — deal #{deal_id}", show_alert=False)
            return
        except Exception as exc:
            logger.exception("[callback] record_deal failed")
            await query.answer(f"Erro ao criar deal: {exc}", show_alert=True)
            return

    await query.answer("✅ Voto registrado", show_alert=False)


# ---------------------------------------------------------------------------
# deal:ignore
# ---------------------------------------------------------------------------

async def _handle_deal_ignore(query, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    parts = data.split(":")
    if len(parts) < 4:
        await query.answer("Callback inválido.", show_alert=True)
        return

    listing_id = int(parts[2])
    opp_id = int(parts[3])
    user = query.from_user
    username = _get_username(user)

    from src.db import get_client
    db = get_client()

    is_new, changed = _upsert_vote(db, opp_id, user.id, username, "ignore")

    if not changed:
        await query.answer("Você já votou nessa 🚫", show_alert=False)
        return

    votes = _load_votes(db, opp_id)
    await _edit_keyboard(query, context, opp_id, listing_id, votes)

    # Registra abandon apenas no primeiro voto ignore (sem deal aberto)
    if is_new and not _deal_already_open(db, listing_id):
        try:
            from src.feedback_loop import record_deal
            record_deal(
                listing_id=listing_id,
                stage="abandoned",
                notes=f"ignored via Telegram (opp #{opp_id})",
                created_by=username,
            )
        except Exception:
            logger.debug("[callback] ignore: record_deal skipped (deal já existe ou erro)")

    await query.answer("🚫 Ignorado", show_alert=False)


# ---------------------------------------------------------------------------
# ficha
# ---------------------------------------------------------------------------

def _md_to_html(text: str) -> str:
    import re
    text = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    text = re.sub(r"```(.*?)```", lambda m: f"<pre>{m.group(1)}</pre>",
                  text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\*([^\*\n]+?)\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w/])_([^_\n]+?)_(?![\w/])", r"<i>\1</i>", text)
    return text


async def _handle_ficha(query, data: str) -> None:
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
        if l.get("url"):
            text = generate_ficha(l["url"])
        elif l.get("latitude") and l.get("longitude"):
            text = generate_ficha(f"{l['latitude']},{l['longitude']}")
        else:
            await query.message.reply_text("Sem URL ou coord no listing.")
            return

        html_text = _md_to_html(text)
        for i in range(0, len(html_text), 4000):
            chunk = html_text[i:i + 4000]
            try:
                await query.message.reply_text(
                    chunk, parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as html_err:
                logger.warning(f"[callback] HTML parse failed, plain: {html_err}")
                import re
                plain_chunk = re.sub(r"<[^>]+>", "", chunk)
                plain_chunk = re.sub(r"\*([^\*\n]+?)\*", r"\1", plain_chunk)
                plain_chunk = re.sub(r"`([^`\n]+?)`", r"\1", plain_chunk)
                plain_chunk = re.sub(r"_([^_\n]+?)_", r"\1", plain_chunk)
                await query.message.reply_text(plain_chunk, disable_web_page_preview=True)
    except Exception as exc:
        logger.exception("[callback] ficha failed")
        await query.message.reply_text(f"Erro: {exc}")


# =========================== INTEGRATION ============================
# Em src/telegram_bot.py, dentro de run_bot(), adicione:
#   from telegram.ext import CallbackQueryHandler
#   from src.telegram.handlers_callback import handle_callback
#   app.add_handler(CallbackQueryHandler(handle_callback))
# ====================================================================

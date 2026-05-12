"""AVM explainer — formats avm_predictions for negotiation UX (Telegram, etc).

Reads from `avm_predictions` populated by src.price_model.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.db import get_client

logger = logging.getLogger(__name__)


def _fetch(listing_id: int) -> Optional[dict]:
    db = get_client()
    try:
        result = (
            db.table("avm_predictions")
            .select("*")
            .eq("listing_id", listing_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]
    except Exception:
        logger.exception(f"[avm_explain] fetch failed for listing {listing_id}")
        return None


def _fmt_brl(v: Optional[float]) -> str:
    if v is None:
        return "—"
    try:
        return f"R$ {float(v):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def explain_for_telegram(listing_id: int) -> str:
    """Markdown-formatted AVM card for Telegram."""
    row = _fetch(listing_id)
    if not row:
        return "_Avaliação indisponível para este imóvel._"

    p25 = row.get("p25")
    p50 = row.get("p50")
    p75 = row.get("p75")
    model = row.get("model_version") or "avm"
    confidence = row.get("confidence")
    conf_str = f"{int(round(float(confidence) * 100))}%" if confidence is not None else "—"

    top = row.get("shap_top_features") or []
    drivers_lines = []
    from src.price_model import FEATURE_LABELS_PT  # local import: avoid cycles
    for f in top[:5]:
        if not isinstance(f, dict):
            continue
        name = f.get("feature", "")
        label = FEATURE_LABELS_PT.get(name, name)
        contrib = f.get("contribution")
        try:
            c = float(contrib)
        except (TypeError, ValueError):
            continue
        if c == 0:
            continue
        sign = "+" if c > 0 else "-"
        drivers_lines.append(f"• {sign}{_fmt_brl(abs(c))} {label}")

    drivers_block = "\n".join(drivers_lines) if drivers_lines else "• _sem drivers disponíveis_"

    return (
        "💰 *Avaliação Justa*\n"
        f"• P25 (teto de oferta): {_fmt_brl(p25)}\n"
        f"• P50 (preço justo): {_fmt_brl(p50)}\n"
        f"• P75 (preço alto): {_fmt_brl(p75)}\n"
        "\n"
        "📊 *Por que esse valor:*\n"
        f"{drivers_block}\n"
        "\n"
        f"_Modelo {model} — confiança {conf_str}_"
    )


def get_offer_ceiling(listing_id: int) -> Optional[float]:
    """Return P25 as the maximum suggested offer, or None."""
    row = _fetch(listing_id)
    if not row:
        return None
    p25 = row.get("p25")
    try:
        return float(p25) if p25 is not None else None
    except (TypeError, ValueError):
        return None


def get_recommendation(listing_id: int, asking_price: float) -> str:
    """Negotiation recommendation given an asking price."""
    row = _fetch(listing_id)
    if not row:
        return "Avaliação indisponível — não é possível recomendar."

    try:
        p25 = float(row.get("p25")) if row.get("p25") is not None else None
        p50 = float(row.get("p50")) if row.get("p50") is not None else None
        p75 = float(row.get("p75")) if row.get("p75") is not None else None
    except (TypeError, ValueError):
        return "Avaliação inválida — não é possível recomendar."

    if p25 is None or p50 is None:
        return "Avaliação incompleta — não é possível recomendar."

    if asking_price < p25:
        return (
            f"Recomendado avaliar (asking {_fmt_brl(asking_price)} "
            f"< P25 {_fmt_brl(p25)}). Subprecificado."
        )
    if asking_price <= p50:
        return (
            f"Justo (asking {_fmt_brl(asking_price)} entre P25 {_fmt_brl(p25)} "
            f"e P50 {_fmt_brl(p50)}). Tentar negociar até P25."
        )
    if p75 is not None and asking_price <= p75:
        return (
            f"Caro (asking {_fmt_brl(asking_price)} entre P50 {_fmt_brl(p50)} "
            f"e P75 {_fmt_brl(p75)}). Negociar para P50 ou descartar."
        )
    return (
        f"Não recomendado (asking {_fmt_brl(asking_price)} acima de P50 {_fmt_brl(p50)})."
    )

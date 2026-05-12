"""Alertas Telegram para queda de preço de materiais.

Detecta quando o preço mais recente de um SKU seed caiu ≥ THRESHOLD%
em relação ao mínimo dos últimos 30 dias (excluindo o snapshot mais recente).
Envia alerta formatado via Telegram.

Uso standalone:
    python -m src.materials.alerts
    python -m src.materials.alerts --threshold 15

Ou import:
    from src.materials.alerts import run_price_alerts
    stats = run_price_alerts(threshold_pct=10.0)

Integração no workflow:
    Adicionar step após runner no daily-materials.yml.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

DEFAULT_THRESHOLD_PCT = float(os.getenv("MATERIALS_ALERT_THRESHOLD", "10.0"))
LOOKBACK_DAYS = 30


def run_price_alerts(threshold_pct: float = DEFAULT_THRESHOLD_PCT) -> dict[str, int]:
    """Verifica quedas de preço e envia alertas. Retorna stats."""
    stats = {"checked": 0, "alerts_sent": 0, "errors": 0}

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[materials.alerts] TELEGRAM_BOT_TOKEN/CHAT_ID não configurados")
        return stats

    db = get_client()
    drops = _find_price_drops(db, threshold_pct)
    stats["checked"] = len(drops)

    for drop in drops:
        try:
            msg = _format_alert(drop, threshold_pct)
            _send_telegram(msg)
            stats["alerts_sent"] += 1
            logger.info(
                f"[materials.alerts] alerta enviado: {drop['canonical_name']} "
                f"{drop['drop_pct']:.1f}%↓"
            )
        except Exception:
            logger.exception(f"[materials.alerts] falhou enviar alerta: {drop}")
            stats["errors"] += 1

    return stats


def _find_price_drops(db, threshold_pct: float) -> list[dict[str, Any]]:
    """Busca SKUs seed com queda de preço recente ≥ threshold."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()

    # Busca SKUs seed ativos
    skus_resp = (
        db.table("material_sku")
        .select("id,canonical_name,category,unit")
        .eq("seed", True)
        .execute()
    )
    skus = skus_resp.data or []

    drops = []
    for sku in skus:
        sku_id = sku["id"]

        # Listings ativos desse SKU
        listings_resp = (
            db.table("material_listing")
            .select("id,supplier_id,url")
            .eq("sku_id", sku_id)
            .eq("is_active", True)
            .execute()
        )
        listing_ids = [r["id"] for r in (listings_resp.data or [])]
        if not listing_ids:
            continue

        # Preço mais recente (últimas 25h) — snapshot atual
        latest_resp = (
            db.table("material_price_history")
            .select("price,listing_id,collected_at")
            .in_("listing_id", listing_ids)
            .eq("is_available", True)
            .gte("collected_at", yesterday)
            .order("collected_at", desc=True)
            .limit(1)
            .execute()
        )
        if not latest_resp.data:
            continue

        latest = latest_resp.data[0]
        current_price = latest["price"]
        if not current_price or current_price <= 0:
            continue

        # Mínimo nos últimos 30d (excl. snapshot atual)
        history_resp = (
            db.table("material_price_history")
            .select("price,collected_at")
            .in_("listing_id", listing_ids)
            .eq("is_available", True)
            .gte("collected_at", cutoff)
            .lt("collected_at", yesterday)
            .order("price", desc=False)
            .limit(1)
            .execute()
        )

        if not history_resp.data:
            # Sem histórico anterior — sem base de comparação
            continue

        prev_min_price = history_resp.data[0]["price"]
        if not prev_min_price or prev_min_price <= 0:
            continue

        drop_pct = (prev_min_price - current_price) / prev_min_price * 100
        if drop_pct >= threshold_pct:
            # Busca nome do fornecedor para contexto
            supplier_info = _get_supplier_for_listing(db, latest["listing_id"])
            drops.append({
                "canonical_name": sku["canonical_name"],
                "category": sku["category"],
                "unit": sku["unit"],
                "current_price": current_price,
                "prev_min_price": prev_min_price,
                "drop_pct": drop_pct,
                "supplier_name": supplier_info.get("name", "?"),
                "url": supplier_info.get("url"),
            })

    return drops


def _get_supplier_for_listing(db, listing_id: int) -> dict:
    resp = (
        db.table("material_listing")
        .select("url,supplier_id,material_supplier(name)")
        .eq("id", listing_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return {}
    row = resp.data[0]
    return {
        "url": row.get("url"),
        "name": (row.get("material_supplier") or {}).get("name", "?"),
    }


def _format_alert(drop: dict, threshold_pct: float) -> str:
    arrow = "🔻"
    lines = [
        f"{arrow} *Queda de preço — Materiais BM3*",
        "",
        f"*{drop['canonical_name']}*",
        f"Categoria: {drop['category']} | Unidade: {drop['unit']}",
        "",
        f"Preço atual: *R$ {drop['current_price']:.2f}*",
        f"Mínimo 30d anterior: R$ {drop['prev_min_price']:.2f}",
        f"Queda: *{drop['drop_pct']:.1f}%* \\(≥{threshold_pct:.0f}% threshold\\)",
        "",
        f"Fornecedor: {drop['supplier_name']}",
    ]
    if drop.get("url"):
        lines.append(f"[Ver produto]({drop['url']})")

    return "\n".join(lines)


def _send_telegram(text: str) -> None:
    url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)
    resp = httpx.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": False,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram HTTP {resp.status_code}: {resp.text[:200]}")


def main() -> None:
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Alertas de queda de preço de materiais.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD_PCT,
        help=f"% de queda para disparar alerta (padrão: {DEFAULT_THRESHOLD_PCT})",
    )
    args = parser.parse_args()

    stats = run_price_alerts(threshold_pct=args.threshold)
    print(stats, file=sys.stdout)
    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

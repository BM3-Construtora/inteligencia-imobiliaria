"""Reporter — generates weekly market intelligence reports via Telegram."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client
from src.llm import generate_market_report, GEMINI_API_KEY

logger = logging.getLogger(__name__)


def run_weekly_report() -> dict[str, int]:
    """Generate and send a weekly market report via Telegram."""
    db = get_client()
    stats = {"generated": 0, "sent": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "reporter", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        data = _gather_report_data(db)

        report_text = None
        if GEMINI_API_KEY:
            report_text = generate_market_report(data)

        # Fallback to static report if LLM fails or is not available
        if not report_text:
            report_text = _build_static_report(data)

        stats["generated"] = 1

        if report_text:
            # Add header
            today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
            full_message = (
                f"*RELATORIO SEMANAL — MariliaBot*\n"
                f"_{today}_\n\n"
                f"{report_text}\n\n"
                f"---\n"
                f"_Dados de {data['total_listings']} imoveis em {data['total_neighborhoods']} bairros_"
            )

            _send_telegram(full_message)
            stats["sent"] = 1
            logger.info("[reporter] Weekly report sent")

        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[reporter] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _gather_report_data(db: Any) -> dict[str, Any]:
    """Gather data for the weekly report."""
    # Total listings
    total = db.table("listings").select("id", count="exact").eq("is_active", True).execute()

    # Total land
    land = db.table("listings").select("id", count="exact").eq("is_active", True).eq("property_type", "land").execute()

    # Neighborhoods count
    neighs = db.table("neighborhoods").select("id", count="exact").execute()

    # Top opportunities this week
    opps = (
        db.table("opportunities")
        .select("score, reason, listing:listings(neighborhood, sale_price, total_area, price_per_m2)")
        .order("score", desc=True)
        .limit(5)
        .execute()
    )

    top_opps = []
    for o in opps.data:
        l = o.get("listing")
        if isinstance(l, list):
            l = l[0] if l else {}
        top_opps.append({
            "score": o["score"],
            "neighborhood": l.get("neighborhood", "?") if l else "?",
            "price": l.get("sale_price") if l else None,
            "area": l.get("total_area") if l else None,
            "price_m2": l.get("price_per_m2") if l else None,
        })

    # Market snapshots — latest for land
    snap = (
        db.table("market_snapshots")
        .select("*")
        .is_("neighborhood", "null")
        .eq("property_type", "land")
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    land_snapshot = snap.data[0] if snap.data else {}

    # Top neighborhoods by land count
    top_neighs = (
        db.table("neighborhoods")
        .select("name, total_land, avg_price_m2_land")
        .gt("total_land", 0)
        .order("total_land", desc=True)
        .limit(5)
        .execute()
    )

    return {
        "total_listings": total.count or 0,
        "total_land": land.count or 0,
        "total_neighborhoods": neighs.count or 0,
        "top_opportunities": top_opps,
        "land_snapshot": land_snapshot,
        "top_neighborhoods": top_neighs.data,
    }


def _build_static_report(data: dict[str, Any]) -> str:
    """Build a static report without LLM (fallback)."""
    lines = []

    snap = data.get("land_snapshot", {})
    lines.append("*Mercado de Terrenos*")
    lines.append(f"Total: {data['total_land']} terrenos ativos")
    if snap:
        avg = snap.get("avg_price")
        med = snap.get("median_price")
        if avg:
            lines.append(f"Preco medio: R$ {float(avg):,.0f}")
        if med:
            lines.append(f"Preco mediano: R$ {float(med):,.0f}")
        dom = snap.get("avg_days_on_market")
        if dom:
            lines.append(f"Tempo medio no mercado: {dom} dias")

    lines.append("")
    lines.append("*Top 5 Oportunidades*")
    for i, o in enumerate(data.get("top_opportunities", []), 1):
        price = f"R$ {float(o['price']):,.0f}" if o.get("price") else "?"
        area = f"{float(o['area']):,.0f}m²" if o.get("area") else "?"
        lines.append(f"{i}. {o['neighborhood']} — {price} | {area} (score {o['score']:.0f})")

    lines.append("")
    lines.append("*Bairros com mais terrenos*")
    for n in data.get("top_neighborhoods", []):
        pm2 = f"R$ {float(n['avg_price_m2_land']):,.0f}/m²" if n.get("avg_price_m2_land") else "?"
        lines.append(f"- {n['name']}: {n['total_land']} terrenos ({pm2})")

    return "\n".join(lines)


def _send_telegram(text: str) -> None:
    """Send report via Telegram."""
    import os
    import httpx

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.error("[reporter] Telegram not configured")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = httpx.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=15)
    resp.raise_for_status()


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
        "items_processed": stats["generated"],
        "items_created": stats["sent"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

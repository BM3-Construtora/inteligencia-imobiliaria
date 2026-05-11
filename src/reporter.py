"""Reporter — generates weekly market intelligence reports via Telegram."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client


_TIER_LABEL = {
    "terreno_economico": "econômico",
    "terreno_medio": "médio",
    "terreno_grande": "grande",
    "terreno_premium": "premium",
}


def _fmt_price(v: Any) -> str:
    if not v:
        return "?"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "?"
    if n >= 1_000_000:
        return f"R${n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"R${n/1000:.0f}k"
    return f"R${n:.0f}"


def _fmt_area(v: Any) -> str:
    if not v:
        return "?"
    try:
        return f"{float(v):.0f}m²"
    except (TypeError, ValueError):
        return "?"


def _short_neigh(name: str, max_len: int = 28) -> str:
    if not name:
        return "?"
    n = (
        name.replace("Residencial ", "Res. ")
        .replace("Jardim ", "Jd. ")
        .replace("Parque ", "Pq. ")
        .replace("Loteamento ", "Lot. ")
        .replace("Núcleo Habitacional ", "N.H. ")
        .replace("Nucleo Habitacional ", "N.H. ")
        .replace("Distrito ", "Dist. ")
        .replace("Vila ", "Vl. ")
        .replace("Conjunto ", "Conj. ")
        .replace("Habitacional ", "Hab. ")
        .replace("Fazenda ", "Faz. ")
    )
    return n if len(n) <= max_len else n[: max_len - 1] + "…"

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
        report_text = _build_report(data)
        stats["generated"] = 1

        if report_text:
            _send_telegram(report_text)
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

    # Top opportunities this week (top 10 for weekly consolidated report)
    opps = (
        db.table("opportunities")
        .select("score, reason, listing:listings(neighborhood, sale_price, total_area, price_per_m2, url, is_mcmv, market_tier)")
        .order("score", desc=True)
        .limit(10)
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
            "url": l.get("url") if l else None,
            "is_mcmv": l.get("is_mcmv") if l else False,
            "tier": l.get("market_tier") if l else None,
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

    # Absorption data — hottest neighborhoods
    hot_neighs = (
        db.table("neighborhoods")
        .select("name, absorption_rate, months_of_inventory, market_heat_score, total_listings")
        .not_.is_("market_heat_score", "null")
        .order("market_heat_score", desc=True)
        .limit(5)
        .execute()
    )

    # Market indices (SINAPI, MCMV demand)
    indices = (
        db.table("market_indices")
        .select("metric_name, metric_value, metadata")
        .eq("region", "marilia")
        .execute()
    )
    indices_map = {i["metric_name"]: i["metric_value"] for i in (indices.data or [])}

    # Viable opportunities (viability studies)
    viable = (
        db.table("viability_studies")
        .select("scenario, outputs, listing:listings(neighborhood, sale_price, total_area)")
        .eq("is_viable", True)
        .order("id", desc=True)
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
        "hot_neighborhoods": hot_neighs.data or [],
        "indices": indices_map,
        "viable_projects": viable.data or [],
    }


def _build_report(data: dict[str, Any]) -> str:
    """Build a compact weekly report (HTML parse mode)."""
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    snap = data.get("land_snapshot", {}) or {}
    lines: list[str] = []

    lines.append(f"<b>📊 Semanal {today}</b>")

    # --- One-line market summary ---
    parts = [f"{data['total_land']} terrenos"]
    if snap.get("median_price"):
        parts.append(f"mediano {_fmt_price(snap['median_price'])}")
    if snap.get("avg_price_m2"):
        parts.append(f"R${float(snap['avg_price_m2']):,.0f}/m²".replace(",", "."))
    if snap.get("avg_days_on_market"):
        parts.append(f"{int(float(snap['avg_days_on_market']))}d no mercado")
    lines.append(" · ".join(parts))

    # --- Top 5 opportunities with URL ---
    opps = data.get("top_opportunities", []) or []
    opps_with_url = [o for o in opps if o.get("url")][:5]
    if not opps_with_url:
        opps_with_url = opps[:5]

    if opps_with_url:
        lines.append("")
        lines.append("<b>🏆 TOP 5</b>")
        for i, o in enumerate(opps_with_url, 1):
            neigh = _short_neigh(o.get("neighborhood") or "?")
            price = _fmt_price(o.get("price"))
            area = _fmt_area(o.get("area"))
            mcmv = " · MCMV" if o.get("is_mcmv") else ""
            tier_raw = o.get("tier") or ""
            tier_label = _TIER_LABEL.get(tier_raw, "")
            tier = f" · {tier_label}" if tier_label else ""
            score = f"{float(o['score']):.0f}" if o.get("score") is not None else "?"
            url = o.get("url")
            if url:
                lines.append(
                    f"{i}. <a href=\"{url}\">{neigh}</a> · {price} · {area}{mcmv}{tier} · <b>{score}</b>"
                )
            else:
                lines.append(f"{i}. {neigh} · {price} · {area}{mcmv}{tier} · <b>{score}</b>")

    # --- Hot neighborhoods (1 line) ---
    hot = data.get("hot_neighborhoods", []) or []
    if hot:
        names = ", ".join(n["name"] for n in hot[:3] if n.get("name"))
        if names:
            lines.append("")
            lines.append(f"🔥 Quentes: {names}")

    # --- Focus pick ---
    if opps_with_url:
        top = opps_with_url[0]
        focus_name = _short_neigh(top.get("neighborhood") or "")
        if focus_name and focus_name != "?":
            lines.append(f"💡 Foco: {focus_name}")

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
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
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

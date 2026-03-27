"""Database queries for Telegram bot responses."""

from __future__ import annotations

import json
from typing import Any

from src.db import get_client
from src.viability import simulate_project, MCMV_FAIXAS


def get_top_opportunities(limit: int = 10) -> str:
    """Get top scored opportunities formatted for Telegram."""
    db = get_client()
    result = (
        db.table("opportunities")
        .select("score, reason, listing:listings(neighborhood, sale_price, total_area, price_per_m2, url, is_mcmv, market_tier)")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )

    if not result.data:
        return "Nenhuma oportunidade encontrada."

    lines = [f"🏆 *Top {limit} Oportunidades*\n"]
    for i, o in enumerate(result.data, 1):
        l = o.get("listing")
        if isinstance(l, list):
            l = l[0] if l else {}
        if not l:
            continue

        price = f"R$ {float(l.get('sale_price') or 0):,.0f}"
        area = f"{float(l.get('total_area') or 0):,.0f}m²"
        neigh = l.get("neighborhood", "?")
        mcmv = " ✅MCMV" if l.get("is_mcmv") else ""
        tier = f" ({l['market_tier']})" if l.get("market_tier") else ""
        url = l.get("url", "")

        lines.append(f"{i}. *{neigh}* — {price} | {area}{mcmv}{tier}")
        lines.append(f"   Score: {o['score']:.0f}/100")
        if url:
            lines.append(f"   {url}")
        lines.append("")

    return "\n".join(lines)


def get_neighborhood_analysis(name: str) -> str:
    """Get detailed analysis of a neighborhood."""
    db = get_client()

    # Try exact match first, then fuzzy
    result = db.table("neighborhoods").select("*").ilike("name", f"%{name}%").limit(1).execute()

    if not result.data:
        return f"Bairro '{name}' nao encontrado. Tente outro nome."

    n = result.data[0]
    lines = [f"📍 *{n['name']}*\n"]

    lines.append(f"Total imoveis: {n.get('total_listings', 0)}")
    lines.append(f"Terrenos: {n.get('total_land', 0)} | Casas: {n.get('total_houses', 0)}")

    if n.get("avg_price_m2_land"):
        lines.append(f"Preco/m² terreno: R$ {float(n['avg_price_m2_land']):,.0f}")
    if n.get("avg_price_m2_house"):
        lines.append(f"Preco/m² casa: R$ {float(n['avg_price_m2_house']):,.0f}")

    heat = n.get("market_heat_score")
    if heat is not None:
        emoji = "🔥" if heat >= 70 else "🟡" if heat >= 40 else "❄️"
        lines.append(f"Calor do mercado: {emoji} {heat}/100")

    dom = n.get("avg_days_on_market")
    if dom is not None:
        lines.append(f"Tempo medio no mercado: {dom} dias")

    absorption = n.get("absorption_rate")
    if absorption is not None:
        lines.append(f"Absorcao: {absorption:.1f}%/mes")

    months = n.get("months_of_inventory")
    if months is not None:
        lines.append(f"Meses de estoque: {months:.1f}")

    risk = n.get("avg_risk_score")
    if risk is not None:
        emoji = "🟢" if risk < 2.5 else "🟡" if risk < 3.5 else "🔴"
        lines.append(f"Risco medio: {emoji} {risk:.1f}/5")

    tiers = n.get("total_listings_by_tier") or {}
    if tiers:
        lines.append(f"\n*Classificacao:*")
        for tier, count in sorted(tiers.items(), key=lambda x: -x[1]):
            lines.append(f"  {tier}: {count}")

    # Top opportunities in this neighborhood
    opps = (
        db.table("opportunities")
        .select("score, listing:listings!inner(neighborhood, sale_price, total_area, url)")
        .order("score", desc=True)
        .limit(3)
        .execute()
    )
    neigh_opps = []
    for o in (opps.data or []):
        l = o.get("listing")
        if isinstance(l, list):
            l = l[0] if l else {}
        if l and l.get("neighborhood", "").lower() == n["name"].lower():
            neigh_opps.append(o)

    if neigh_opps:
        lines.append(f"\n*Melhores terrenos:*")
        for o in neigh_opps[:3]:
            l = o["listing"] if not isinstance(o["listing"], list) else o["listing"][0]
            price = f"R$ {float(l.get('sale_price') or 0):,.0f}"
            lines.append(f"  Score {o['score']:.0f} — {price}")

    return "\n".join(lines)


def get_market_summary() -> str:
    """Get overall market summary."""
    db = get_client()

    total = db.table("listings").select("id", count="exact").eq("is_active", True).execute()
    land = db.table("listings").select("id", count="exact").eq("is_active", True).eq("property_type", "land").execute()
    opps = db.table("opportunities").select("id", count="exact").execute()

    indices = db.table("market_indices").select("metric_name, metric_value").eq("region", "marilia").execute()
    idx = {i["metric_name"]: i["metric_value"] for i in (indices.data or [])}

    lines = ["📊 *Mercado Imobiliario — Marilia/SP*\n"]
    lines.append(f"Total imoveis: {total.count or 0}")
    lines.append(f"Terrenos ativos: {land.count or 0}")
    lines.append(f"Oportunidades: {opps.count or 0}")

    sinapi = idx.get("sinapi_custo_m2")
    if sinapi:
        lines.append(f"\nSINAPI/m² (SP): R$ {float(sinapi):,.0f}")

    pop = idx.get("populacao")
    if pop:
        lines.append(f"Populacao: {int(pop):,}")

    deficit = idx.get("deficit_habitacional_estimado")
    if deficit:
        lines.append(f"Deficit habitacional: {int(deficit):,} unidades")

    demanda = idx.get("demanda_mcmv_faixa2_anual")
    if demanda:
        lines.append(f"Demanda MCMV F2: {int(demanda)} un/ano")

    # Hot neighborhoods
    hot = (
        db.table("neighborhoods")
        .select("name, market_heat_score")
        .not_.is_("market_heat_score", "null")
        .order("market_heat_score", desc=True)
        .limit(5)
        .execute()
    )
    if hot.data:
        lines.append(f"\n*Bairros mais quentes:*")
        for n in hot.data:
            lines.append(f"  {n['name']}: {n['market_heat_score']}/100")

    return "\n".join(lines)


def simulate_viability_text(price: float, area: float) -> str:
    """Simulate viability for a land parcel and format for Telegram."""
    lines = [f"🧮 *Viabilidade — Terreno R$ {price:,.0f} | {area:,.0f}m²*\n"]

    any_viable = False
    for key, faixa in MCMV_FAIXAS.items():
        result = simulate_project(price, area, key)
        if not result:
            continue

        out = result["outputs"]
        go = "✅ GO" if result["is_viable"] else "❌ NO-GO"
        lines.append(f"*{result['scenario']}* — {go}")
        lines.append(f"  Unidades: {out['unidades']} | VGV: R$ {out['vgv']:,.0f}")
        lines.append(f"  Margem: {out['margem_liquida_pct']:.1f}% | ROI: {out['roi_pct']:.1f}%")
        lines.append(f"  Payback: {out['payback_anos']:.1f} anos | TIR: {out['tir_anual_pct']:.1f}%")
        lines.append(f"  Investimento: R$ {out['investimento_total']:,.0f}")
        lines.append("")

        if result["is_viable"]:
            any_viable = True

    if not any_viable:
        lines.append("⚠️ Nenhum cenario viavel para esse terreno.")

    return "\n".join(lines)


def get_market_context_for_ai() -> str:
    """Build a compact context string for LLM conversations."""
    db = get_client()

    indices = db.table("market_indices").select("metric_name, metric_value").eq("region", "marilia").execute()
    idx = {i["metric_name"]: i["metric_value"] for i in (indices.data or [])}

    total = db.table("listings").select("id", count="exact").eq("is_active", True).execute()
    land = db.table("listings").select("id", count="exact").eq("is_active", True).eq("property_type", "land").execute()

    hot = (
        db.table("neighborhoods")
        .select("name, market_heat_score, avg_price_m2_land, total_listings")
        .not_.is_("market_heat_score", "null")
        .order("market_heat_score", desc=True)
        .limit(10)
        .execute()
    )

    top_opps = (
        db.table("opportunities")
        .select("score, listing:listings(neighborhood, sale_price, total_area)")
        .order("score", desc=True)
        .limit(5)
        .execute()
    )

    context = f"""Dados atuais do mercado de Marilia-SP:
- Total imoveis ativos: {total.count or 0}
- Terrenos ativos: {land.count or 0}
- SINAPI custo/m² (SP): R$ {idx.get('sinapi_custo_m2', '?')}
- Populacao: {int(idx.get('populacao', 247000)):,}
- Deficit habitacional: {int(idx.get('deficit_habitacional_estimado', 13000)):,}
- Demanda MCMV F2/ano: {int(idx.get('demanda_mcmv_faixa2_anual', 565))}
- Renda media domiciliar: R$ {int(idx.get('renda_media_domiciliar', 5000)):,}

Bairros mais quentes (heat score 0-100):
"""
    for n in (hot.data or []):
        pm2 = f"R$ {float(n['avg_price_m2_land']):,.0f}/m²" if n.get("avg_price_m2_land") else "?"
        context += f"  {n['name']}: heat={n['market_heat_score']}, {n['total_listings']} listings, {pm2}\n"

    context += "\nTop 5 oportunidades de terrenos:\n"
    for o in (top_opps.data or []):
        l = o.get("listing")
        if isinstance(l, list):
            l = l[0] if l else {}
        if l:
            context += f"  Score {o['score']:.0f}: {l.get('neighborhood','?')} R$ {float(l.get('sale_price') or 0):,.0f} {float(l.get('total_area') or 0):.0f}m²\n"

    return context

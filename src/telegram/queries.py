"""Database queries for Telegram bot responses."""

from __future__ import annotations

import json
from typing import Any

from src.db import get_client
from src.viability import simulate_project, MCMV_FAIXAS

_TIER_EMOJI = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}


def _brl(v: Any) -> str:
    try:
        return f"R$ {float(v or 0):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


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


def get_undervalued_text(limit: int = 10) -> str:
    """Imóveis subprecificados pelo AVM (pedido abaixo do P25). Para /subprecificados."""
    db = get_client()
    try:
        result = (
            db.table("avm_predictions")
            .select(
                "listing_id, actual_price, p25, p50, mispricing_pct, shap_summary, "
                "listing:listings!inner(neighborhood, total_area, url, is_active)"
            )
            .eq("is_undervalued", True)
            .order("mispricing_pct", desc=True)
            .limit(limit * 3)
            .execute()
        )
    except Exception:
        return "Avaliação de subprecificados indisponível no momento."

    lines = [f"🔽 *Top {limit} subprecificados* (pedido abaixo do P25 do AVM)\n"]
    shown = 0
    for r in result.data or []:
        l = r.get("listing")
        if isinstance(l, list):
            l = l[0] if l else {}
        if not l or not l.get("is_active"):
            continue

        misp = float(r.get("mispricing_pct") or 0)
        neigh = l.get("neighborhood") or "?"
        area = l.get("total_area")
        area_s = f"{float(area):,.0f}m²".replace(",", ".") if area else "?"
        url = l.get("url") or ""

        shown += 1
        lines.append(f"{shown}. *{neigh}* — {area_s} | 🔽 {misp:.0f}% abaixo do justo")
        lines.append(f"   Pedido {_brl(r.get('actual_price'))} vs justo P50 {_brl(r.get('p50'))}")
        summ = (r.get("shap_summary") or "").strip()
        if summ:
            lines.append(f"   _{summ[:140]}_")
        if url:
            lines.append(f"   {url}")
        lines.append("")
        if shown >= limit:
            break

    if shown == 0:
        return "Nenhum imóvel subprecificado agora (nenhum pedido abaixo do P25 do AVM)."
    return "\n".join(lines)


def get_radar_text(neighborhood: str | None = None, limit: int = 8) -> str:
    """Radar de lançamentos: pipeline competitivo (alvarás/EIV) + sinais de upzoning.

    Alvará de aprovação aparece 18-36 meses antes do habite-se; EIV antes do alvará;
    sinais de plano diretor/CMDU antes de tudo. É o pipeline mais adiantado que existe.
    """
    db = get_client()
    escopo = f" — {neighborhood}" if neighborhood else ""
    lines = [f"📡 *Radar de lançamentos{escopo}*\n"]

    # 1) Pipeline competitivo (radar_concorrencia)
    lines.append("*🏗 Pipeline competitivo* (alvarás/EIV, 24 meses)")
    try:
        q = db.table("radar_concorrencia").select(
            "tipo_sinal, publication_date, requerente, neighborhood, area_m2, unidades, subtipo, resultado"
        )
        if neighborhood:
            q = q.ilike("neighborhood", f"%{neighborhood}%")
        rows = (q.order("publication_date", desc=True).limit(limit).execute()).data or []
    except Exception:
        rows = []

    if rows:
        for r in rows:
            emoji = "🏢" if r.get("tipo_sinal") == "eiv" else "🏗"
            data = str(r.get("publication_date") or "")[:10]
            req = r.get("requerente") or "requerente não informado"
            bairro = r.get("neighborhood") or "?"
            area = r.get("area_m2")
            area_s = f" | {float(area):,.0f}m²".replace(",", ".") if area else ""
            und = r.get("unidades")
            und_s = f" | {und}u" if und else ""
            extra = r.get("resultado") or r.get("subtipo") or ""
            extra_s = f" ({extra})" if extra else ""
            lines.append(f"{emoji} {data} *{bairro}* — {req}{area_s}{und_s}{extra_s}")
    else:
        lines.append("_Nenhum alvará/EIV recente" + (f" em {neighborhood}." if neighborhood else ".") + "_")
    lines.append("")

    # 2) Sinais de upzoning (radar_upzoning)
    lines.append("*📈 Sinais de upzoning* (rezoneamento antecipado)")
    try:
        q2 = db.table("radar_upzoning").select(
            "bairro, total_sinais, ultimo_sinal, tem_plano_diretor, tem_audiencia_publica"
        )
        if neighborhood:
            q2 = q2.ilike("bairro", f"%{neighborhood}%")
        ups = (q2.limit(limit).execute()).data or []
    except Exception:
        ups = []

    if ups:
        for u in ups:
            bairro = u.get("bairro") or "?"
            n = u.get("total_sinais") or 0
            ult = str(u.get("ultimo_sinal") or "")[:10]
            flags = []
            if u.get("tem_plano_diretor"):
                flags.append("PD")
            if u.get("tem_audiencia_publica"):
                flags.append("audiência")
            flags_s = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"• *{bairro}* — {n} sinal(is), últ. {ult}{flags_s}")
    else:
        lines.append("_Nenhum sinal de upzoning" + (f" em {neighborhood}." if neighborhood else ".") + "_")

    # 3) Novos loteamentos aprovados (futura oferta de terreno)
    lines.append("")
    lines.append("*🧭 Novos loteamentos aprovados* (futura oferta)")
    try:
        lq = db.table("parcelamento_solo_marilia").select(
            "titulo, tipo, issue_date, neighborhood"
        ).not_.is_("issue_date", "null")
        if neighborhood:
            lq = lq.ilike("neighborhood", f"%{neighborhood}%")
        lot = (lq.order("issue_date", desc=True).limit(limit * 4).execute()).data or []
    except Exception:
        lot = []

    if lot:
        nomeados = [x for x in lot if x.get("titulo")]
        anon = [x for x in lot if not x.get("titulo")]
        # Nomeados primeiro (mais acionável), completa com anônimos recentes.
        display = (nomeados + anon)[:limit]
        for x in display:
            data = str(x.get("issue_date") or "")[:10]
            nome = x.get("titulo") or f"({x.get('tipo') or 'parcelamento'} sem nome)"
            bairro = x.get("neighborhood")
            bairro_s = f" — {bairro}" if bairro else ""
            lines.append(f"• {data} *{nome}*{bairro_s}")
    else:
        lines.append("_Nenhum loteamento recente" + (f" em {neighborhood}." if neighborhood else ".") + "_")

    return "\n".join(lines)


def get_construtora_rating_text(nome_or_cnpj: str) -> str:
    """Rating público de uma construtora (dados DOM-MAR + CNPJ). Para /construtora."""
    from src.rating_construtoras import get_construtora_rating

    r = get_construtora_rating(nome_or_cnpj)
    if not r:
        return (
            f"🏗 Construtora '{nome_or_cnpj}' não encontrada no radar público.\n"
            "_Base: alvarás e habite-se do Diário Oficial de Marília; "
            "pode não ter registros nos últimos anos._"
        )

    nome = r.get("razao_social") or r.get("nome") or nome_or_cnpj
    tier = (r.get("tier") or "").upper()
    emoji = _TIER_EMOJI.get(tier, "⚪")
    score = r.get("score_geral")

    lines = [f"🏗 *{nome}*"]
    if tier and score is not None:
        lines.append(f"{emoji} Tier *{tier}* — score {float(score):.0f}/100")
    elif score is not None:
        lines.append(f"Score geral: {float(score):.0f}/100")

    subs = []
    for label, key in (("Entrega", "score_entrega"), ("Prazo", "score_prazo"), ("Volume", "score_volume")):
        v = r.get(key)
        if v is not None:
            subs.append(f"{label} {float(v):.0f}")
    if subs:
        lines.append("   " + " | ".join(subs))

    alvaras = r.get("total_alvaras") or 0
    habite = r.get("total_habite_se") or 0
    if alvaras or habite:
        lines.append(f"Obras: {habite} concluídas de {alvaras} alvarás")
    pend = r.get("alvaras_sem_habite_se") or 0
    if pend:
        lines.append(f"Em aberto (sem habite-se): {pend}")

    tempo = r.get("tempo_medio_obra_dias")
    if tempo:
        lines.append(f"Tempo médio de obra: {float(tempo):.0f} dias (~{float(tempo) / 30:.0f} meses)")

    bairros = r.get("bairros_atuacao") or []
    if bairros:
        shown = ", ".join(bairros[:5])
        extra = f" (+{len(bairros) - 5})" if len(bairros) > 5 else ""
        lines.append(f"Atuação: {shown}{extra}")
    if r.get("bairro_principal"):
        lines.append(f"Bairro principal: {r['bairro_principal']}")

    cnpj_bits = []
    if r.get("situacao_cadastral"):
        cnpj_bits.append(str(r["situacao_cadastral"]))
    if r.get("porte"):
        cnpj_bits.append(str(r["porte"]))
    if r.get("capital_social"):
        cnpj_bits.append(f"capital R$ {float(r['capital_social']):,.0f}".replace(",", "."))
    if cnpj_bits:
        lines.append(f"CNPJ: {' · '.join(cnpj_bits)}")

    flags = []
    if r.get("tem_embargo"):
        flags.append("embargo")
    if r.get("tem_processo_tjsp"):
        flags.append("processo TJSP")
    risco = r.get("cnpj_risco")
    if risco and str(risco).lower() not in ("baixo", "none", ""):
        flags.append(f"risco CNPJ {risco}")
    if flags:
        lines.append(f"🔴 Sinais de risco: {', '.join(flags)}")

    if r.get("ultima_atividade_date"):
        lines.append(f"_Última atividade: {r['ultima_atividade_date']}_")

    lines.append("")
    lines.append("_Base: dados públicos DOM-MAR + Receita Federal. Referência, não due diligence formal._")
    return "\n".join(lines)


def get_bairro_construtoras(neighborhood: str, limit: int = 3) -> list[str]:
    """Top construtoras atuando num bairro (view construtoras_por_bairro).

    Retorna linhas markdown compactas para embutir em outras respostas (ex: ficha).
    Best-effort: qualquer erro/ausência de dados devolve lista vazia.
    """
    if not neighborhood:
        return []
    db = get_client()
    try:
        result = (
            db.table("construtoras_por_bairro")
            .select("construtora, alvaras_no_bairro")
            .ilike("neighborhood", f"%{neighborhood}%")
            .order("alvaras_no_bairro", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        return []

    lines: list[str] = []
    for row in result.data or []:
        nome = row.get("construtora") or "?"
        n_alv = row.get("alvaras_no_bairro") or 0
        tier_mark = ""
        try:
            rt = (
                db.table("construtoras_rating")
                .select("tier")
                .ilike("nome", f"%{nome}%")
                .limit(1)
                .execute()
            )
            if rt.data and rt.data[0].get("tier"):
                t = str(rt.data[0]["tier"]).upper()
                tier_mark = f" {_TIER_EMOJI.get(t, '')}{t}"
        except Exception:
            pass
        lines.append(f"• {nome}{tier_mark} — {n_alv} alvará(s) em 36 meses")
    return lines


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


def get_ficha_query(text: str) -> str:
    """Generate full land ficha (Track B) — wraps generate_ficha for Telegram."""
    from src.telegram.ficha import generate_ficha
    return generate_ficha(text)


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

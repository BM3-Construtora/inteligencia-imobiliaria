"""Ficha de Terreno — Track B.

Recebe endereço/CEP/coord/URL e devolve markdown completo para Telegram:
AVM, comps próximos, viabilidade 4 faixas MCMV, riscos, veredito + teto sugerido.

Sistema RECOMENDA apenas — decisão final é do usuário.
"""

from __future__ import annotations

import logging
import math
import re
import time
from functools import lru_cache
from typing import Any, Optional

import httpx

from src.db import get_client
from src.telegram.avm import quick_avm
from src.viability import MCMV_FAIXAS, simulate_project

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
TOTAL_TIMEOUT_S = 30.0
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "MariliaBot/1.0 (ficha)"}
NOMINATIM_VIEWBOX = "-50.0,-22.4,-49.8,-22.1"
MARILIA_CENTER = (-22.21, -49.95)
SEARCH_RADIUS_KM = 1.0
RECOMENDA_MIN_MARGEM = 15.0
RECOMENDA_MAX_PAYBACK = 4.0


# ----------------------------------------------------------------------
# Query parsing
# ----------------------------------------------------------------------
CEP_RE = re.compile(r"\b(\d{5})-?(\d{3})\b")
COORD_RE = re.compile(r"^\s*(-?\d{1,3}\.\d+)\s*[,;\s]\s*(-?\d{1,3}\.\d+)\s*$")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
AREA_HINT_RE = re.compile(r"(\d{2,5})\s*m\s*[²2]?", re.IGNORECASE)


def _classify_query(text: str) -> tuple[str, str]:
    """Return (kind, normalized_value). kind in {url, coord, cep, address}."""
    t = (text or "").strip()
    if not t:
        return "address", ""
    if URL_RE.search(t):
        return "url", URL_RE.search(t).group(0)
    m = COORD_RE.match(t)
    if m:
        return "coord", f"{m.group(1)},{m.group(2)}"
    m = CEP_RE.search(t)
    if m:
        return "cep", f"{m.group(1)}-{m.group(2)}"
    return "address", t


def _extract_area(text: str) -> Optional[float]:
    """Detect area hint like '250m²' in the user query."""
    m = AREA_HINT_RE.search(text or "")
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v if 30 <= v <= 50000 else None
    except ValueError:
        return None


def _extract_price(text: str) -> Optional[float]:
    """Detect price hint like 'R$ 200000' or '200k'."""
    if not text:
        return None
    m = re.search(r"r\$?\s*([\d\.\,]+)\s*(k|mil|m|milh|milhão|milhao)?", text, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace(",", ".")
    try:
        v = float(raw)
    except ValueError:
        return None
    suf = (m.group(2) or "").lower()
    if suf in ("k", "mil"):
        v *= 1_000
    elif suf in ("m", "milh", "milhão", "milhao"):
        v *= 1_000_000
    return v if v >= 10_000 else None


# ----------------------------------------------------------------------
# Geocoding (in-memory LRU cache)
# ----------------------------------------------------------------------
@lru_cache(maxsize=256)
def _geocode_address(query: str) -> Optional[tuple[float, float]]:
    """Geocode free-form address via Nominatim. Returns (lat,lng) or None."""
    if not query:
        return None
    params = {
        "q": f"{query}, Marília, SP, Brasil" if "marília" not in query.lower() and "marilia" not in query.lower() else query,
        "format": "json",
        "limit": 1,
        "countrycodes": "br",
        "viewbox": NOMINATIM_VIEWBOX,
        "bounded": "0",
    }
    try:
        resp = httpx.get(NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        lat = float(data[0]["lat"])
        lng = float(data[0]["lon"])
        # Sanity: must be near Marília
        if _haversine(lat, lng, *MARILIA_CENTER) > 50:
            return None
        return lat, lng
    except Exception as exc:
        logger.debug(f"[ficha] geocode failed for '{query}': {exc}")
        return None


@lru_cache(maxsize=256)
def _geocode_cep(cep: str) -> Optional[tuple[float, float, str, str]]:
    """Geocode CEP via ViaCEP + Nominatim. Returns (lat,lng,street,neighborhood)."""
    digits = re.sub(r"\D", "", cep or "")
    if len(digits) != 8:
        return None
    try:
        resp = httpx.get(f"https://viacep.com.br/ws/{digits}/json/", timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("erro"):
            return None
        street = data.get("logradouro") or ""
        neigh = data.get("bairro") or ""
        city = data.get("localidade") or "Marília"
        uf = data.get("uf") or "SP"
        query = ", ".join([p for p in [street, neigh, city, uf, "Brasil"] if p])
        coords = _geocode_address(query)
        if coords:
            return coords[0], coords[1], street, neigh
    except Exception as exc:
        logger.debug(f"[ficha] CEP geocode failed: {exc}")
    return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ----------------------------------------------------------------------
# Reverse-locate neighborhood from coords (best-effort)
# ----------------------------------------------------------------------
def _nearest_neighborhood(db: Any, lat: float, lng: float) -> Optional[str]:
    try:
        result = (
            db.table("listings")
            .select("neighborhood, latitude, longitude")
            .not_.is_("latitude", "null")
            .not_.is_("longitude", "null")
            .not_.is_("neighborhood", "null")
            .limit(2000)
            .execute()
        )
        best_d = float("inf")
        best_n: Optional[str] = None
        for r in result.data or []:
            try:
                d = _haversine(lat, lng, float(r["latitude"]), float(r["longitude"]))
            except (TypeError, ValueError):
                continue
            if d < best_d:
                best_d = d
                best_n = r.get("neighborhood")
        return best_n if best_d <= 2.0 else None
    except Exception:
        return None


# ----------------------------------------------------------------------
# Comps within radius
# ----------------------------------------------------------------------
def _find_comps_radius(
    db: Any, lat: float, lng: float, radius_km: float = SEARCH_RADIUS_KM, limit: int = 30
) -> list[dict[str, Any]]:
    """Listings with coords inside radius_km. Returns sorted by distance asc."""
    try:
        # rough bbox prefilter (~1 degree ≈ 111km)
        d = radius_km / 111.0
        result = (
            db.table("listings")
            .select("id, neighborhood, sale_price, total_area, price_per_m2, "
                    "property_type, url, title, latitude, longitude")
            .eq("is_active", True)
            .gte("latitude", lat - d)
            .lte("latitude", lat + d)
            .gte("longitude", lng - d)
            .lte("longitude", lng + d)
            .not_.is_("sale_price", "null")
            .gt("sale_price", 0)
            .limit(300)
            .execute()
        )
        out: list[dict[str, Any]] = []
        for r in result.data or []:
            try:
                dist = _haversine(lat, lng, float(r["latitude"]), float(r["longitude"]))
            except (TypeError, ValueError):
                continue
            if dist <= radius_km:
                r["_dist_km"] = round(dist, 3)
                out.append(r)
        out.sort(key=lambda x: x["_dist_km"])
        return out[:limit]
    except Exception as exc:
        logger.debug(f"[ficha] comps radius failed: {exc}")
        return []


# ----------------------------------------------------------------------
# Listing URL lookup (when user pastes a listing link)
# ----------------------------------------------------------------------
def _listing_by_url(db: Any, url: str) -> Optional[dict[str, Any]]:
    try:
        result = (
            db.table("listings")
            .select("id, sale_price, total_area, neighborhood, latitude, longitude, "
                    "street, address, zip_code, price_per_m2, property_type, title, url")
            .eq("url", url)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        return None


# ----------------------------------------------------------------------
# Regulatory signals (graceful)
# ----------------------------------------------------------------------
def _fetch_risks(db: Any, neighborhood: Optional[str], lat: float, lng: float) -> list[str]:
    risks: list[str] = []
    try:
        q = db.table("regulatory_signals").select("category, description, severity, neighborhood").limit(50)
        if neighborhood:
            q = q.ilike("neighborhood", neighborhood)
        result = q.execute()
        for r in result.data or []:
            cat = r.get("category") or "Risco"
            desc = r.get("description") or ""
            sev = r.get("severity") or ""
            sev_mark = "🔴" if str(sev).lower() in ("high", "alto") else "🟡"
            risks.append(f"{sev_mark} *{cat}*: {desc}")
    except Exception as exc:
        logger.debug(f"[ficha] regulatory_signals unavailable: {exc}")
    return risks


# ----------------------------------------------------------------------
# Main entry
# ----------------------------------------------------------------------
def generate_ficha(query: str) -> str:
    """Generate full markdown ficha for a land query. Always returns a string."""
    started = time.monotonic()

    def time_left() -> float:
        return max(0.0, TOTAL_TIMEOUT_S - (time.monotonic() - started))

    if not query or not query.strip():
        return (
            "❓ Envie um endereço, CEP, coordenada (lat,lng) ou URL de anúncio.\n"
            "Exemplo: `/ficha Rua das Flores, 123, Palmital`"
        )

    db = get_client()

    # --- 1) Parse ---
    kind, value = _classify_query(query)
    user_area = _extract_area(query)
    user_price = _extract_price(query)

    lat: Optional[float] = None
    lng: Optional[float] = None
    neighborhood: Optional[str] = None
    label: str = query.strip()
    matched_listing: Optional[dict[str, Any]] = None

    # --- 2) Geocode / resolve ---
    try:
        if kind == "url":
            matched_listing = _listing_by_url(db, value)
            if matched_listing:
                lat = matched_listing.get("latitude")
                lng = matched_listing.get("longitude")
                neighborhood = matched_listing.get("neighborhood")
                if user_area is None and matched_listing.get("total_area"):
                    user_area = float(matched_listing["total_area"])
                if user_price is None and matched_listing.get("sale_price"):
                    user_price = float(matched_listing["sale_price"])
                label = matched_listing.get("title") or value
            else:
                label = value

        elif kind == "coord":
            try:
                a, b = value.split(",")
                lat, lng = float(a), float(b)
            except ValueError:
                pass

        elif kind == "cep":
            res = _geocode_cep(value)
            if res:
                lat, lng, street, neigh = res
                neighborhood = neigh or None
                label = f"CEP {value}" + (f" — {street}, {neigh}" if street else "")

        else:  # address
            coords = _geocode_address(value)
            if coords:
                lat, lng = coords
    except Exception as exc:
        logger.warning(f"[ficha] parse/geocode error: {exc}")

    if (lat is None or lng is None) and not matched_listing:
        return (
            f"❌ Não consegui localizar `{query}`.\n\n"
            "Tente:\n"
            "• CEP (8 dígitos): `17500-000`\n"
            "• Endereço completo: `Rua X, 123, Bairro`\n"
            "• Coordenada: `-22.21,-49.95`\n"
            "• URL de anúncio cadastrado\n\n"
            "_Recomendação — decisão final é sua._"
        )

    # Try to fill neighborhood by reverse lookup
    if not neighborhood and lat and lng:
        neighborhood = _nearest_neighborhood(db, lat, lng)

    # --- 3) Comps ---
    comps: list[dict[str, Any]] = []
    if lat is not None and lng is not None and time_left() > 5:
        comps = _find_comps_radius(db, lat, lng, SEARCH_RADIUS_KM, limit=20)

    # --- 4) AVM ---
    avm: dict[str, Any] = {"p25": 0, "p50": 0, "p75": 0, "n_comps": 0, "method": "unavailable"}
    if neighborhood and time_left() > 3:
        avm = quick_avm(neighborhood, user_area or 0, db)

    # If neighborhood AVM unavailable, derive from comps in-radius (price_per_m2)
    if avm.get("n_comps", 0) < 3 and comps:
        ppms = [
            float(c["price_per_m2"]) for c in comps
            if c.get("price_per_m2") and float(c["price_per_m2"]) > 0
        ]
        if len(ppms) >= 3:
            from src.telegram.avm import _quantile  # reuse
            import statistics as _st
            avm = {
                "p25": round(_quantile(ppms, 0.25), 2),
                "p50": round(_st.median(ppms), 2),
                "p75": round(_quantile(ppms, 0.75), 2),
                "n_comps": len(ppms),
                "method": "radius_quantile",
            }

    # --- 5) Viability (4 faixas) ---
    viability_studies: dict[str, Optional[dict[str, Any]]] = {}
    viability_failed = False
    if user_price and user_area and time_left() > 5:
        try:
            for key in MCMV_FAIXAS.keys():
                if time_left() <= 2:
                    viability_failed = True
                    break
                viability_studies[key] = simulate_project(user_price, user_area, key)
        except Exception as exc:
            logger.warning(f"[ficha] viability failed: {exc}")
            viability_failed = True

    # --- 6) Risks ---
    risks = _fetch_risks(db, neighborhood, lat or 0, lng or 0) if time_left() > 2 else []

    # --- 7) Render ---
    return _render_ficha(
        label=label,
        kind=kind,
        lat=lat, lng=lng,
        neighborhood=neighborhood,
        user_area=user_area,
        user_price=user_price,
        avm=avm,
        comps=comps,
        viability=viability_studies,
        viability_failed=viability_failed,
        risks=risks,
        matched_listing=matched_listing,
    )


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------
def _fmt_money(v: Optional[float]) -> str:
    if v is None or v == 0:
        return "—"
    return f"R$ {float(v):,.0f}".replace(",", ".")


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{float(v):.1f}%"


def _verdict(
    viability: dict[str, Optional[dict[str, Any]]],
    avm: dict[str, Any],
    user_price: Optional[float],
    user_area: Optional[float],
) -> tuple[str, str, Optional[float]]:
    """Return (verdict_text, motivo, teto_sugerido)."""
    teto_sugerido: Optional[float] = None
    if avm.get("p25") and user_area and user_area > 0:
        teto_sugerido = float(avm["p25"]) * float(user_area)

    best = None
    best_margin = -999.0
    for k, study in viability.items():
        if not study:
            continue
        m = study["outputs"]["margem_liquida_pct"]
        if m > best_margin:
            best_margin = m
            best = study

    if not best:
        return ("⚪ *Análise insuficiente*", "Faltam dados para simular viabilidade.", teto_sugerido)

    payback = best["outputs"]["payback_anos"]
    margin_ok = best_margin >= RECOMENDA_MIN_MARGEM
    payback_ok = payback <= RECOMENDA_MAX_PAYBACK

    # AVM check (preço pedido vs P25)
    avm_ok = True
    avm_reason = ""
    if user_price and user_area and avm.get("p25"):
        ask_per_m2 = user_price / user_area
        if ask_per_m2 > float(avm["p25"]):
            avm_ok = False
            avm_reason = (
                f"preço pedido (R$ {ask_per_m2:,.0f}/m²) acima do P25 do AVM "
                f"(R$ {float(avm['p25']):,.0f}/m²)"
            )

    if margin_ok and payback_ok and avm_ok:
        motivo = (
            f"melhor cenário {best['scenario']} → margem {best_margin:.1f}%, "
            f"payback {payback:.1f} anos"
        )
        return ("🟢 *Recomendado avaliar*", motivo, teto_sugerido)

    reasons: list[str] = []
    if not margin_ok:
        reasons.append(f"margem {best_margin:.1f}% < {RECOMENDA_MIN_MARGEM:.0f}%")
    if not payback_ok:
        reasons.append(f"payback {payback:.1f} anos > {RECOMENDA_MAX_PAYBACK:.0f}")
    if not avm_ok:
        reasons.append(avm_reason)

    return ("🔴 *Não recomendado*", "; ".join(reasons) or "critérios mínimos não atendidos", teto_sugerido)


def _render_ficha(
    *,
    label: str,
    kind: str,
    lat: Optional[float],
    lng: Optional[float],
    neighborhood: Optional[str],
    user_area: Optional[float],
    user_price: Optional[float],
    avm: dict[str, Any],
    comps: list[dict[str, Any]],
    viability: dict[str, Optional[dict[str, Any]]],
    viability_failed: bool,
    risks: list[str],
    matched_listing: Optional[dict[str, Any]],
) -> str:
    lines: list[str] = []

    # Header
    lines.append("🏗 *Ficha de Terreno*")
    lines.append(f"📍 {label}")
    if neighborhood:
        lines.append(f"Bairro: *{neighborhood}*")
    if lat is not None and lng is not None:
        lines.append(f"Coord: `{lat:.5f},{lng:.5f}`")
    if user_area:
        lines.append(f"Área: *{user_area:,.0f} m²*".replace(",", "."))
    if user_price:
        lines.append(f"Preço pedido: *{_fmt_money(user_price)}*")
        if user_area:
            lines.append(f"Preço/m² pedido: *R$ {user_price/user_area:,.0f}/m²*".replace(",", "."))
    lines.append("")

    # AVM
    lines.append("*📈 AVM — Valor estimado (R$/m²)*")
    if avm.get("n_comps", 0) >= 3:
        lines.append(
            f"P25 {_fmt_money(avm['p25'])} | P50 {_fmt_money(avm['p50'])} | "
            f"P75 {_fmt_money(avm['p75'])}"
        )
        lines.append(f"_Base: {avm['n_comps']} comps ({avm['method']})_")
        if user_area:
            v_low = float(avm["p25"]) * user_area
            v_mid = float(avm["p50"]) * user_area
            v_hi = float(avm["p75"]) * user_area
            lines.append(
                f"Valor total estimado: {_fmt_money(v_low)} — "
                f"{_fmt_money(v_mid)} — {_fmt_money(v_hi)}"
            )
        else:
            lines.append("_Sem área informada — não é possível estimar valor total._")
    else:
        lines.append("_AVM indisponível (poucos comps no bairro)._")
    lines.append("")

    # Comps
    lines.append("*🏘 Comps próximos (raio 1km)*")
    if comps:
        for i, c in enumerate(comps[:3], 1):
            price = _fmt_money(c.get("sale_price"))
            area = c.get("total_area")
            area_s = f"{float(area):,.0f}m²".replace(",", ".") if area else "?"
            ppm = c.get("price_per_m2")
            ppm_s = f"R$ {float(ppm):,.0f}/m²".replace(",", ".") if ppm else ""
            dist = c.get("_dist_km", 0)
            neigh = c.get("neighborhood") or "?"
            url = c.get("url") or ""
            line = f"{i}. {neigh} — {price} | {area_s} | {ppm_s} | {dist:.2f}km"
            lines.append(line)
            if url:
                lines.append(f"   {url}")
    else:
        lines.append("_Nenhum comp ativo no raio de 1km._")
    lines.append("")

    # Viability
    lines.append("*🧮 Viabilidade MCMV (4 cenários)*")
    if viability_failed:
        lines.append("_Viabilidade indisponível (timeout)._")
    elif not user_price or not user_area:
        missing = []
        if not user_price:
            missing.append("preço")
        if not user_area:
            missing.append("área")
        lines.append(
            f"_Informe {' e '.join(missing)} no comando para simular._\n"
            f"Ex: `/ficha {label} 250m² R$200000`"
        )
    else:
        lines.append("```")
        lines.append(f"{'Faixa':<14} {'Margem':>7} {'Payback':>8} {'VGV':>13}")
        for key in MCMV_FAIXAS.keys():
            s = viability.get(key)
            if not s:
                lines.append(f"{MCMV_FAIXAS[key]['nome'][:14]:<14} {'—':>7} {'—':>8} {'—':>13}")
                continue
            o = s["outputs"]
            mark = "✅" if s["is_viable"] else "❌"
            lines.append(
                f"{MCMV_FAIXAS[key]['nome'][:14]:<14} "
                f"{o['margem_liquida_pct']:>6.1f}% "
                f"{o['payback_anos']:>6.1f}a {mark} "
                f"{o['vgv']:>12,.0f}".replace(",", ".")
            )
        lines.append("```")
    lines.append("")

    # Risks
    lines.append("*⚠️ Riscos / Sinais regulatórios*")
    if risks:
        for r in risks[:5]:
            lines.append(f"• {r}")
    else:
        lines.append("_Nenhum risco regulatório detectado para a região._")
    lines.append("")

    # Verdict
    verdict, motivo, teto = _verdict(viability, avm, user_price, user_area)
    lines.append("*🎯 Veredito*")
    lines.append(verdict)
    lines.append(f"_{motivo}_")
    if teto:
        lines.append("")
        lines.append(
            f"💡 *Teto de oferta sugerido:* {_fmt_money(teto)} "
            f"_(P25 AVM × área — apenas referência)_"
        )
    lines.append("")
    lines.append("_Recomendação — decisão final é sua._")

    return "\n".join(lines)

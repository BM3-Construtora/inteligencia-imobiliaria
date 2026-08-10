"""Hunter (Caçador) — scores land opportunities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from postgrest.exceptions import APIError

from src.config import SUPABASE_URL
from src.db import get_client

logger = logging.getLogger(__name__)

# Scoring config (can be overridden via env)
import os

SCORING_MIN_AREA = float(os.getenv("SCORING_MIN_AREA", "200"))
# Teto de área do funil urbano MCMV. Acima disso é gleba/rural (loteamento,
# chácara, fazenda) — não serve pra casa MCMV, então não vira oportunidade.
SCORING_MAX_AREA = float(os.getenv("SCORING_MAX_AREA", "2000"))
SCORING_MAX_PRICE = float(os.getenv("SCORING_MAX_PRICE", "300000"))
SCORING_IDEAL_PRICE_M2 = float(os.getenv("SCORING_IDEAL_PRICE_M2", "350"))
MCMV_MAX_PRICE = float(os.getenv("MCMV_MAX_PRICE", "264000"))


def run_hunter() -> dict[str, int]:
    """Score all active land listings and create/update opportunities."""
    db = get_client()
    stats = {"scored": 0, "opportunities": 0, "top_score": 0.0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "hunter", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Get market context for relative scoring
        context = _get_market_context(db)
        logger.info(
            f"[hunter] Market context: avg_price_m2={context['avg_price_m2']}, "
            f"median_price={context['median_price']}, total_land={context['total_land']}"
        )

        # Fetch all active land listings.
        # mcmv_accessibility_score (Score v2, eixo spatial) vem junto quando a
        # coluna existe; se a migration 045 não foi aplicada, refaz sem ela.
        base_cols = (
            "id, source, source_id, sale_price, total_area, "
            "price_per_m2, neighborhood, latitude, longitude, "
            "is_mcmv, title, address, first_seen_at, features"
        )

        def _fetch_listings(cols: str):
            return (
                db.table("listings")
                .select(cols)
                .eq("is_active", True)
                .is_("canonical_listing_id", "null")
                .eq("property_type", "land")
                .not_.is_("sale_price", "null")
                .gt("sale_price", 5000)  # Filter out placeholder/error prices
                # Exclui itens em quarentena (ppm2/área/price implausíveis marcados
                # pelo normalizer). Sem isto, erros de parse de área — que geram
                # preço/m² minúsculo — recebem nota máxima e viram falsos "quentes".
                .or_("quarantined.is.false,quarantined.is.null")
                .execute()
            )

        try:
            result = _fetch_listings(base_cols + ", mcmv_accessibility_score")
        except APIError as e:
            if "mcmv_accessibility_score" in str(e):
                logger.warning(
                    "[hunter] coluna mcmv_accessibility_score ausente — "
                    "eixo spatial do Score v2 desativado"
                )
                result = _fetch_listings(base_cols)
            else:
                raise

        listings = result.data
        logger.info(f"[hunter] Scoring {len(listings)} land listings (filtered price > R$5000)")

        # Score v2 — sinais AVM por listing (subprecificação). Degradação
        # graciosa: tabela vazia/ausente → mapa vazio → multiplicador V2 = 1.0.
        avm_map = _fetch_avm_signals(db, [l["id"] for l in listings])

        scored = []
        for listing in listings:
            score, breakdown = _score_listing(listing, context, avm_map.get(listing["id"]))
            scored.append((listing, score, breakdown))
            stats["scored"] += 1

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        if scored:
            stats["top_score"] = scored[0][1]

        # --- Percentile calibration ---
        # Collect all raw_scores, sort, then compute percentile per listing.
        # Distribution snapshot is logged so the user can detect calibration drift.
        all_scores = sorted([s for _, s, _ in scored])
        total_scored = len(all_scores)
        percentile_by_listing: dict[int, float] = {}
        if total_scored > 0:
            # Build rank lookup: percentile = (rank / total) * 100 where rank is
            # the 1-based index of the score in the sorted ascending list.
            # Equal scores get the same rank (highest position) — stable for ties.
            for listing, score, _ in scored:
                # Rank = number of scores <= this score (handles ties)
                # Use bisect-like behavior: count items <= score
                rank = 0
                lo, hi = 0, total_scored
                while lo < hi:
                    mid = (lo + hi) // 2
                    if all_scores[mid] <= score:
                        lo = mid + 1
                    else:
                        hi = mid
                rank = lo
                pct = round((rank / total_scored) * 100, 2)
                percentile_by_listing[listing["id"]] = pct

            _log_score_distribution(all_scores)

        # Batch upsert opportunities
        opp_batch: list[dict] = []
        history_batch: list[dict] = []
        for listing, score, breakdown in scored:
            pct = percentile_by_listing.get(listing["id"])
            history_batch.append({
                "listing_id": listing["id"],
                "raw_score": score,
                "percentile": pct,
                "score_breakdown": breakdown,
            })
            if score < 30:
                continue

            # Gleba/rural (área conhecida acima do teto urbano) não vira
            # oportunidade — fica fora do funil MCMV. Área desconhecida (0/None)
            # não é excluída: pode ser lote urbano sem área parseada.
            area_val = float(listing.get("total_area") or 0)
            if area_val > SCORING_MAX_AREA:
                continue

            reason = _build_reason(listing, score, breakdown)
            opp_batch.append({
                "listing_id": listing["id"],
                "score": score,
                "score_breakdown": breakdown,
                "reason": reason,
                "percentile_score": pct,
            })
            stats["opportunities"] += 1

        # Preserva last_notified_price: o notifier grava esse valor dentro de
        # score_breakdown para detectar quedas de preço. Como o upsert abaixo
        # sobrescreve o breakdown inteiro, sem este merge a chave seria apagada
        # a cada run do hunter, quebrando a renotificação por price-drop.
        if opp_batch:
            opp_listing_ids = [o["listing_id"] for o in opp_batch]
            last_price_by_listing: dict[int, float] = {}
            for i in range(0, len(opp_listing_ids), 100):
                chunk = opp_listing_ids[i:i + 100]
                try:
                    er = (
                        db.table("opportunities")
                        .select("listing_id, score_breakdown")
                        .in_("listing_id", chunk)
                        .execute()
                    )
                except APIError:
                    continue
                for row in er.data or []:
                    bd = row.get("score_breakdown") or {}
                    if isinstance(bd, dict) and bd.get("last_notified_price"):
                        last_price_by_listing[row["listing_id"]] = bd["last_notified_price"]
            for o in opp_batch:
                lnp = last_price_by_listing.get(o["listing_id"])
                if lnp and isinstance(o.get("score_breakdown"), dict):
                    o["score_breakdown"]["last_notified_price"] = lnp

        # Flag controls whether new column / history table writes are attempted.
        # If migration 020 is not applied we log once and skip the rest.
        percentile_cols_available = True
        history_table_available = True

        migration_warned = False
        for i in range(0, len(opp_batch), 100):
            batch = opp_batch[i:i + 100]
            # Strip percentile_score if the column is unavailable
            if not percentile_cols_available:
                batch = [{k: v for k, v in row.items() if k != "percentile_score"} for row in batch]
            try:
                db.table("opportunities").upsert(
                    batch, on_conflict="listing_id"
                ).execute()
            except APIError as e:
                code = getattr(e, "code", None) or (e.args[0] if e.args else "")
                msg = str(e)
                if "PGRST204" in msg or "percentile_score" in msg:
                    if percentile_cols_available:
                        logger.warning(
                            "[hunter] Coluna percentile_score ausente em opportunities. "
                            "Aplique supabase/migrations/*_hunter_score_history.sql. Pulando writes desta coluna."
                        )
                    percentile_cols_available = False
                    batch = [{k: v for k, v in row.items() if k != "percentile_score"} for row in batch]
                    try:
                        db.table("opportunities").upsert(batch, on_conflict="listing_id").execute()
                    except APIError:
                        _fallback_upsert(db, batch)
                elif "42P10" in str(code) or "42P10" in msg:
                    if not migration_warned:
                        logger.error(
                            "[hunter] UNIQUE(listing_id) ausente em opportunities. "
                            "Aplique supabase/migrations/*_data_quality_fixes.sql. Usando fallback insert/update."
                        )
                        migration_warned = True
                    _fallback_upsert(db, batch)
                else:
                    logger.warning(f"[hunter] Upsert batch failed: {e}; tentando 1-a-1")
                    _fallback_upsert(db, batch)

        # --- Hunter score history (series temporal) ---
        if history_table_available and history_batch:
            for i in range(0, len(history_batch), 200):
                hbatch = history_batch[i:i + 200]
                try:
                    db.table("hunter_score_history").insert(hbatch).execute()
                except APIError as e:
                    msg = str(e)
                    if "PGRST205" in msg or "hunter_score_history" in msg or "PGRST204" in msg:
                        logger.warning(
                            "[hunter] Tabela hunter_score_history ausente. "
                            "Aplique supabase/migrations/*_hunter_score_history.sql. Pulando histórico."
                        )
                        history_table_available = False
                        break
                    else:
                        logger.warning(f"[hunter] History insert failed: {e}")

        logger.info(
            f"[hunter] Done: {stats['scored']} scored, "
            f"{stats['opportunities']} opportunities (top: {stats['top_score']:.1f})"
        )

        # Log top 10
        for listing, score, breakdown in scored[:10]:
            logger.info(
                f"[hunter] TOP {score:.1f}: "
                f"R${listing['sale_price']:,.0f} | "
                f"{listing.get('total_area', '?')}m² | "
                f"{listing.get('neighborhood', '?')} | "
                f"{listing.get('source', '')}:{listing.get('source_id', '')}"
            )

        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[hunter] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _log_score_distribution(sorted_scores: list[float]) -> None:
    """Log p10/p25/p50/p75/p90/p99 of raw scores for calibration drift visibility."""
    n = len(sorted_scores)
    if n == 0:
        return

    def _pct(p: float) -> float:
        idx = min(n - 1, max(0, int(round((p / 100) * (n - 1)))))
        return sorted_scores[idx]

    logger.info(
        f"[hunter] Score distribution (n={n}): "
        f"p10={_pct(10):.1f} | p25={_pct(25):.1f} | p50={_pct(50):.1f} | "
        f"p75={_pct(75):.1f} | p90={_pct(90):.1f} | p99={_pct(99):.1f} | "
        f"min={sorted_scores[0]:.1f} | max={sorted_scores[-1]:.1f}"
    )


def _fallback_upsert(db: Any, batch: list[dict]) -> None:
    """Per-row update-or-insert when unique constraint is missing."""
    for item in batch:
        try:
            existing = (
                db.table("opportunities")
                .select("id")
                .eq("listing_id", item["listing_id"])
                .limit(1)
                .execute()
            )
            if existing.data:
                db.table("opportunities").update(item).eq(
                    "listing_id", item["listing_id"]
                ).execute()
            else:
                db.table("opportunities").insert(item).execute()
        except APIError:
            continue


def _get_market_context(db: Any) -> dict[str, float]:
    """Get market averages for land listings to use in relative scoring."""
    result = (
        db.table("listings")
        .select("sale_price, total_area, price_per_m2")
        .eq("is_active", True)
        .eq("property_type", "land")
        .not_.is_("sale_price", "null")
        .gt("sale_price", 0)
        .execute()
    )

    prices = [float(r["sale_price"]) for r in result.data]
    areas = [float(r["total_area"]) for r in result.data if r.get("total_area")]
    price_m2s = [float(r["price_per_m2"]) for r in result.data if r.get("price_per_m2")]

    prices.sort()
    n = len(prices)
    median = prices[n // 2] if n else 0

    return {
        "avg_price": sum(prices) / n if n else 0,
        "median_price": median,
        "avg_price_m2": sum(price_m2s) / len(price_m2s) if price_m2s else 0,
        "avg_area": sum(areas) / len(areas) if areas else 0,
        "total_land": n,
    }


# Source confidence weights — based on data quality audit
# Applied as a multiplier to the raw score
SOURCE_CONFIDENCE = {
    "uniao": 1.00,       # Tier 1: GPS, endereço, MCMV flag, API estruturada
    "toca": 1.00,        # Tier 1: GPS, preço 100%, zona do bairro
    "vivareal": 0.85,    # Tier 2: bons dados preço/área, sem geo
    "zapimoveis": 0.85,  # Tier 2: JSON-LD estruturado, bons dados preço/área
    "chavesnamao": 0.80,  # Tier 2: muitos terrenos, área ~52% confiável
    # imovelweb aposentado 2026-05-11 (Cloudflare bloqueia ~100%) — sem peso.
}


def _fetch_avm_signals(db: Any, listing_ids: list[int]) -> dict[int, dict]:
    """Mapa listing_id -> sinal AVM (subprecificação) para o Score v2.

    Degradação graciosa: se a tabela avm_predictions não existe (migration não
    aplicada) ou está vazia, retorna mapa vazio e o multiplicador V2 vira 1.0.
    """
    out: dict[int, dict] = {}
    if not listing_ids:
        return out
    for i in range(0, len(listing_ids), 200):
        chunk = listing_ids[i:i + 200]
        try:
            r = (
                db.table("avm_predictions")
                .select("listing_id, mispricing_pct, is_undervalued, confidence")
                .in_("listing_id", chunk)
                .execute()
            )
        except APIError:
            logger.warning("[hunter] avm_predictions indisponível — eixo AVM do Score v2 desativado")
            return {}
        for row in r.data or []:
            out[row["listing_id"]] = row
    return out


def _v2_multiplier(
    listing: dict[str, Any],
    avm: dict | None,
    breakdown: dict[str, Any],
) -> float:
    """Multiplicador do Score v2 a partir dos sinais do cérebro V2.

    final = base * confidence * v2_multiplier, com v2 = clamp(1 + upside +
    antecipado, 0.90, 1.30). Cada termo é 0 quando o sinal falta, então sem
    dado o multiplicador é 1.0 e o score fica idêntico ao base (degradação
    graciosa). Fricção regulatória fica para a fatia 2 (ver docs/specs).
    """
    upside = 0.0
    antecipado = 0.0

    # Eixo upside — AVM: subprecificado (p50 > pedido) empurra pra cima,
    # ponderado pela confiança do modelo. mispricing_pct = (p50-actual)/p50*100.
    if avm:
        mis = avm.get("mispricing_pct")
        conf = float(avm.get("confidence") or 0.0)
        if mis is not None and conf >= 0.3:
            # +0.20 no máximo (20% subprecificado com confiança), proporcional.
            upside = max(0.0, min(float(mis) / 100.0, 0.20)) * min(conf, 1.0)
            breakdown["v2_avm_upside"] = round(upside, 3)
            if avm.get("is_undervalued"):
                breakdown["v2_undervalued"] = True

    # Eixo antecipado — acessibilidade MCMV (spatial), 0-100 centrado em 50.
    access = listing.get("mcmv_accessibility_score")
    if access is not None:
        try:
            a = float(access)
            antecipado = max(-0.05, min((a - 50.0) / 500.0, 0.10))
            breakdown["v2_accessibility"] = round(antecipado, 3)
        except (ValueError, TypeError):
            pass

    mult = max(0.90, min(1.0 + upside + antecipado, 1.30))
    return round(mult, 4)


def _score_listing(
    listing: dict[str, Any],
    context: dict[str, float],
    avm: dict | None = None,
) -> tuple[float, dict[str, Any]]:
    """Score a single land listing. Returns (score, breakdown).

    Raw score is 0-100 based on:
    - price_score (25pts): lower price = better
    - price_m2_score (20pts): lower price/m² = better
    - area_score (15pts): larger area = better (up to a point)
    - mcmv_score (10pts): MCMV compatible = bonus
    - location_score (10pts): has coordinates = bonus, known neighborhood = bonus
    - data_quality (10pts): completeness of fields for this listing
    - source_confidence (10pts): reliability of the source

    Final score = raw_score * source_confidence_multiplier * v2_multiplier
    (v2 = sinais do cérebro V2; sem dado, v2 = 1.0 → score inalterado).
    """
    breakdown: dict[str, Any] = {}
    source = listing.get("source", "")
    price = float(listing.get("sale_price") or 0)
    area = float(listing.get("total_area") or 0)
    price_m2 = float(listing.get("price_per_m2") or 0)

    # --- Price score (25pts): better if below max, best if way below ---
    if price <= 0:
        breakdown["price"] = 0
    elif price <= SCORING_MAX_PRICE * 0.5:
        breakdown["price"] = 25
    elif price <= SCORING_MAX_PRICE * 0.75:
        breakdown["price"] = 20
    elif price <= SCORING_MAX_PRICE:
        breakdown["price"] = 17
    elif price <= SCORING_MAX_PRICE * 1.5:
        breakdown["price"] = 8
    elif price <= SCORING_MAX_PRICE * 2:
        breakdown["price"] = 4
    else:
        breakdown["price"] = 0

    # --- Price per m² score (20pts): relative to market ---
    if price_m2 <= 0:
        breakdown["price_m2"] = 0  # No data = no points (was 5 before, rewarded missing data)
    elif price_m2 <= SCORING_IDEAL_PRICE_M2 * 0.5:
        breakdown["price_m2"] = 20
    elif price_m2 <= SCORING_IDEAL_PRICE_M2:
        breakdown["price_m2"] = 17
    elif price_m2 <= context.get("avg_price_m2", 500):
        breakdown["price_m2"] = 12
    elif price_m2 <= context.get("avg_price_m2", 500) * 1.5:
        breakdown["price_m2"] = 6
    else:
        breakdown["price_m2"] = 0

    # --- Area score (15pts): prefer >= SCORING_MIN_AREA ---
    if area <= 0:
        breakdown["area"] = 0  # No data = no points
    elif area >= SCORING_MIN_AREA * 2:
        breakdown["area"] = 15
    elif area >= SCORING_MIN_AREA * 1.5:
        breakdown["area"] = 13
    elif area >= SCORING_MIN_AREA:
        breakdown["area"] = 11
    elif area >= SCORING_MIN_AREA * 0.75:
        breakdown["area"] = 7
    elif area >= SCORING_MIN_AREA * 0.5:
        breakdown["area"] = 4
    else:
        breakdown["area"] = 2

    # --- MCMV score (10pts) ---
    is_mcmv = listing.get("is_mcmv", False)
    mcmv_price_ok = 0 < price <= MCMV_MAX_PRICE
    if is_mcmv:
        breakdown["mcmv"] = 10
    elif mcmv_price_ok:
        breakdown["mcmv"] = 7
    elif price <= MCMV_MAX_PRICE * 1.2:
        breakdown["mcmv"] = 3
    else:
        breakdown["mcmv"] = 0

    # --- Location score (10pts) ---
    has_coords = (
        listing.get("latitude") is not None
        and listing.get("longitude") is not None
    )
    has_neighborhood = bool(listing.get("neighborhood"))
    has_address = bool(listing.get("address"))

    loc_score = 0
    if has_coords:
        loc_score += 5
    if has_neighborhood:
        loc_score += 3
    if has_address:
        loc_score += 2
    breakdown["location"] = loc_score

    # --- Data quality score (10pts): reward complete listings ---
    dq = 0
    if price > 0:
        dq += 2
    if area > 0:
        dq += 2
    if price_m2 > 0:
        dq += 2
    if has_coords:
        dq += 2
    if listing.get("title"):
        dq += 1
    if listing.get("is_mcmv") is not None:
        dq += 1
    breakdown["data_quality"] = dq

    # --- Enriched features bonus (up to 10pts) ---
    features = listing.get("features") or {}
    if not isinstance(features, dict):
        features = {}
    enriched = features.get("_source") == "claude_haiku"

    enrich_score = 0
    if enriched:
        infra = features.get("infraestrutura") or []
        if not isinstance(infra, list):
            infra = []
        enrich_score += min(len(infra), 4)

        prox = features.get("proximidades") or []
        if not isinstance(prox, list):
            prox = []
        enrich_score += min(len(prox), 3)

        zoning = (features.get("zoneamento") or "").lower()
        if "residencial" in zoning:
            enrich_score += 2
        elif "misto" in zoning:
            enrich_score += 1

        terreno = features.get("caracteristicas_terreno") or []
        if not isinstance(terreno, list):
            terreno = []
        if any("plano" in str(t).lower() for t in terreno):
            enrich_score += 1

    breakdown["enriched"] = min(enrich_score, 10)

    # --- Stale bonus (5pts): terrenos parados há muito tempo = vendedor negocia ---
    from datetime import datetime, timezone
    stale = 0
    fs = listing.get("first_seen_at")
    if fs:
        try:
            first = datetime.fromisoformat(str(fs).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - first).days
            if days >= 120:
                stale = 5  # 4+ meses parado
            elif days >= 90:
                stale = 4
            elif days >= 60:
                stale = 2
        except (ValueError, TypeError):
            pass
    breakdown["stale_bonus"] = stale

    # --- Source confidence (multiplier only, no additive points) ---
    confidence = SOURCE_CONFIDENCE.get(source, 0.70)

    raw_total = sum(breakdown.values())

    # Score v2 — sinais do cérebro V2 como multiplicador (degradação graciosa:
    # sem dado → 1.0). Calculado antes de escrever as chaves informativas para
    # que elas não entrem no raw_total.
    v2_mult = _v2_multiplier(listing, avm, breakdown)

    # Apply source confidence as multiplier (not additive — avoids double-penalty)
    final = round(raw_total * confidence * v2_mult, 1)
    breakdown["raw_total"] = raw_total
    breakdown["confidence_multiplier"] = confidence
    breakdown["v2_multiplier"] = v2_mult
    breakdown["total"] = final

    return final, breakdown


def _build_reason(
    listing: dict[str, Any],
    score: float,
    breakdown: dict[str, Any],
) -> str:
    """Build a human-readable reason for the score."""
    parts = []
    price = float(listing.get("sale_price") or 0)
    area = float(listing.get("total_area") or 0)
    price_m2 = float(listing.get("price_per_m2") or 0)
    neigh = listing.get("neighborhood", "?")

    source = listing.get("source", "?")
    confidence = breakdown.get("confidence_multiplier", 1.0)

    if score >= 70:
        parts.append("Oportunidade excelente")
    elif score >= 55:
        parts.append("Boa oportunidade")
    elif score >= 40:
        parts.append("Vale acompanhar")
    else:
        parts.append("Registro")

    parts.append(f"R$ {price:,.0f}")
    if area > 0:
        parts.append(f"{area:.0f}m²")
    if price_m2 > 0:
        parts.append(f"R$ {price_m2:,.0f}/m²")
    parts.append(f"Bairro: {neigh}")

    if breakdown.get("mcmv", 0) >= 7:
        parts.append("MCMV compativel")

    # Confidence tag
    if confidence >= 1.0:
        parts.append(f"[{source} alta confianca]")
    elif confidence >= 0.85:
        parts.append(f"[{source} media confianca]")
    else:
        parts.append(f"[{source} baixa confianca - validar dados]")

    return " | ".join(parts)


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
        "items_processed": stats["scored"],
        "items_created": stats["opportunities"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

"""Track D — Feedback loop / decision calibration.

Registra visitas/ofertas/resultados reais em `bm3_deals`, snapshota AVM e
hunter score no momento da visita, e cruza recomendação vs realidade para
gerar drift report semanal.

Não toma decisões automáticas — é aprendizado. Cada chamada é idempotente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage machine — não pode voltar de closed_won/closed_lost
# ---------------------------------------------------------------------------

VALID_STAGES = {
    "visited", "offered", "negotiating", "accepted",
    "rejected", "closed_won", "closed_lost", "abandoned",
}

# Ordem lógica do funil — usada apenas para validar transições.
_STAGE_ORDER = {
    "visited": 1,
    "offered": 2,
    "negotiating": 3,
    "accepted": 4,
    "rejected": 99,
    "closed_won": 100,
    "closed_lost": 100,
    "abandoned": 100,
}

# Estágios que contam como acerto do Hunter: recomendação que virou ação real e
# não foi rejeitada, perdida ou abandonada. rejected/closed_lost NÃO são hit —
# incluí-los media "alguém foi visitar", não "a recomendação era boa".
POSITIVE_STAGES = {"visited", "offered", "negotiating", "accepted", "closed_won"}

# Amostra mínima para tratar uma taxa de calibração como estatisticamente útil.
# Abaixo disso, o drift report não recomenda ajuste de parâmetro de produção.
MIN_CALIBRATION_SAMPLE = 8

_TERMINAL = {"closed_won", "closed_lost", "abandoned", "rejected"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_transition(current: Optional[str], new: str) -> None:
    if new not in VALID_STAGES:
        raise ValueError(f"stage inválido: {new}. Valores: {sorted(VALID_STAGES)}")
    if current is None:
        return
    if current in _TERMINAL and new != current:
        raise ValueError(
            f"transição inválida: deal já está em estado terminal '{current}' "
            f"— não pode ir para '{new}'"
        )


# ---------------------------------------------------------------------------
# Snapshots — Hunter score / AVM no momento da visita
# ---------------------------------------------------------------------------

def _snapshot_hunter_score(db: Any, listing_id: int) -> Optional[float]:
    """Pega o score mais recente da listing em `opportunities`."""
    try:
        res = (
            db.table("opportunities")
            .select("score")
            .eq("listing_id", listing_id)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return float(res.data[0]["score"])
    except Exception as exc:
        logger.debug(f"[feedback_loop] hunter score snapshot falhou: {exc}")
    return None


def _snapshot_avm(db: Any, listing_id: int) -> dict[str, Optional[float]]:
    """Computa AVM (P25/P50/P75) para o bairro da listing.

    Retorna preços absolutos (price_per_m2 * area) para comparar com
    asking/offered/accepted_price diretamente.
    """
    out: dict[str, Optional[float]] = {"p25": None, "p50": None, "p75": None}
    try:
        lst = (
            db.table("listings")
            .select("neighborhood, total_area")
            .eq("id", listing_id)
            .single()
            .execute()
        )
        row = lst.data or {}
        neigh = row.get("neighborhood")
        area = row.get("total_area")
        if not neigh or not area:
            return out

        from src.telegram.avm import quick_avm
        avm = quick_avm(neigh, float(area), db)
        if avm.get("p50"):
            area_f = float(area)
            out["p25"] = round(float(avm["p25"]) * area_f, 2)
            out["p50"] = round(float(avm["p50"]) * area_f, 2)
            out["p75"] = round(float(avm["p75"]) * area_f, 2)
    except Exception as exc:
        logger.debug(f"[feedback_loop] AVM snapshot falhou: {exc}")
    return out


def _snapshot_viability_margin(db: Any, listing_id: int) -> Optional[float]:
    """Pega net_margin_pct do viability_studies mais recente da listing."""
    try:
        res = (
            db.table("viability_studies")
            .select("net_margin_pct, gross_margin_pct, outputs")
            .eq("listing_id", listing_id)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            if row.get("net_margin_pct") is not None:
                return float(row["net_margin_pct"])
            if row.get("gross_margin_pct") is not None:
                return float(row["gross_margin_pct"])
            outputs = row.get("outputs") or {}
            if isinstance(outputs, dict):
                for k in ("net_margin_pct", "margin_pct", "gross_margin_pct"):
                    if outputs.get(k) is not None:
                        return float(outputs[k])
    except Exception as exc:
        logger.debug(f"[feedback_loop] viability snapshot falhou: {exc}")
    return None


def _snapshot_asking_price(db: Any, listing_id: int) -> Optional[float]:
    try:
        res = (
            db.table("listings")
            .select("sale_price")
            .eq("id", listing_id)
            .single()
            .execute()
        )
        if res.data and res.data.get("sale_price") is not None:
            return float(res.data["sale_price"])
    except Exception as exc:
        logger.debug(f"[feedback_loop] asking_price snapshot falhou: {exc}")
    return None


# ---------------------------------------------------------------------------
# record_deal — insert/update
# ---------------------------------------------------------------------------

def record_deal(
    listing_id: Optional[int],
    stage: str,
    *,
    deal_id: Optional[int] = None,
    **fields: Any,
) -> int:
    """Cria ou atualiza um bm3_deal. Snapshota AVM/Hunter/Viability se houver listing_id.

    fields aceitos: offered_price, accepted_price, notes, rejection_reason,
                    visited_at, offered_at, closed_at, created_by,
                    off_market_signal_id, asking_price.
    """
    db = get_client()

    # Carrega current se update
    current_row: dict[str, Any] = {}
    if deal_id is not None:
        res = db.table("bm3_deals").select("*").eq("id", deal_id).limit(1).execute()
        if res.data:
            current_row = res.data[0]
        else:
            raise ValueError(f"deal_id={deal_id} não encontrado")

    _validate_transition(current_row.get("stage"), stage)

    payload: dict[str, Any] = {"stage": stage}
    if listing_id is not None:
        payload["listing_id"] = listing_id

    # Timestamps automáticos
    now = _now_iso()
    if stage == "visited" and not current_row.get("visited_at"):
        payload.setdefault("visited_at", fields.pop("visited_at", now))
    if stage in {"offered", "negotiating"} and not current_row.get("offered_at"):
        payload.setdefault("offered_at", fields.pop("offered_at", now))
    if stage in _TERMINAL and not current_row.get("closed_at"):
        payload.setdefault("closed_at", fields.pop("closed_at", now))

    # Snapshots — apenas no momento da visita (primeira gravação) e se ainda vazio
    is_first_write = deal_id is None
    if listing_id and is_first_write:
        if current_row.get("hunter_score_at_visit") is None:
            hs = _snapshot_hunter_score(db, listing_id)
            if hs is not None:
                payload["hunter_score_at_visit"] = hs
        if current_row.get("avm_p50_at_visit") is None:
            avm = _snapshot_avm(db, listing_id)
            if avm.get("p50"):
                payload["avm_p25_at_visit"] = avm["p25"]
                payload["avm_p50_at_visit"] = avm["p50"]
                payload["avm_p75_at_visit"] = avm["p75"]
        if current_row.get("viability_margin_at_visit") is None:
            vm = _snapshot_viability_margin(db, listing_id)
            if vm is not None:
                payload["viability_margin_at_visit"] = vm
        if current_row.get("asking_price") is None and "asking_price" not in fields:
            ap = _snapshot_asking_price(db, listing_id)
            if ap is not None:
                payload["asking_price"] = ap

    # Campos passados explicitamente sobrescrevem
    for k, v in fields.items():
        if v is not None:
            payload[k] = v

    if deal_id is None:
        res = db.table("bm3_deals").insert(payload).execute()
        if not res.data:
            raise RuntimeError("insert bm3_deals sem retorno")
        new_id = int(res.data[0]["id"])
        logger.info(f"[feedback_loop] deal criado id={new_id} stage={stage}")
        return new_id

    db.table("bm3_deals").update(payload).eq("id", deal_id).execute()
    logger.info(f"[feedback_loop] deal id={deal_id} atualizado para stage={stage}")
    return deal_id


def record_outcome(
    deal_id: int,
    actual_margin_pct: float,
    actual_payback_months: int,
) -> None:
    """Preenche o resultado real após obra/venda."""
    db = get_client()
    res = db.table("bm3_deals").select("stage").eq("id", deal_id).limit(1).execute()
    if not res.data:
        raise ValueError(f"deal_id={deal_id} não encontrado")

    update = {
        "actual_outcome_margin_pct": float(actual_margin_pct),
        "actual_outcome_payback_months": int(actual_payback_months),
    }
    db.table("bm3_deals").update(update).eq("id", deal_id).execute()
    logger.info(
        f"[feedback_loop] outcome id={deal_id} margem={actual_margin_pct}% "
        f"payback={actual_payback_months}m"
    )


# ---------------------------------------------------------------------------
# Calibração — drift real vs recomendação
# ---------------------------------------------------------------------------

def run_calibration() -> dict[str, Any]:
    """Cruza realidade vs recomendação e grava em recommendation_calibration."""
    db = get_client()
    now = datetime.now(timezone.utc)
    cutoff_180 = (now - timedelta(days=180)).isoformat()
    cutoff_90 = (now - timedelta(days=90)).isoformat()

    # ---- Viability error ----
    viability_error_pct: Optional[float] = None
    viab_n = 0
    try:
        res = (
            db.table("bm3_deals")
            .select("viability_margin_at_visit, actual_outcome_margin_pct")
            .eq("stage", "closed_won")
            .not_.is_("actual_outcome_margin_pct", "null")
            .not_.is_("viability_margin_at_visit", "null")
            .gte("closed_at", cutoff_180)
            .execute()
        )
        errors = []
        for r in res.data or []:
            est = float(r["viability_margin_at_visit"])
            real = float(r["actual_outcome_margin_pct"])
            errors.append(abs(est - real))
        if errors:
            viability_error_pct = round(sum(errors) / len(errors), 2)
            viab_n = len(errors)
    except Exception as exc:
        logger.exception(f"[calibration] viability error falhou: {exc}")

    # ---- AVM hit rate (accepted dentro de P25-P75) ----
    avm_hits = 0
    avm_total = 0
    avm_error_pct: Optional[float] = None
    try:
        res = (
            db.table("bm3_deals")
            .select("avm_p25_at_visit, avm_p50_at_visit, avm_p75_at_visit, "
                    "accepted_price, offered_price")
            .gte("offered_at", cutoff_90)
            .not_.is_("avm_p50_at_visit", "null")
            .execute()
        )
        errors_avm = []
        for r in res.data or []:
            actual = r.get("accepted_price") or r.get("offered_price")
            p25 = r.get("avm_p25_at_visit")
            p50 = r.get("avm_p50_at_visit")
            p75 = r.get("avm_p75_at_visit")
            if actual is None or p50 in (None, 0):
                continue
            actual = float(actual)
            p50f = float(p50)
            avm_total += 1
            if p25 is not None and p75 is not None:
                if float(p25) <= actual <= float(p75):
                    avm_hits += 1
            errors_avm.append(abs(actual - p50f) / p50f * 100)
        if errors_avm:
            avm_error_pct = round(sum(errors_avm) / len(errors_avm), 2)
    except Exception as exc:
        logger.exception(f"[calibration] avm error falhou: {exc}")

    avm_hit_rate = round(avm_hits / avm_total, 4) if avm_total else None

    # ---- Hunter hit rate (oportunidades score>=70 que viraram deal) ----
    hunter_hit_rate: Optional[float] = None
    total_recs = 0
    deals_from_recs = 0
    try:
        opps = (
            db.table("opportunities")
            .select("listing_id, score, created_at")
            .gte("score", 70)
            .gte("created_at", cutoff_90)
            .execute()
        )
        listing_ids = list({o["listing_id"] for o in (opps.data or []) if o.get("listing_id")})
        total_recs = len(listing_ids)
        if listing_ids:
            deals = (
                db.table("bm3_deals")
                .select("listing_id, stage")
                .in_("listing_id", listing_ids)
                .execute()
            )
            advanced = {d["listing_id"] for d in (deals.data or [])
                        if d.get("stage") in POSITIVE_STAGES}
            deals_from_recs = len(advanced)
            hunter_hit_rate = round(deals_from_recs / total_recs, 4) if total_recs else None
    except Exception as exc:
        logger.exception(f"[calibration] hunter hit rate falhou: {exc}")

    # ---- Contadores de funil últimos 90 dias ----
    visited = offered = accepted = 0
    try:
        res = (
            db.table("bm3_deals")
            .select("stage")
            .gte("created_at", cutoff_90)
            .execute()
        )
        for r in res.data or []:
            s = r.get("stage")
            if s == "visited":
                visited += 1
            elif s in {"offered", "negotiating"}:
                offered += 1
            elif s in {"accepted", "closed_won"}:
                accepted += 1
    except Exception as exc:
        logger.debug(f"[calibration] contagem de funil falhou: {exc}")

    payload = {
        "run_date": now.date().isoformat(),
        "total_recommendations": total_recs,
        "visited": visited,
        "offered": offered,
        "accepted": accepted,
        "hunter_hit_rate": hunter_hit_rate,
        "avm_mean_error_pct": avm_error_pct,
        "viability_mean_error_pct": viability_error_pct,
        "notes": (
            f"deals_analyzed_viability={viab_n}; "
            f"avm_hit_rate_p25p75={avm_hit_rate}; "
            f"deals_from_recs={deals_from_recs}"
        ),
    }

    try:
        db.table("recommendation_calibration").insert(payload).execute()
    except Exception as exc:
        logger.exception(f"[calibration] insert falhou: {exc}")

    return {
        "hunter_hit_rate": hunter_hit_rate,
        "avm_error_pct": avm_error_pct,
        "viability_error_pct": viability_error_pct,
        "deals_analyzed": viab_n,
        "avm_n": avm_total,
        "total_recommendations": total_recs,
        "visited": visited,
        "offered": offered,
        "accepted": accepted,
        "avm_hit_rate_p25p75": avm_hit_rate,
    }


# ---------------------------------------------------------------------------
# Drift report (markdown)
# ---------------------------------------------------------------------------

def _fmt_pct(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "n/a"
    return f"{v:.{digits}f}%"


def _fmt_rate(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%"


def weekly_drift_report() -> str:
    """Markdown report para Telegram — drift de Hunter/AVM/Viability."""
    cal = run_calibration()
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    hunter = cal.get("hunter_hit_rate")
    avm_err = cal.get("avm_error_pct")
    viab_err = cal.get("viability_error_pct")
    deals_n = cal.get("deals_analyzed") or 0
    hunter_n = cal.get("total_recommendations") or 0
    avm_n = cal.get("avm_n") or 0

    # Targets
    HUNTER_TARGET = 0.25
    AVM_TARGET = 10.0
    VIAB_TARGET = 5.0

    lines: list[str] = []
    lines.append(f"*Drift Report {today}*")
    lines.append("")
    lines.append(f"Deals fechados últimos 90d (com outcome): *{deals_n}*")
    lines.append(f"Funil 90d: visitados={cal.get('visited')} · "
                 f"ofertados={cal.get('offered')} · aceitos={cal.get('accepted')}")
    lines.append("")
    lines.append("*Métricas vs target:*")
    lines.append("```")
    lines.append("Métrica           | atual    | target")
    lines.append("------------------+----------+--------")
    lines.append(f"Hunter hit rate   | {_fmt_rate(hunter):>8} | >={HUNTER_TARGET*100:.0f}%")
    lines.append(f"AVM mean error    | {_fmt_pct(avm_err):>8} | <=±{AVM_TARGET:.0f}%")
    lines.append(f"Viability error   | {_fmt_pct(viab_err):>8} | <=±{VIAB_TARGET:.0f}%")
    lines.append("```")

    # Recomendações concretas. Só recomendamos ajuste de parâmetro de produção
    # quando a amostra da métrica atinge MIN_CALIBRATION_SAMPLE — com N pequeno,
    # a taxa é ruído e ajustar parâmetro faz mais mal que bem.
    recs: list[str] = []
    insufficient: list[str] = []

    if hunter_n < MIN_CALIBRATION_SAMPLE:
        insufficient.append(f"Hunter ({hunter_n} recs)")
    elif hunter is not None and hunter < HUNTER_TARGET:
        recs.append(
            f"• *Hunter*: hit rate {_fmt_rate(hunter)} abaixo do target. "
            f"Considere subir threshold de score (ex: 70 → 75) ou revisar pesos "
            f"em `_score_listing` (price_per_m2, MCMV bonus)."
        )
    elif hunter is not None and hunter > 0.6:
        recs.append(
            f"• *Hunter*: hit rate {_fmt_rate(hunter)} muito alto — pode estar "
            f"subestimando oportunidades. Reduza threshold para capturar mais leads."
        )

    if avm_n < MIN_CALIBRATION_SAMPLE:
        insufficient.append(f"AVM ({avm_n} deals)")
    elif avm_err is not None and avm_err > AVM_TARGET:
        recs.append(
            f"• *AVM*: erro médio {_fmt_pct(avm_err)} (target ±{AVM_TARGET:.0f}%). "
            f"Ampliar janela de comps em `quick_avm` ou usar comps de bairros "
            f"vizinhos quando n<10."
        )

    if deals_n < MIN_CALIBRATION_SAMPLE:
        insufficient.append(f"Viability ({deals_n} deals)")
    elif viab_err is not None and viab_err > VIAB_TARGET:
        recs.append(
            f"• *Viability*: erro médio {_fmt_pct(viab_err)} na margem projetada. "
            f"Revisar BDI/eficiência e custo SINAPI/m² em `viability.py` "
            f"(env VIABILITY_BDI_PCT, VIABILITY_EFFICIENCY)."
        )

    if insufficient:
        recs.insert(0, (
            f"• *Amostra insuficiente* para calibrar: {', '.join(insufficient)} "
            f"(mínimo {MIN_CALIBRATION_SAMPLE}). As métricas acima são indicativas; "
            f"registre mais deals via `/deal_add` antes de ajustar parâmetros."
        ))

    if not recs:
        recs.append("• Sistema dentro dos targets — manter parâmetros atuais.")

    # Garante pelo menos 3 itens (preenche com checks operacionais)
    if len(recs) < 3:
        recs.append(
            "• Revisar manualmente top 3 deals fechados último mês — comparar "
            "narrativa do Hunter `reason` vs motivo real de aceite/rejeição."
        )
        recs.append(
            "• Rodar `/calibration` semanalmente para acompanhar a deriva ao longo do tempo."
        )

    lines.append("")
    lines.append("*Ajustes sugeridos:*")
    lines.extend(recs[:5])

    return "\n".join(lines)

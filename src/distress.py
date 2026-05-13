"""Distress scorer — pontua off_market_signals (0-100) e dispara Telegram top-N.

Heurísticas:
- +40 leilão Caixa com lance abaixo de avaliação
- +30 IPTU em atraso > 3 anos
- +25 inventário em fase avançada
- +20 alvará caducado > 12 meses
- bônus por bairro alvo (neighborhoods.market_heat_score)

Pega geocode se ausente via src.enricher.geocode_address (se existir).
Registra run em agent_runs.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

AGENT_NAME = "distress"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org/bot{token}"

# Limite p/ paginação
SIGNAL_BATCH = 500


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_distress_scorer() -> dict[str, int]:
    """Score todos os sinais ativos e UPDATE em off_market_signals."""
    stats = {"processed": 0, "updated": 0, "failed": 0, "geocoded": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        heat_map = _load_neighborhood_heat(db)

        offset = 0
        while True:
            resp = (
                db.table("off_market_signals")
                .select(
                    "id, source, signal_type, neighborhood, address, "
                    "latitude, longitude, estimated_value, event_date, "
                    "raw_payload, city"
                )
                .eq("is_active", True)
                .range(offset, offset + SIGNAL_BATCH - 1)
                .execute()
            )
            rows = resp.data or []
            if not rows:
                break

            for row in rows:
                stats["processed"] += 1
                try:
                    # Geocode opcional
                    if not row.get("latitude") or not row.get("longitude"):
                        coords = _maybe_geocode(row.get("address"), row.get("city"))
                        if coords:
                            db.table("off_market_signals").update({
                                "latitude": coords[0],
                                "longitude": coords[1],
                            }).eq("id", row["id"]).execute()
                            row["latitude"] = coords[0]
                            row["longitude"] = coords[1]
                            stats["geocoded"] += 1

                    score, reasons = _score_signal(row, heat_map)
                    db.table("off_market_signals").update({
                        "distress_score": score,
                        "distress_reasons": reasons,
                        "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", row["id"]).execute()
                    stats["updated"] += 1
                except Exception:
                    stats["failed"] += 1
                    logger.exception(f"[{AGENT_NAME}] Failed scoring id={row.get('id')}")

            if len(rows) < SIGNAL_BATCH:
                break
            offset += SIGNAL_BATCH

        logger.info(
            f"[{AGENT_NAME}] Done: processed={stats['processed']} "
            f"updated={stats['updated']} geocoded={stats['geocoded']} "
            f"failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{AGENT_NAME}] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def send_daily_top_telegram(n: int = 5) -> dict[str, int]:
    """[DESATIVADO 2026-05-13 por decisão do user]

    Off-market signals (leilões, etc) NÃO devem mais virar alertas Telegram.
    Apenas oportunidades de TERRENO (via src/notifier.py) geram alertas.

    Esta função permanece como no-op para compat com main.py + GitHub Actions.
    Para reativar: remover o early-return abaixo.
    """
    logger.info(f"[{AGENT_NAME}] Telegram alerts desativados (decisão produto)")
    return {"sent": 0, "failed": 0, "disabled": True}
    # --- código original abaixo (mantido para histórico) ---
    stats = {"sent": 0, "failed": 0}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error(f"[{AGENT_NAME}] TELEGRAM_BOT_TOKEN/CHAT_ID não setados")
        return stats

    db = get_client()
    try:
        resp = (
            db.table("off_market_signals")
            .select(
                "id, source, signal_type, title, description, address, "
                "neighborhood, estimated_value, area_m2, event_date, url, "
                "distress_score, distress_reasons, latitude, longitude"
            )
            .eq("is_active", True)
            .not_.is_("distress_score", "null")
            .order("distress_score", desc=True)
            .limit(n)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            logger.info(f"[{AGENT_NAME}] Sem sinais distress p/ enviar")
            return stats

        header = f"*🎯 TOP {len(rows)} OFF-MARKET — DISTRESS DO DIA*"
        _send_text(header)

        for row in rows:
            try:
                msg = _format_signal_msg(row)
                _send_text(msg)
                stats["sent"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{AGENT_NAME}] Falha enviar id={row.get('id')}")

        logger.info(f"[{AGENT_NAME}] Telegram top: {stats}")
    except Exception:
        logger.exception(f"[{AGENT_NAME}] send_daily_top_telegram failed")

    return stats


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_signal(row: dict[str, Any], heat_map: dict[str, float]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    source = row.get("source")
    payload = row.get("raw_payload") or {}

    if source == "leilao_caixa":
        # +40 se lance mínimo < avaliação. Sem campo separado de "avaliação",
        # usamos heurística: payload pode trazer dois valores.
        estimated = _f(row.get("estimated_value"))
        avaliacao = _f(payload.get("avaliacao") or payload.get("valor_avaliacao"))
        if estimated and avaliacao and estimated < avaliacao:
            score += 40
            reasons.append("leilão Caixa com lance abaixo da avaliação (+40)")
        elif estimated:
            # Sem avaliação explícita — leilão por si só é distress
            score += 25
            reasons.append("leilão Caixa (+25)")

    elif source == "iptu_devedor":
        anos = _f(payload.get("anos_atraso"))
        if anos and anos > 3:
            score += 30
            reasons.append(f"IPTU em atraso há {anos:.0f} anos (+30)")
        else:
            score += 15
            reasons.append("IPTU em dívida ativa (+15)")

    elif source == "inventario_tjsp":
        fase = (payload.get("fase") or "").lower()
        movs = payload.get("movimentos") or []
        n_movs = len(movs) if isinstance(movs, list) else 0
        if "partilha" in fase or "sentença" in fase or n_movs >= 30:
            score += 25
            reasons.append("inventário em fase avançada (+25)")
        else:
            score += 12
            reasons.append("inventário em andamento (+12)")

    elif source == "alvara_prefeitura":
        meses_caduco = _f(payload.get("meses_caducado"))
        if meses_caduco and meses_caduco > 12:
            score += 20
            reasons.append(f"alvará caducado há {meses_caduco:.0f} meses (+20)")
        else:
            score += 8
            reasons.append("alvará registrado (+8)")

    elif source == "leilao_judicial":
        score += 30
        reasons.append("leilão judicial (+30)")

    # Bônus por bairro alvo
    neigh = (row.get("neighborhood") or "").strip().lower()
    if neigh and neigh in heat_map:
        heat = heat_map[neigh]
        bonus = round(min(heat, 100) * 0.15, 1)  # até +15
        if bonus > 0:
            score += bonus
            reasons.append(f"bairro alvo {row['neighborhood']} (+{bonus})")

    score = max(0.0, min(score, 100.0))
    return round(score, 1), reasons


def _load_neighborhood_heat(db: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    try:
        resp = (
            db.table("neighborhoods")
            .select("name, market_heat_score")
            .not_.is_("market_heat_score", "null")
            .execute()
        )
        for n in (resp.data or []):
            name = (n.get("name") or "").strip().lower()
            score = n.get("market_heat_score")
            if name and score is not None:
                out[name] = float(score)
    except Exception:
        logger.exception(f"[{AGENT_NAME}] Failed to load neighborhoods")
    return out


def _maybe_geocode(address: Optional[str], city: Optional[str]) -> Optional[tuple[float, float]]:
    if not address:
        return None
    try:
        from src import enricher  # type: ignore
        fn = getattr(enricher, "geocode_address", None)
        if not callable(fn):
            return None
        q = f"{address}, {city or 'Marília'}, SP, Brasil"
        result = fn(q)
        if result and isinstance(result, (tuple, list)) and len(result) == 2:
            return float(result[0]), float(result[1])
    except Exception:
        logger.debug(f"[{AGENT_NAME}] geocode skipped", exc_info=True)
    return None


def _f(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _format_signal_msg(row: dict[str, Any]) -> str:
    score = row.get("distress_score") or 0
    src = row.get("source") or "?"
    title = row.get("title") or "Sinal off-market"
    neigh = row.get("neighborhood") or "?"
    address = row.get("address") or ""
    value = _f(row.get("estimated_value"))
    area = _f(row.get("area_m2"))
    event = row.get("event_date")
    url = row.get("url") or ""
    reasons = row.get("distress_reasons") or []
    lat = row.get("latitude")
    lng = row.get("longitude")

    lines = [
        f"*🚩 {title}*",
        f"Distress: *{float(score):.0f}/100*",
        f"Fonte: `{src}`",
        f"📍 {neigh}",
    ]
    if address:
        lines.append(f"   {address}")
    if value:
        lines.append(f"💰 Valor estimado: R$ {value:,.0f}")
    if area:
        lines.append(f"📐 Área: {area:,.0f} m²")
    if event:
        lines.append(f"📅 Evento: {event[:10]}")
    if reasons:
        lines.append("")
        lines.append("*Razões:*")
        for r in reasons[:6]:
            lines.append(f"• {r}")
    if lat and lng:
        lines.append(f"\n[📍 Mapa](https://maps.google.com/?q={lat},{lng})")
    if url:
        lines.append(f"[🔗 Fonte]({url})")

    return "\n".join(lines)


def _send_text(text: str) -> None:
    url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendMessage"
    resp = httpx.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# agent_runs
# ---------------------------------------------------------------------------

def _start_run(db: Any) -> Optional[int]:
    try:
        r = db.table("agent_runs").insert({
            "agent_name": AGENT_NAME,
            "status": "running",
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception:
        logger.exception(f"[{AGENT_NAME}] Failed to start agent_runs")
        return None


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
        "items_processed": stats.get("processed", 0),
        "items_updated": stats.get("updated", 0),
        "items_failed": stats.get("failed", 0),
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.exception(f"[{AGENT_NAME}] Failed to update agent_runs")

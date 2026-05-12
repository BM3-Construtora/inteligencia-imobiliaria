"""Construction Timeline — cruza Alvará × Habite-se para extrair prazo real de obra.

Match strategy (em ordem de prioridade):
    1. process_number / alvara_reference exato
       habite_se_records.alvara_reference == off_market_signals.source_id
       (ou == process_number extraído da description do alvará).
       Confiabilidade: ALTA. Único caso onde temos certeza do par.

    2. Endereço normalizado + área ±10% + janela 6-48 meses
       normalize_address(alvara.address) == normalize_address(habite_se.address)
       AND abs(area_m2_alvara - area_built_m2) / area_m2_alvara <= 0.10
       AND 180 <= (habite_se.issue_date - alvara.first_seen_at) <= 1460 dias.
       Confiabilidade: MÉDIA. Fallback quando o alvara_reference não preenche.

Cada match vira 1 linha em `construction_timeline` (UNIQUE alvara_signal_id, habite_se_id).
O upsert é idempotente — re-rodar não duplica.

Como `viability.py` consome:
    from src.construction_timeline import get_median_duration_days, get_avg_cost_per_m2
    duration = get_median_duration_days("Jardim Aquarius") or DEFAULT_DURATION_DAYS
    cost_m2  = get_avg_cost_per_m2("Jardim Aquarius") or DEFAULT_CONSTRUCTION_COST_M2

Ambos retornam None se sample_size < 3 (não confiável). Caller deve cair no default.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from src.address import normalize_address
from src.db import get_client

logger = logging.getLogger(__name__)

# Janela mínima/máxima entre alvará e habite-se (em dias)
MIN_CONSTRUCTION_DAYS = 180        # < 6 meses: provavelmente não é a mesma obra
MAX_CONSTRUCTION_DAYS = 48 * 30    # > 48 meses: obra estagnada, par duvidoso

# Tolerância de área no fallback (10%)
AREA_TOLERANCE = 0.10

# Mínimo de amostras para estatística confiável por bairro
MIN_SAMPLE_SIZE = 3

# Lookback: só consideramos pares dos últimos 5 anos
LOOKBACK_YEARS = 5

# Regex para extrair número de processo da description do alvará
# Ex: "Processo 12345/2024", "Proc. 1234/23", "12345/2024"
PROCESS_NUMBER_RE = re.compile(r"\b(\d{3,6}\s*/\s*\d{2,4})\b")


def run_join_analyzer() -> dict[str, int]:
    """Cruza alvarás × habite-se e popula `construction_timeline`.

    Returns:
        Stats: matched, unmatched_alvaras, unmatched_habite_se,
               matched_by_process, matched_by_address.
    """
    db = get_client()
    stats = {
        "matched": 0,
        "matched_by_process": 0,
        "matched_by_address": 0,
        "unmatched_alvaras": 0,
        "unmatched_habite_se": 0,
    }

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "construction_timeline", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_YEARS)).isoformat()

        alvaras = _fetch_alvaras(db, cutoff)
        habite_records = _fetch_habite_se(db, cutoff)

        logger.info(
            f"[construction_timeline] {len(alvaras)} alvarás, "
            f"{len(habite_records)} habite-se a cruzar"
        )

        if not alvaras or not habite_records:
            logger.info("[construction_timeline] Sem dados para cruzar — saindo cedo")
            stats["unmatched_alvaras"] = len(alvaras)
            stats["unmatched_habite_se"] = len(habite_records)
            _finish_run(db, run_id, "completed", stats)
            return stats

        # Indexes auxiliares
        # 1) por process_number/source_id (case-insensitive, sem espaços)
        alvara_by_process: dict[str, dict[str, Any]] = {}
        for a in alvaras:
            keys = _extract_alvara_keys(a)
            for k in keys:
                alvara_by_process.setdefault(k, a)

        used_alvara_ids: set[int] = set()
        used_habite_ids: set[int] = set()

        # 2) Pass 1 — match por process_number
        unmatched_habite: list[dict[str, Any]] = []
        for h in habite_records:
            ref = _normalize_process_key(h.get("alvara_reference") or h.get("process_number") or "")
            if ref and ref in alvara_by_process:
                a = alvara_by_process[ref]
                if a["id"] in used_alvara_ids:
                    unmatched_habite.append(h)
                    continue
                row = _build_timeline_row(a, h, "process_number")
                if row and _upsert_timeline(db, row):
                    stats["matched"] += 1
                    stats["matched_by_process"] += 1
                    used_alvara_ids.add(a["id"])
                    used_habite_ids.add(h["id"])
                    continue
            unmatched_habite.append(h)

        # 3) Pass 2 — fallback por endereço + área + janela temporal
        remaining_alvaras = [a for a in alvaras if a["id"] not in used_alvara_ids]
        for h in unmatched_habite:
            match = _find_address_match(h, remaining_alvaras, used_alvara_ids)
            if not match:
                continue
            row = _build_timeline_row(match, h, "address_area_window")
            if row and _upsert_timeline(db, row):
                stats["matched"] += 1
                stats["matched_by_address"] += 1
                used_alvara_ids.add(match["id"])
                used_habite_ids.add(h["id"])

        stats["unmatched_alvaras"] = len(alvaras) - len(used_alvara_ids)
        stats["unmatched_habite_se"] = len(habite_records) - len(used_habite_ids)

        logger.info(
            f"[construction_timeline] Done: {stats['matched']} matched "
            f"({stats['matched_by_process']} por processo, "
            f"{stats['matched_by_address']} por endereço) — "
            f"{stats['unmatched_alvaras']} alvarás sem habite-se, "
            f"{stats['unmatched_habite_se']} habite-se órfãos"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[construction_timeline] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


# ---------------------------------------------------------------------------
# Helpers consumidos pelo viability.py
# ---------------------------------------------------------------------------

def get_median_duration_days(neighborhood: str) -> Optional[int]:
    """Retorna mediana de prazo de obra (dias) para o bairro.

    Returns None se sample_size < MIN_SAMPLE_SIZE. Caller deve cair no default.
    """
    if not neighborhood:
        return None
    db = get_client()
    try:
        result = (
            db.table("v_construction_stats_by_neighborhood")
            .select("median_duration_days, sample_size")
            .eq("neighborhood", neighborhood)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("[construction_timeline] get_median_duration_days falhou")
        return None

    if not result.data:
        return None
    row = result.data[0]
    if (row.get("sample_size") or 0) < MIN_SAMPLE_SIZE:
        return None
    val = row.get("median_duration_days")
    return int(val) if val is not None else None


def get_avg_cost_per_m2(neighborhood: str) -> Optional[float]:
    """Retorna mediana de custo declarado por m² (R$) para o bairro.

    Returns None se sample_size < MIN_SAMPLE_SIZE ou sem custo declarado.
    """
    if not neighborhood:
        return None
    db = get_client()
    try:
        result = (
            db.table("v_construction_stats_by_neighborhood")
            .select("median_cost_per_m2, sample_size")
            .eq("neighborhood", neighborhood)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("[construction_timeline] get_avg_cost_per_m2 falhou")
        return None

    if not result.data:
        return None
    row = result.data[0]
    if (row.get("sample_size") or 0) < MIN_SAMPLE_SIZE:
        return None
    val = row.get("median_cost_per_m2")
    return float(val) if val is not None else None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _fetch_alvaras(db: Any, cutoff_iso: str) -> list[dict[str, Any]]:
    """Busca alvarás de construção dos últimos N anos."""
    try:
        result = (
            db.table("off_market_signals")
            .select(
                "id, source_id, description, address, neighborhood, "
                "area_m2, first_seen_at, event_date"
            )
            .eq("source", "alvara_prefeitura")
            .eq("signal_type", "permit")
            .gte("first_seen_at", cutoff_iso)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("[construction_timeline] _fetch_alvaras falhou")
        return []


def _fetch_habite_se(db: Any, cutoff_iso: str) -> list[dict[str, Any]]:
    """Busca registros de habite-se dos últimos N anos."""
    try:
        result = (
            db.table("habite_se_records")
            .select(
                "id, issue_date, process_number, alvara_reference, "
                "address, neighborhood, area_built_m2, declared_cost"
            )
            .gte("first_seen_at", cutoff_iso)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("[construction_timeline] _fetch_habite_se falhou")
        return []


def _extract_alvara_keys(alvara: dict[str, Any]) -> list[str]:
    """Gera chaves possíveis de match: source_id + processos extraídos da description."""
    keys: list[str] = []
    sid = alvara.get("source_id")
    if sid:
        norm = _normalize_process_key(sid)
        if norm:
            keys.append(norm)
    desc = alvara.get("description") or ""
    for m in PROCESS_NUMBER_RE.findall(desc):
        norm = _normalize_process_key(m)
        if norm:
            keys.append(norm)
    return keys


def _normalize_process_key(raw: str) -> str:
    """Normaliza chave de processo: lowercase, sem espaços/pontos."""
    if not raw:
        return ""
    return re.sub(r"[\s\.\-]", "", raw).lower()


def _find_address_match(
    habite: dict[str, Any],
    alvaras: list[dict[str, Any]],
    used: set[int],
) -> Optional[dict[str, Any]]:
    """Match fallback por endereço normalizado + área ±10% + janela 6-48 meses."""
    h_addr = normalize_address(habite.get("address") or "")
    h_area = _to_float(habite.get("area_built_m2"))
    h_date = _to_date(habite.get("issue_date"))

    if not h_addr or not h_area or not h_date:
        return None

    for a in alvaras:
        if a["id"] in used:
            continue
        a_addr = normalize_address(a.get("address") or "")
        if not a_addr or a_addr != h_addr:
            continue

        a_area = _to_float(a.get("area_m2"))
        if a_area and h_area:
            if abs(a_area - h_area) / a_area > AREA_TOLERANCE:
                continue

        permit_date = _to_date(a.get("event_date")) or _to_date(a.get("first_seen_at"))
        if not permit_date:
            continue

        days = (h_date - permit_date).days
        if days < MIN_CONSTRUCTION_DAYS or days > MAX_CONSTRUCTION_DAYS:
            continue

        return a

    return None


def _build_timeline_row(
    alvara: dict[str, Any],
    habite: dict[str, Any],
    strategy: str,
) -> Optional[dict[str, Any]]:
    """Monta a linha de construction_timeline. Retorna None se dados insuficientes."""
    permit_date = _to_date(alvara.get("event_date")) or _to_date(alvara.get("first_seen_at"))
    completion_date = _to_date(habite.get("issue_date"))
    if not permit_date or not completion_date:
        return None

    duration = (completion_date - permit_date).days
    if duration <= 0:
        # habite-se antes do alvará — par inválido
        return None

    area = _to_float(habite.get("area_built_m2")) or _to_float(alvara.get("area_m2"))
    cost = _to_float(habite.get("declared_cost"))
    cost_per_m2 = (cost / area) if (cost and area and area > 0) else None

    neighborhood = habite.get("neighborhood") or alvara.get("neighborhood")

    return {
        "alvara_signal_id": alvara["id"],
        "habite_se_id": habite["id"],
        "permit_date": permit_date.isoformat(),
        "completion_date": completion_date.isoformat(),
        "duration_days": duration,
        "neighborhood": neighborhood,
        "area_m2": area,
        "declared_cost_brl": cost,
        "cost_per_m2": cost_per_m2,
        "match_strategy": strategy,
    }


def _upsert_timeline(db: Any, row: dict[str, Any]) -> bool:
    """Upsert idempotente em construction_timeline (UNIQUE alvara_signal_id, habite_se_id)."""
    try:
        db.table("construction_timeline").upsert(
            row, on_conflict="alvara_signal_id,habite_se_id"
        ).execute()
        return True
    except Exception:
        logger.exception(
            f"[construction_timeline] upsert falhou para "
            f"alvara={row.get('alvara_signal_id')} habite={row.get('habite_se_id')}"
        )
        return False


def _to_date(val: Any) -> Optional[date]:
    """Converte ISO string ou datetime em date."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.strptime(val[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
    return None


def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (TypeError, ValueError):
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
        "items_processed": stats.get("matched", 0),
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.exception("[construction_timeline] _finish_run falhou")

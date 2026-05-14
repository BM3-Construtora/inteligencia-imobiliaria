"""Enriquecimento de CNPJ para construtoras cadastradas em construtoras_rating.

Fonte: open.cnpja.com — API pública, sem autenticação, rate limit ~3 req/s.
  https://open.cnpja.com/office/{cnpj}

Regras de negócio:
  - Reprocessa apenas CNPJs nunca enriquecidos ou com cnpj_enriched_at > 30 dias.
  - CPFs de sócios nunca são armazenados em claro — somente SHA-256 dos dígitos.
  - Sleep de 0.4 s entre chamadas para respeitar o rate limit.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "cnpj_construtoras"
API_BASE = "https://open.cnpja.com/office/{cnpj}"
TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.4

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_PORTE_MAP = {
    "mei": "me",
    "me": "me",
    "microempresa": "me",
    "microempreendedor individual": "me",
    "epp": "epp",
    "empresa de pequeno porte": "epp",
}


def run_cnpj_enricher() -> dict[str, int]:
    """Enriquece CNPJs de construtoras_rating via open.cnpja.com."""
    stats = {"processed": 0, "enriched": 0, "failed": 0, "skipped": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        rows = _fetch_pending(db)
        logger.info(f"[{SOURCE}] CNPJs pendentes: {len(rows)}")

        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
            for row in rows:
                stats["processed"] += 1
                cnpj_raw = row.get("cnpj") or ""
                cnpj = re.sub(r"\D", "", cnpj_raw)

                if len(cnpj) != 14:
                    logger.warning(f"[{SOURCE}] CNPJ inválido ignorado: {cnpj_raw!r}")
                    stats["skipped"] += 1
                    continue

                try:
                    payload = _fetch_cnpj(client, cnpj)
                except Exception:
                    logger.exception(f"[{SOURCE}] Falha na API para CNPJ {cnpj}")
                    stats["failed"] += 1
                    time.sleep(SLEEP_BETWEEN_REQUESTS)
                    continue

                if payload is None:
                    stats["skipped"] += 1
                    time.sleep(SLEEP_BETWEEN_REQUESTS)
                    continue

                update = _build_update(payload)

                try:
                    db.table("construtoras_rating").update(update).eq("id", row["id"]).execute()
                    stats["enriched"] += 1
                except Exception:
                    logger.exception(f"[{SOURCE}] upsert falhou: id={row.get('id')}")
                    stats["failed"] += 1

                time.sleep(SLEEP_BETWEEN_REQUESTS)

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} enriched={stats['enriched']} "
            f"failed={stats['failed']} skipped={stats['skipped']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Enricher falhou")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


# ---------------------------------------------------------------------------
# Busca de registros pendentes
# ---------------------------------------------------------------------------

def _fetch_pending(db: Any) -> list[dict[str, Any]]:
    try:
        r = (
            db.table("construtoras_rating")
            .select("id, cnpj")
            .not_.is_("cnpj", "null")
            .or_("cnpj_enriched_at.is.null,cnpj_enriched_at.lt.now()-interval '30 days'")
            .execute()
        )
        return r.data or []
    except Exception:
        logger.exception(f"[{SOURCE}] Falha ao buscar CNPJs pendentes")
        return []


# ---------------------------------------------------------------------------
# API open.cnpja.com
# ---------------------------------------------------------------------------

def _fetch_cnpj(client: httpx.Client, cnpj: str) -> dict[str, Any] | None:
    url = API_BASE.format(cnpj=cnpj)
    resp = client.get(url)

    if resp.status_code == 404:
        logger.warning(f"[{SOURCE}] CNPJ não encontrado: {cnpj}")
        return None

    if resp.status_code != 200:
        logger.warning(f"[{SOURCE}] HTTP {resp.status_code} para CNPJ {cnpj}")
        return None

    return resp.json()


# ---------------------------------------------------------------------------
# Transformação de payload
# ---------------------------------------------------------------------------

def _build_update(data: dict[str, Any]) -> dict[str, Any]:
    razao_social = data.get("company", {}).get("name") or data.get("alias") or None

    situacao_id = (data.get("status") or {}).get("id") or None
    situacao_cadastral = str(situacao_id).upper() if situacao_id else None

    data_abertura = data.get("founded") or None

    capital_raw = data.get("capital")
    capital_social: float | None = None
    try:
        capital_social = float(capital_raw) if capital_raw is not None else None
    except (TypeError, ValueError):
        pass

    nature_text = ((data.get("nature") or {}).get("text") or "").lower()
    porte = _map_porte(nature_text)

    socios = _extract_socios(data.get("members") or [])

    activities = data.get("activities") or []
    cnae_principal = (activities[0].get("text") if activities else None) or None

    emails = data.get("emails") or []
    email = (emails[0].get("address") if emails else None) or None

    phones = data.get("phones") or []
    telefone = (phones[0].get("number") if phones else None) or None

    address_obj = data.get("address") or {}
    endereco_cnpj = _build_address(address_obj) or None

    cnpj_risco = _calc_risco(situacao_cadastral, capital_social)

    return {
        "razao_social": razao_social,
        "situacao_cadastral": situacao_cadastral,
        "data_abertura": data_abertura,
        "capital_social": capital_social,
        "porte": porte,
        "socios": socios,
        "cnae_principal": cnae_principal,
        "email": email,
        "telefone": telefone,
        "endereco_cnpj": endereco_cnpj,
        "cnpj_risco": cnpj_risco,
        "cnpj_enriched_at": datetime.now(timezone.utc).isoformat(),
    }


def _map_porte(nature_text: str) -> str:
    for key, value in _PORTE_MAP.items():
        if key in nature_text:
            return value
    return "media"


def _extract_socios(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for m in members:
        person = m.get("person") or {}
        nome = person.get("name") or m.get("name") or None
        cpf_raw = person.get("taxId") or person.get("cpf") or ""
        cpf_digits = re.sub(r"\D", "", str(cpf_raw))
        cpf_hash = (
            hashlib.sha256(cpf_digits.encode()).hexdigest()
            if len(cpf_digits) == 11
            else None
        )
        cargo = (m.get("role") or {}).get("text") or m.get("role") or None
        entrada = m.get("since") or None
        result.append({
            "nome": nome,
            "cpf_hash": cpf_hash,
            "cargo": cargo,
            "entrada": entrada,
        })
    return result


def _build_address(addr: dict[str, Any]) -> str | None:
    parts = [
        addr.get("street"),
        addr.get("number"),
        addr.get("neighborhood"),
    ]
    filled = [str(p).strip() for p in parts if p]
    return ", ".join(filled) if filled else None


def _calc_risco(situacao: str | None, capital: float | None) -> str:
    if situacao and situacao != "ATIVA":
        return "critico"
    if capital is not None and capital < 10_000:
        return "critico"
    if capital is not None and capital < 50_000:
        return "alto"
    if capital is not None and capital < 200_000:
        return "medio"
    return "baixo"


# ---------------------------------------------------------------------------
# agent_runs
# ---------------------------------------------------------------------------

def _start_run(db: Any) -> int | None:
    try:
        r = db.table("agent_runs").insert({
            "agent_name": f"collector_{SOURCE}",
            "status": "running",
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception:
        logger.exception(f"[{SOURCE}] Failed to start agent_runs")
        return None


def _finish_run(
    db: Any,
    run_id: int | None,
    status: str,
    stats: dict[str, int],
    error: str | None = None,
) -> None:
    if not run_id:
        return
    update: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["processed"],
        "items_created": stats.get("enriched", 0),
        "items_failed": stats["failed"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.exception(f"[{SOURCE}] Failed to update agent_runs")

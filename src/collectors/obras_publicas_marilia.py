"""Coleta obras públicas municipais de Marília-SP.

Fonte: API de Dados Abertos da Prefeitura de Marília
  https://www.marilia.sp.gov.br/portal/dados-abertos/obras/{year}

JSON público, sem autenticação. Retorna lista de obras com título, categoria,
situação, valor contratado, datas de execução e descrição.

Configuração (opcional):
  OBRAS_START_YEAR  — ano inicial (default: 2017)
  OBRAS_END_YEAR    — ano final (default: ano atual)

Uso no sistema:
  obras_por_bairro(neighborhood, years=3) → feature de valorização no AVM.
  Obras de pavimentação/praças/escolas concluídas nos últimos N anos em um
  bairro são proxy de investimento público e correlacionam com apreciação.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "obras_publicas_marilia"
CITY = "Marília"
STATE = "SP"

OBRAS_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/obras/{year}"
_THIS_YEAR = datetime.now().year

OBRAS_START_YEAR = int(os.getenv("OBRAS_START_YEAR", "2017"))
OBRAS_END_YEAR = int(os.getenv("OBRAS_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 30
SLEEP_BETWEEN_YEARS = 1.0

# Extrai bairro da descrição (ex: "na área do Jardim Cavallari")
RE_BAIRRO = re.compile(
    r"(?:bairro|jardim|jd\.?|parque|vila|conjunto|núcleo|residencial|loteamento)\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s]{2,50}?)(?=[,\.;]|$|\s{2})",
    re.IGNORECASE,
)


def run_collector() -> dict[str, int]:
    """Coleta obras públicas e upserta em obras_publicas_marilia."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        records = _collect_all_years()
        logger.info(f"[{SOURCE}] Total obras encontradas: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("obras_publicas_marilia").upsert(
                    _to_row(rec), on_conflict="source_id"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] upsert falhou: {rec.get('source_id')}")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector falhou")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


# ---------------------------------------------------------------------------
# Coleta
# ---------------------------------------------------------------------------

def _collect_all_years() -> list[dict[str, Any]]:
    years = range(OBRAS_START_YEAR, OBRAS_END_YEAR + 1)
    all_records: list[dict[str, Any]] = []
    seen: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in years:
            url = OBRAS_API.format(year=year)
            obras = _fetch_year(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(obras)} obras")

            for obra in obras:
                rec = _parse_obra(obra, year)
                if rec["source_id"] not in seen:
                    seen.add(rec["source_id"])
                    all_records.append(rec)

            if year != OBRAS_END_YEAR:
                time.sleep(SLEEP_BETWEEN_YEARS)

    return all_records


def _fetch_year(client: httpx.Client, url: str, year: int) -> list[dict[str, Any]]:
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"[{SOURCE}] Ano {year}: HTTP {resp.status_code}")
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        for key in ("dados", "data", "items", "obras", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        logger.warning(f"[{SOURCE}] Ano {year}: formato inesperado — keys={list(data.keys())[:5]}")
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Erro ao buscar obras {year}")
        return []


def _parse_obra(obra: dict[str, Any], year: int) -> dict[str, Any]:
    titulo = (obra.get("titulo") or "").strip()
    slug = re.sub(r"[^\w]", "_", titulo.lower())[:60]
    source_id = f"{year}_{slug}" if slug else f"{year}_{hashlib.sha1(str(obra).encode()).hexdigest()[:12]}"

    neighborhood = _extract_neighborhood(obra)

    return {
        "source_id": source_id,
        "year": year,
        "titulo": titulo,
        "categoria": (obra.get("categoria") or "").strip() or None,
        "situacao": (obra.get("situacao") or "").strip() or None,
        "neighborhood": neighborhood,
        "valor": _to_float(obra.get("valor")),
        "data_inicio": _parse_date(obra.get("dataExecucaoInicio")),
        "data_fim": _parse_date(obra.get("dataExecucaoFim")),
        "data_atualizacao": _parse_ts(obra.get("dataAtualizacao")),
        "descricao": (obra.get("descricao") or "").strip()[:2000] or None,
        "raw_payload": obra,
    }


def _extract_neighborhood(obra: dict[str, Any]) -> str | None:
    # Tenta extrair bairro do título primeiro, depois da descrição
    for text in [obra.get("titulo") or "", obra.get("descricao") or ""]:
        m = RE_BAIRRO.search(text)
        if m:
            return m.group(1).strip().title()
    return None


def _parse_date(raw: Any) -> str | None:
    if not raw:
        return None
    s = str(raw)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_ts(raw: Any) -> str | None:
    if not raw:
        return None
    s = str(raw)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": rec["source_id"],
        "year": rec["year"],
        "titulo": rec["titulo"],
        "categoria": rec.get("categoria"),
        "situacao": rec.get("situacao"),
        "neighborhood": rec.get("neighborhood"),
        "valor": rec.get("valor"),
        "data_inicio": rec.get("data_inicio"),
        "data_fim": rec.get("data_fim"),
        "data_atualizacao": rec.get("data_atualizacao"),
        "descricao": rec.get("descricao"),
        "raw_payload": rec.get("raw_payload"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


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
    update = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["processed"],
        "items_created": stats["created"],
        "items_failed": stats["failed"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.exception(f"[{SOURCE}] Failed to update agent_runs")


# ---------------------------------------------------------------------------
# Helpers para uso externo (AVM / viability)
# ---------------------------------------------------------------------------

def obras_por_bairro(
    neighborhood: str,
    years: int = 3,
    situacao: str = "Concluído",
    db: Any = None,
) -> list[dict[str, Any]]:
    """Retorna obras concluídas num bairro nos últimos N anos.

    Útil como feature de valorização no AVM:
      obras = obras_por_bairro("Jardim Cavallari", years=3)
      score = sum(1 for o in obras if o["categoria"] in ("Pavimentação", "Praças"))
    """
    if db is None:
        db = get_client()
    cutoff_year = _THIS_YEAR - years
    try:
        r = (
            db.table("obras_publicas_marilia")
            .select("titulo,categoria,situacao,valor,data_fim,neighborhood")
            .ilike("neighborhood", f"%{neighborhood}%")
            .eq("situacao", situacao)
            .gte("year", cutoff_year)
            .execute()
        )
        return r.data or []
    except Exception:
        logger.exception(f"[{SOURCE}] obras_por_bairro falhou")
        return []

"""Coleta licitações de obras públicas de Marília-SP.

Fonte: API de Dados Abertos da Prefeitura de Marília
  https://www.marilia.sp.gov.br/portal/dados-abertos/licitacoes/{year}

JSON público, sem autenticação. Retorna lista de editais com título, modalidade,
situação, datas e número do processo. Filtra por palavras-chave de obras/construção
para manter foco no pipeline imobiliário.

Configuração (opcional):
  LICITACOES_START_YEAR  — ano inicial (default: 2020)
  LICITACOES_END_YEAR    — ano final (default: ano atual)

Uso no sistema:
  licitacoes_por_periodo(year_start, year_end) → pipeline de obras públicas
  planejadas. Cruzar com obras_publicas_marilia para rastrear ciclo edital→execução.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "licitacoes_obras_marilia"
CITY = "Marília"
STATE = "SP"

LICITACOES_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/licitacoes/{year}"
_THIS_YEAR = datetime.now().year

LICITACOES_START_YEAR = int(os.getenv("LICITACOES_START_YEAR", "2020"))
LICITACOES_END_YEAR = int(os.getenv("LICITACOES_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 30
SLEEP_BETWEEN_YEARS = 1.0

# Palavras-chave para filtrar editais relacionados a obras/construção
RE_OBRA = re.compile(
    r"obra|constru|reforma|pavimenta|demoli|sanea|drenagem|calçada|"
    r"asfalto|terraplenagem|alvenaria|elétrica|hidráulic|infraestrutura|"
    r"revitaliza|urbaniza|praça|parque|escola|ubs|creche|ginásio|quadra|"
    r"engenharia|arquitetura",
    re.IGNORECASE,
)


def run_collector() -> dict[str, int]:
    """Coleta licitações de obras e upserta em licitacoes_obras_marilia."""
    stats = {"processed": 0, "created": 0, "skipped": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        records = _collect_all_years()
        logger.info(f"[{SOURCE}] Total licitações de obras encontradas: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("licitacoes_obras_marilia").upsert(
                    _to_row(rec), on_conflict="source_id"
                ).execute()
                stats["created"] = stats.get("created", 0) + 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] upsert falhou: {rec.get('source_id')}")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats.get('created',0)} skipped={stats['skipped']} failed={stats['failed']}"
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
    all_records: list[dict[str, Any]] = []
    seen: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in range(LICITACOES_START_YEAR, LICITACOES_END_YEAR + 1):
            url = LICITACOES_API.format(year=year)
            items = _fetch_year(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(items)} editais brutos")

            obra_count = 0
            for item in items:
                if not _is_obra(item):
                    continue
                rec = _parse_item(item, year)
                sid = rec["source_id"]
                if sid not in seen:
                    seen.add(sid)
                    all_records.append(rec)
                    obra_count += 1

            logger.info(f"[{SOURCE}] Ano {year}: {obra_count} licitações de obras filtradas")

            if year != LICITACOES_END_YEAR:
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
        for key in ("dados", "data", "items", "editais", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        logger.warning(f"[{SOURCE}] Ano {year}: formato inesperado — keys={list(data.keys())[:5]}")
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Erro ao buscar licitações {year}")
        return []


def _is_obra(item: dict[str, Any]) -> bool:
    text = f"{item.get('titulo','') or ''} {item.get('descricao','') or ''}"
    return bool(RE_OBRA.search(text))


def _parse_item(item: dict[str, Any], year: int) -> dict[str, Any]:
    num_edital = item.get("numeroEdital") or item.get("numero_edital")
    num_processo = item.get("numeroProcesso") or item.get("numero_processo")

    if num_edital and num_processo:
        source_id = f"{year}_{num_edital}_{num_processo}"
    elif num_edital:
        source_id = f"{year}_{num_edital}"
    else:
        source_id = f"{year}_{hashlib.sha1(str(item).encode()).hexdigest()[:12]}"

    return {
        "source_id": source_id,
        "year": year,
        "numero_edital": _to_int(num_edital),
        "numero_processo": _to_int(num_processo),
        "modalidade": (item.get("modalidade") or "").strip() or None,
        "situacao": (item.get("situacao") or "").strip() or None,
        "titulo": (item.get("titulo") or "").strip(),
        "data_postagem": _parse_ts(item.get("dataPostagem")),
        "data_realizacao": _parse_ts(item.get("dataRealizacao")),
        "data_atualizacao": _parse_ts(item.get("dataAtualizacao")),
        "descricao_html": (item.get("descricao") or "").strip()[:4000] or None,
        "is_obra": True,
        "raw_payload": item,
    }


def _parse_ts(raw: Any) -> str | None:
    if not raw:
        return None
    s = str(raw)[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": rec["source_id"],
        "year": rec["year"],
        "numero_edital": rec.get("numero_edital"),
        "numero_processo": rec.get("numero_processo"),
        "modalidade": rec.get("modalidade"),
        "situacao": rec.get("situacao"),
        "titulo": rec["titulo"],
        "data_postagem": rec.get("data_postagem"),
        "data_realizacao": rec.get("data_realizacao"),
        "data_atualizacao": rec.get("data_atualizacao"),
        "descricao_html": rec.get("descricao_html"),
        "is_obra": rec.get("is_obra", True),
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
        "items_created": stats.get("created", 0),
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
# Helpers para uso externo
# ---------------------------------------------------------------------------

def licitacoes_por_periodo(
    year_start: int,
    year_end: int,
    situacao: str | None = None,
    db: Any = None,
) -> list[dict[str, Any]]:
    """Retorna licitações de obras em um intervalo de anos.

    Útil para cruzar com obras_publicas_marilia (edital → obra em andamento).
    """
    if db is None:
        db = get_client()
    try:
        q = (
            db.table("licitacoes_obras_marilia")
            .select("source_id,year,titulo,modalidade,situacao,data_postagem,data_realizacao,numero_edital")
            .gte("year", year_start)
            .lte("year", year_end)
        )
        if situacao:
            q = q.eq("situacao", situacao)
        r = q.execute()
        return r.data or []
    except Exception:
        logger.exception(f"[{SOURCE}] licitacoes_por_periodo falhou")
        return []

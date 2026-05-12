"""Coleta aprovações de parcelamento de solo (loteamentos e desmembramentos) — Marília-SP.

Fonte: API de Dados Abertos do Diário Oficial Municipal de Marília.
  https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}

Mesmo endpoint usado pelo coletor habite_se_marilia.py. Filtra publicações
relacionadas a parcelamento de solo para rastrear novos loteamentos e
desmembramentos aprovados — sinal antecipado de expansão urbana.

Configuração (opcional):
  PARCELAMENTO_START_YEAR  — ano inicial (default: ano atual - 3)
  PARCELAMENTO_END_YEAR    — ano final (default: ano atual)
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

SOURCE = "parcelamento_solo_marilia"
CITY = "Marília"
STATE = "SP"

DOM_MAR_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}"
_THIS_YEAR = datetime.now().year

PARCELAMENTO_START_YEAR = int(os.getenv("PARCELAMENTO_START_YEAR", str(_THIS_YEAR - 3)))
PARCELAMENTO_END_YEAR = int(os.getenv("PARCELAMENTO_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 60
SLEEP_BETWEEN_YEARS = 2.0

RE_PARCELAMENTO = re.compile(
    r"(?:"
    r"parcelamento\s+(?:do\s+)?solo"
    r"|loteamento"
    r"|desmembramento"
    r"|subdivis[ãa]o\s+(?:de\s+)?(?:gl[eé]ba|terreno|lote)"
    r"|aprovação\s+de\s+lote"
    r"|projeto\s+de\s+loteamento"
    r")"
    r"[^\n]{0,500}",
    re.IGNORECASE,
)
RE_PROCESSO = re.compile(
    r"(?:processo|protocolo|proc\.?)\s*[:nº#]*\s*([\d\./-]{4,})",
    re.IGNORECASE,
)
RE_AREA = re.compile(
    r"(?:[áa]rea\s+(?:total|do\s+terreno|da\s+gl[eé]ba)?|a\.?t\.?)\s*[:=]?\s*"
    r"(\d{1,8}(?:[\.,]\d{1,3})?)\s*m[²2]",
    re.IGNORECASE,
)
RE_LOTES = re.compile(
    r"(\d{1,4})\s*(?:lotes?|unidades?\s+(?:habitacionais?|imobili[áa]rias?))",
    re.IGNORECASE,
)
RE_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_NEIGHBORHOOD = re.compile(
    r"(?:bairro|jardim|jd\.?|parque|vila|conjunto|loteamento)\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s]{2,50}?)(?=[,\.;]|$|\n)",
    re.IGNORECASE,
)
RE_ADDRESS = re.compile(
    r"(?:rua|avenida|av\.|travessa|alameda|estrada)\s+"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w\s\.,Áéíóúâêôãõç-]{3,60},?\s*n?[º°]?\s*\d{1,5}",
    re.IGNORECASE,
)
RE_TIPO = re.compile(
    r"\b(loteamento|desmembramento|parcelamento|subdivis[ãa]o)\b",
    re.IGNORECASE,
)


def run_collector() -> dict[str, int]:
    """Coleta parcelamentos de solo do DOM-MAR e upserta em parcelamento_solo_marilia."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        records = _collect_from_api()
        logger.info(f"[{SOURCE}] Total parcelamentos encontrados: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("parcelamento_solo_marilia").upsert(
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
# Coleta via API dados-abertos DOM-MAR
# ---------------------------------------------------------------------------

def _collect_from_api() -> list[dict[str, Any]]:
    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in range(PARCELAMENTO_START_YEAR, PARCELAMENTO_END_YEAR + 1):
            url = DOM_MAR_API.format(year=year)
            editions = _fetch_editions(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(editions)} edições do DOM")

            for ed in editions:
                text = ed.get("descricao") or ""
                if not text:
                    continue
                if not RE_PARCELAMENTO.search(text):
                    continue

                ed_date = _parse_edition_date(ed)
                ed_id = str(ed.get("edicao") or ed.get("id") or "")
                records = _extract_parcelamentos(text, fallback_date=ed_date, edition_id=ed_id)

                for r in records:
                    if r["source_id"] not in seen_ids:
                        seen_ids.add(r["source_id"])
                        all_records.append(r)

            if year != PARCELAMENTO_END_YEAR:
                time.sleep(SLEEP_BETWEEN_YEARS)

    return all_records


def _fetch_editions(client: httpx.Client, url: str, year: int) -> list[dict[str, Any]]:
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"[{SOURCE}] Ano {year}: HTTP {resp.status_code}")
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        for key in ("dados", "data", "items", "edicoes", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        logger.warning(f"[{SOURCE}] Ano {year}: formato inesperado — keys={list(data.keys())[:5]}")
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Erro ao buscar edições {year}")
        return []


def _parse_edition_date(ed: dict[str, Any]) -> date | None:
    raw = ed.get("data") or ed.get("date") or ed.get("publicacao") or ""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(str(raw)[:19], fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _extract_parcelamentos(
    text: str,
    fallback_date: date | None = None,
    edition_id: str = "",
) -> list[dict[str, Any]]:
    if not text:
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in RE_PARCELAMENTO.finditer(text):
        snippet = text[max(0, m.start() - 150): m.end() + 600]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        proc = _first_match(RE_PROCESSO, snippet)
        area_total = _to_float(_first_match(RE_AREA, snippet))
        lotes_count = _to_int(_first_match(RE_LOTES, snippet))
        issue_date = _extract_date(snippet) or fallback_date
        neighborhood = _first_match(RE_NEIGHBORHOOD, snippet)
        address_m = RE_ADDRESS.search(snippet)
        address = address_m.group(0).strip() if address_m else None

        tipo_m = RE_TIPO.search(m.group(0))
        tipo = tipo_m.group(1).lower() if tipo_m else "parcelamento"

        # source_id: processo se disponível, senão hash do snippet
        if proc:
            normalized = re.sub(r"[^\d]", "", proc)
            source_id = f"{edition_id}_{normalized}" if edition_id else normalized
        else:
            source_id = hashlib.sha1(snippet.encode("utf-8")).hexdigest()[:16]

        if source_id in seen:
            continue
        seen.add(source_id)

        records.append({
            "source_id": source_id,
            "issue_date": issue_date.isoformat() if issue_date else None,
            "process_number": proc,
            "tipo": tipo,
            "neighborhood": neighborhood.strip() if neighborhood else None,
            "address": address,
            "area_total_m2": area_total,
            "lotes_count": lotes_count,
            "snippet": snippet[:1500],
        })

    return records


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return m.group(1) if m.groups() else m.group(0)


def _to_float(val: str | None) -> float | None:
    if not val:
        return None
    try:
        cleaned = val.replace(".", "").replace(",", ".") if "," in val else val
        return float(cleaned)
    except ValueError:
        return None


def _to_int(val: str | None) -> int | None:
    if not val:
        return None
    try:
        return int(re.sub(r"[^\d]", "", val))
    except (ValueError, TypeError):
        return None


def _extract_date(text: str) -> date | None:
    m = RE_DATE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_id": rec["source_id"],
        "issue_date": rec.get("issue_date"),
        "process_number": rec.get("process_number"),
        "tipo": rec.get("tipo"),
        "neighborhood": rec.get("neighborhood"),
        "address": rec.get("address"),
        "area_total_m2": rec.get("area_total_m2"),
        "lotes_count": rec.get("lotes_count"),
        "snippet": rec.get("snippet"),
        "raw_payload": rec,
        "last_seen_at": now,
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

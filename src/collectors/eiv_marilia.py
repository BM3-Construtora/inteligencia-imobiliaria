"""Coleta EIV (Estudo de Impacto de Vizinhança) — DOM-MAR (Marília-SP).

EIV é obrigatório para glebas >5000m² e empreendimentos de grande impacto.
Publicado no DOM antes da aprovação — sinal de pipeline competitivo premium.

Configuração (opcional):
  EIV_START_YEAR  — ano inicial (default: ano atual - 2)
  EIV_END_YEAR    — ano final (default: ano atual)
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
from src.marilia_neighborhoods import validate_neighborhood

logger = logging.getLogger(__name__)

SOURCE = "eiv_marilia"
CITY = "Marília"
STATE = "SP"

DOM_MAR_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}"
_THIS_YEAR = datetime.now().year

EIV_START_YEAR = int(os.getenv("EIV_START_YEAR", str(_THIS_YEAR - 2)))
EIV_END_YEAR = int(os.getenv("EIV_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 60
SLEEP_BETWEEN_YEARS = 2.0

RE_EIV_BLOCK = re.compile(
    r"(?:"
    r"estudo\s+de\s+impacto\s+de\s+vizinhan[çc]a"
    r"|e\.?i\.?v\.?"
    r"|impacto\s+de\s+vizinhan[çc]a"
    r")"
    r"[^\n]{0,600}",
    re.IGNORECASE,
)
RE_NUMERO_EIV = re.compile(
    r"(?:eiv|e\.i\.v\.?)\s*[:nº#]*\s*([\d\.\-/]{3,})", re.IGNORECASE
)
RE_PROCESSO = re.compile(
    r"(?:processo|protocolo|proc\.?)\s*[:nº#]*\s*([\d\./-]{4,})", re.IGNORECASE
)
RE_REQUERENTE = re.compile(
    r"(?:requerente|empreendedor|propriet[áa]rio|interessado)\s*[:]\s*([^\n,;]{3,80})",
    re.IGNORECASE,
)
RE_AREA_GLEBA = re.compile(
    r"(?:[áa]rea\s+(?:da\s+)?gleba|gleba|[áa]rea\s+total)\s*[:=]?\s*"
    r"(\d{1,6}(?:[\.,]\d{1,3})?)\s*m[²2]",
    re.IGNORECASE,
)
RE_UNIDADES = re.compile(
    r"(?:unidades?|apart\.?|lotes?)\s*[:=]?\s*(\d{1,4})",
    re.IGNORECASE,
)
RE_RESULTADO_EIV = re.compile(
    r"(?:resultado|parecer|decis[ãa]o)\s*[:.]?\s*(aprovad[oa]|reprovad[oa]|deferido|indeferido|em\s+an[áa]lise)",
    re.IGNORECASE,
)
RE_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_NEIGHBORHOOD = re.compile(
    r"(?:bairro|jardim|jd\.?|parque|vila|conjunto)\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s]{2,40})",
)
RE_ADDRESS = re.compile(
    r"(?:rua|avenida|av\.|travessa|alameda|estrada|pra[çc]a)\s+"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w\s\.,Áéíóúâêôãõç-]{3,60},?\s*n?[º°]?\s*\d{1,5}",
    re.IGNORECASE,
)


def run_eiv_collector() -> dict[str, int]:
    """Coleta EIVs do DOM-MAR e upserta em eiv_marilia."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        records = _collect_from_api()
        logger.info(f"[{SOURCE}] Total EIVs encontrados: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("eiv_marilia").upsert(
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


def _collect_from_api() -> list[dict[str, Any]]:
    years = range(EIV_START_YEAR, EIV_END_YEAR + 1)
    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in years:
            url = DOM_MAR_API.format(year=year)
            editions = _fetch_editions(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(editions)} edições")

            for ed in editions:
                text = ed.get("descricao") or ""
                if not text or not RE_EIV_BLOCK.search(text):
                    continue

                ed_date = _parse_edition_date(ed)
                ed_id = str(ed.get("edicao") or ed.get("id") or "")
                records = _extract_eivs(text, fallback_date=ed_date, edition_id=ed_id)

                for r in records:
                    if r["source_id"] not in seen_ids:
                        seen_ids.add(r["source_id"])
                        all_records.append(r)

            if year != EIV_END_YEAR:
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


def _extract_eivs(
    text: str,
    fallback_date: date | None = None,
    edition_id: str = "",
) -> list[dict[str, Any]]:
    if not text:
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in RE_EIV_BLOCK.finditer(text):
        snippet = text[max(0, m.start() - 80): m.end() + 500]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        numero_eiv = _first_match(RE_NUMERO_EIV, snippet)
        processo = _first_match(RE_PROCESSO, snippet)
        requerente = _first_match(RE_REQUERENTE, snippet)
        area_gleba = _to_float(_first_match(RE_AREA_GLEBA, snippet))
        unidades = _to_int(_first_match(RE_UNIDADES, snippet))
        resultado_raw = _first_match(RE_RESULTADO_EIV, snippet)
        resultado = _classify_resultado(resultado_raw)
        pub_date = _extract_date(snippet) or fallback_date
        neighborhood = validate_neighborhood(_first_match(RE_NEIGHBORHOOD, snippet))
        address_m = RE_ADDRESS.search(snippet)
        address = address_m.group(0).strip() if address_m else None

        # Descarta fragmentos sem sinal útil
        if not any([numero_eiv, processo, area_gleba, address]):
            continue

        key_parts = [edition_id, _normalize(processo or ""), _normalize(numero_eiv or ""), _normalize(address or "")]
        source_id = hashlib.sha1(":".join(key_parts).encode()).hexdigest()[:20]

        if source_id in seen:
            continue
        seen.add(source_id)

        records.append({
            "source_id": source_id,
            "publication_date": pub_date.isoformat() if pub_date else None,
            "numero_eiv": numero_eiv,
            "numero_processo": processo,
            "requerente": requerente,
            "endereco": address,
            "neighborhood": neighborhood.strip() if neighborhood else None,
            "area_gleba_m2": area_gleba,
            "unidades": unidades,
            "resultado": resultado,
            "snippet": snippet[:1000],
        })

    return records


def _classify_resultado(raw: str | None) -> str:
    if not raw:
        return "em_analise"
    t = raw.lower()
    if re.search(r"aprovad[oa]|deferido", t):
        return "aprovado"
    if re.search(r"reprovad[oa]|indeferido", t):
        return "reprovado"
    return "em_analise"


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
        return int(val.strip())
    except ValueError:
        return None


def _extract_date(text: str) -> date | None:
    m = RE_DATE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]", "", value.lower())


def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_id": rec["source_id"],
        "publication_date": rec.get("publication_date"),
        "numero_eiv": rec.get("numero_eiv"),
        "numero_processo": rec.get("numero_processo"),
        "requerente": rec.get("requerente"),
        "endereco": rec.get("endereco"),
        "neighborhood": rec.get("neighborhood"),
        "city": CITY,
        "state": STATE,
        "area_gleba_m2": rec.get("area_gleba_m2"),
        "unidades": rec.get("unidades"),
        "resultado": rec.get("resultado"),
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

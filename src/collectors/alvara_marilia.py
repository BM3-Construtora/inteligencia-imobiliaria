"""Coleta Alvarás de aprovação de projeto — Seção III-A do DOM-MAR (Marília-SP).

Sinal de 18-36 meses antes do habite-se. Fonte: mesma API do diário oficial
usada por habite_se_marilia.py.

Configuração (opcional):
  ALVARA_START_YEAR  — ano inicial (default: ano atual - 2)
  ALVARA_END_YEAR    — ano final (default: ano atual)
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

SOURCE = "alvara_marilia"
CITY = "Marília"
STATE = "SP"

DOM_MAR_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}"
_THIS_YEAR = datetime.now().year

ALVARA_START_YEAR = int(os.getenv("ALVARA_START_YEAR", str(_THIS_YEAR - 2)))
ALVARA_END_YEAR = int(os.getenv("ALVARA_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 60
SLEEP_BETWEEN_YEARS = 2.0

RE_ALVARA_BLOCK = re.compile(
    r"(?:"
    r"alvará\s+de\s+(?:aprova[çc][ãa]o|constru[çc][ãa]o|licen[çc]a)"
    r"|licen[çc]a\s+de\s+(?:constru[çc][ãa]o|obras?)"
    r"|aprova[çc][ãa]o\s+de\s+projeto"
    r")"
    r"[^\n]{0,600}",
    re.IGNORECASE,
)
RE_NUMERO_ALVARA = re.compile(
    r"alvará\s*[:nº#]*\s*([\d\.\-/]{3,})", re.IGNORECASE
)
RE_PROCESSO = re.compile(
    r"(?:processo|protocolo|proc\.?)\s*[:nº#]*\s*([\d\./-]{4,})", re.IGNORECASE
)
RE_REQUERENTE = re.compile(
    r"(?:requerente|propriet[áa]rio|interessado)\s*[:]\s*([^\n,;]{3,80})",
    re.IGNORECASE,
)
RE_CNPJ = re.compile(
    r"(?:cnpj|cpf)\s*[:.]?\s*([\d\.\-/]{11,})", re.IGNORECASE
)
RE_AREA_CONSTRUIDA = re.compile(
    r"(?:[áa]rea\s+(?:constru[íi]da|total\s+constru[íi]da)|a\.?c\.?)"
    r"\s*[:=]?\s*(\d{1,5}(?:[\.,]\d{1,3})?)\s*m[²2]",
    re.IGNORECASE,
)
RE_UNIDADES = re.compile(
    r"(?:unidades?|apart\.?|lotes?)\s*[:=]?\s*(\d{1,4})",
    re.IGNORECASE,
)
RE_PAVIMENTOS = re.compile(
    r"(?:pavimentos?|andares?|pisos?)\s*[:=]?\s*(\d{1,2})",
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


def run_alvara_collector() -> dict[str, int]:
    """Coleta alvarás do DOM-MAR e upserta em alvaras_marilia."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        records = _collect_from_api()
        logger.info(f"[{SOURCE}] Total alvarás encontrados: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("alvaras_marilia").upsert(
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
    years = range(ALVARA_START_YEAR, ALVARA_END_YEAR + 1)
    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in years:
            url = DOM_MAR_API.format(year=year)
            editions = _fetch_editions(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(editions)} edições")

            for ed in editions:
                text = ed.get("descricao") or ""
                if not text or not RE_ALVARA_BLOCK.search(text):
                    continue

                ed_date = _parse_edition_date(ed)
                ed_id = str(ed.get("edicao") or ed.get("id") or "")
                records = _extract_alvaras(text, fallback_date=ed_date, edition_id=ed_id)

                for r in records:
                    if r["source_id"] not in seen_ids:
                        seen_ids.add(r["source_id"])
                        all_records.append(r)

            if year != ALVARA_END_YEAR:
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


def _extract_alvaras(
    text: str,
    fallback_date: date | None = None,
    edition_id: str = "",
) -> list[dict[str, Any]]:
    if not text:
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in RE_ALVARA_BLOCK.finditer(text):
        snippet = text[max(0, m.start() - 80): m.end() + 500]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        numero_alvara = _first_match(RE_NUMERO_ALVARA, snippet)
        processo = _first_match(RE_PROCESSO, snippet)
        requerente = _first_match(RE_REQUERENTE, snippet)
        cnpj = _first_match(RE_CNPJ, snippet)
        area = _to_float(_first_match(RE_AREA_CONSTRUIDA, snippet))
        unidades = _to_int(_first_match(RE_UNIDADES, snippet))
        pavimentos = _to_int(_first_match(RE_PAVIMENTOS, snippet))
        pub_date = _extract_date(snippet) or fallback_date
        neighborhood = validate_neighborhood(_first_match(RE_NEIGHBORHOOD, snippet))
        address_m = RE_ADDRESS.search(snippet)
        address = address_m.group(0).strip() if address_m else None

        tipo_alvara = _classify_alvara_type(snippet)
        uso = _classify_uso(snippet)

        # Descarta se não houver sinal mínimo de obra
        if not any([numero_alvara, processo, area, address]):
            continue

        # Gera source_id determinístico
        key_parts = [edition_id, _normalize(processo or ""), _normalize(numero_alvara or ""), _normalize(address or ""), str(area or "")]
        source_id = hashlib.sha1(":".join(key_parts).encode()).hexdigest()[:20]

        if source_id in seen:
            continue
        seen.add(source_id)

        records.append({
            "source_id": source_id,
            "publication_date": pub_date.isoformat() if pub_date else None,
            "numero_alvara": numero_alvara,
            "numero_processo": processo,
            "tipo_alvara": tipo_alvara,
            "uso": uso,
            "requerente": requerente,
            "cnpj_cpf": cnpj,
            "endereco": address,
            "neighborhood": neighborhood.strip() if neighborhood else None,
            "area_construida_m2": area,
            "unidades": unidades,
            "pavimentos": pavimentos,
            "snippet": snippet[:1000],
        })

    return records


def _classify_alvara_type(text: str) -> str:
    t = text.lower()
    if re.search(r"demoli[çc][ãa]o", t):
        return "demolicao"
    if re.search(r"reforma", t):
        return "reforma"
    if re.search(r"licen[çc]a\s+de\s+constru[çc][ãa]o", t):
        return "licenca_construcao"
    return "aprovacao_projeto"


def _classify_uso(text: str) -> str:
    t = text.lower()
    usos = {
        "comercial": bool(re.search(r"comerci[ao]l|loja|sal[ãa]o|escrit[oó]rio", t)),
        "industrial": bool(re.search(r"industrial|galpão|dep[oó]sito|armazém", t)),
        "misto": bool(re.search(r"misto|uso\s+misto", t)),
    }
    for k, v in usos.items():
        if v:
            return k
    return "residencial"


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
        "numero_alvara": rec.get("numero_alvara"),
        "numero_processo": rec.get("numero_processo"),
        "tipo_alvara": rec.get("tipo_alvara"),
        "uso": rec.get("uso"),
        "requerente": rec.get("requerente"),
        "cnpj_cpf": rec.get("cnpj_cpf"),
        "endereco": rec.get("endereco"),
        "neighborhood": rec.get("neighborhood"),
        "city": CITY,
        "state": STATE,
        "area_construida_m2": rec.get("area_construida_m2"),
        "unidades": rec.get("unidades"),
        "pavimentos": rec.get("pavimentos"),
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

"""Coleta atas do CMDU (Conselho Municipal de Desenvolvimento Urbano) — Marília-SP.

Publicadas no DOM-MAR. Contêm aprovações de EIV, discussões de zoneamento,
decisões de loteamento — sinal com 6-12 meses de antecedência sobre qualquer portal.

Plano Diretor 2026: as atas de 2025-2026 são especialmente valiosas (revisão em curso).

Configuração (opcional):
  CMDU_START_YEAR  — ano inicial (default: ano atual - 2)
  CMDU_END_YEAR    — ano final (default: ano atual)
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

SOURCE = "cmdu_marilia"
DOM_MAR_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}"
_THIS_YEAR = datetime.now().year

CMDU_START_YEAR = int(os.getenv("CMDU_START_YEAR", str(_THIS_YEAR - 2)))
CMDU_END_YEAR = int(os.getenv("CMDU_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 60
SLEEP_BETWEEN_YEARS = 2.0

RE_CMDU_BLOCK = re.compile(
    r"(?:"
    r"conselho\s+municipal\s+de\s+desenvolvimento\s+urbano"
    r"|c\.?m\.?d\.?u\.?"
    r"|ata\s+(?:da\s+)?reuni[ãa]o\s+(?:do\s+)?(?:cmdu|conselho)"
    r"|reuni[ãa]o\s+(?:ordin[áa]ria|extraordin[áa]ria)\s+(?:do\s+)?cmdu"
    r")"
    r"[^\n]{0,800}",
    re.IGNORECASE,
)
RE_ATA_NUMBER = re.compile(
    r"(?:ata|reuni[ãa]o)\s*(?:n[º°]|num\.?)?\s*(\d{1,4}(?:/\d{4})?)",
    re.IGNORECASE,
)
RE_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_PAUTA = re.compile(
    r"(?:pauta|ordem\s+do\s+dia|processo|aprecia[çc][ãa]o)\s*[:.]?\s*([^\n]{10,200})",
    re.IGNORECASE,
)
RE_APROVACAO = re.compile(
    r"(?:aprovad[oa]|aprovação|deferido|improv[ae]d)\s*(?:por\s+unanimidade|por\s+maioria)?",
    re.IGNORECASE,
)
RE_ZONEAMENTO = re.compile(
    r"(?:rezon[ae]amento|altera[çc][ãa]o\s+de\s+zo(?:n[ae]amento)?|uso\s+e\s+ocupa[çc][ãa]o|plano\s+diretor"
    r"|lei\s+de\s+zoneamento|ZR\d|ZC\d|ZI\d|ZEIS|ZDE)",
    re.IGNORECASE,
)
RE_NEIGHBORHOOD = re.compile(
    r"(?:bairro|jardim|jd\.?|parque|vila|conjunto)\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s]{2,40})",
)


def run_cmdu_collector() -> dict[str, int]:
    """Coleta atas do CMDU do DOM-MAR e upserta em cmdu_atas."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        _ensure_table(db)
        records = _collect_from_api()
        logger.info(f"[{SOURCE}] Total atas CMDU encontradas: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("cmdu_atas").upsert(
                    _to_row(rec), on_conflict="source_id"
                ).execute()
                stats["created"] += 1

                # Indexar no document_embeddings se tiver texto útil
                if rec.get("texto_pauta"):
                    _queue_embedding(db, rec)

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


def _ensure_table(db: Any) -> None:
    """Cria tabela cmdu_atas se não existir (via upsert — Supabase cria automaticamente se migration já aplicada)."""
    pass  # Migration em sql/048_cmdu_atas.sql — aplicar via Supabase dashboard


def _collect_from_api() -> list[dict[str, Any]]:
    years = range(CMDU_START_YEAR, CMDU_END_YEAR + 1)
    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in years:
            url = DOM_MAR_API.format(year=year)
            editions = _fetch_editions(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(editions)} edições")

            for ed in editions:
                text = ed.get("descricao") or ""
                if not text or not RE_CMDU_BLOCK.search(text):
                    continue

                ed_date = _parse_edition_date(ed)
                ed_id = str(ed.get("edicao") or ed.get("id") or "")
                records = _extract_atas(text, fallback_date=ed_date, edition_id=ed_id)

                for r in records:
                    if r["source_id"] not in seen_ids:
                        seen_ids.add(r["source_id"])
                        all_records.append(r)

            if year != CMDU_END_YEAR:
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
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Erro ao buscar edições {year}")
        return []


def _parse_edition_date(ed: dict[str, Any]) -> date | None:
    raw = ed.get("data") or ed.get("date") or ed.get("publicacao") or ""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(raw)[:19], fmt).date()
        except ValueError:
            continue
    return None


def _extract_atas(
    text: str,
    fallback_date: date | None = None,
    edition_id: str = "",
) -> list[dict[str, Any]]:
    if not text:
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in RE_CMDU_BLOCK.finditer(text):
        snippet = text[max(0, m.start() - 100): m.end() + 800]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        numero_ata = _first_match(RE_ATA_NUMBER, snippet)
        pub_date = _extract_date(snippet) or fallback_date
        pauta_match = RE_PAUTA.search(snippet)
        texto_pauta = pauta_match.group(1).strip()[:500] if pauta_match else None
        tem_aprovacao = bool(RE_APROVACAO.search(snippet))
        tem_zoneamento = bool(RE_ZONEAMENTO.search(snippet))
        neighborhood_match = RE_NEIGHBORHOOD.search(snippet)
        neighborhood = neighborhood_match.group(1).strip() if neighborhood_match else None

        # Descarta fragmentos sem sinal útil
        if not any([numero_ata, texto_pauta, tem_zoneamento]):
            continue

        key_parts = [edition_id, numero_ata or "", str(pub_date or "")]
        source_id = hashlib.sha1(":".join(key_parts).encode()).hexdigest()[:20]

        if source_id in seen:
            continue
        seen.add(source_id)

        records.append({
            "source_id": source_id,
            "publication_date": pub_date.isoformat() if pub_date else None,
            "numero_ata": numero_ata,
            "texto_pauta": texto_pauta,
            "tem_aprovacao": tem_aprovacao,
            "tem_zoneamento": tem_zoneamento,
            "neighborhood": neighborhood,
            "snippet": snippet[:1200],
        })

    return records


def _queue_embedding(db: Any, rec: dict[str, Any]) -> None:
    """Registra metadados para embedding posterior — não gera o vector aqui (custo/latência)."""
    try:
        chunk_text = f"CMDU {rec.get('numero_ata', '')} | {rec.get('publication_date', '')} | {rec.get('texto_pauta', '')}"
        content_hash = hashlib.sha1(chunk_text.encode()).hexdigest()
        db.table("document_embeddings").upsert({
            "source_table": "cmdu_atas",
            "source_id": rec["source_id"],
            "chunk_index": 0,
            "chunk_text": chunk_text[:2000],
            "content_hash": content_hash,
            "metadata": {
                "publication_date": rec.get("publication_date"),
                "tem_zoneamento": rec.get("tem_zoneamento"),
                "neighborhood": rec.get("neighborhood"),
            },
        }, on_conflict="source_table,source_id,chunk_index").execute()
    except Exception:
        logger.debug(f"[{SOURCE}] embedding queue falhou (tabela pode não existir ainda)")


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return m.group(1) if m.groups() else m.group(0)


def _extract_date(text: str) -> date | None:
    m = RE_DATE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_id": rec["source_id"],
        "publication_date": rec.get("publication_date"),
        "numero_ata": rec.get("numero_ata"),
        "texto_pauta": rec.get("texto_pauta"),
        "tem_aprovacao": rec.get("tem_aprovacao", False),
        "tem_zoneamento": rec.get("tem_zoneamento", False),
        "neighborhood": rec.get("neighborhood"),
        "raw_snippet": rec.get("snippet", "")[:2000],
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

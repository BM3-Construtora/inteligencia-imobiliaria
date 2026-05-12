"""Coleta lista de dívida ativa IPTU de Marília-SP.

Fonte oficial publica anualmente em https://www.marilia.sp.gov.br/.
Como o endpoint varia ano a ano, é configurável via env IPTU_DEVEDORES_URL.
Sem URL setada → log warning e retorna 0.

signal_type = 'distress'
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "iptu_devedor"
SIGNAL_TYPE = "distress"
CITY = "Marília"
STATE = "SP"

IPTU_DEVEDORES_URL = os.getenv("IPTU_DEVEDORES_URL", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}
TIMEOUT = 60


def run_collector() -> dict[str, int]:
    """Coleta dívida ativa IPTU e upserta em off_market_signals."""
    stats = {"processed": 0, "created": 0, "failed": 0}

    if not IPTU_DEVEDORES_URL:
        logger.warning(
            f"[{SOURCE}] IPTU_DEVEDORES_URL não configurada — pulando coleta"
        )
        return stats

    db = get_client()
    run_id = _start_run(db)

    try:
        content, content_type = _download(IPTU_DEVEDORES_URL)
        if not content:
            logger.warning(f"[{SOURCE}] Download vazio")
            _finish_run(db, run_id, "completed", stats)
            return stats

        records = _parse(content, content_type)
        logger.info(f"[{SOURCE}] Parsed {len(records)} records")

        for rec in records:
            stats["processed"] += 1
            try:
                payload = _to_signal_row(rec)
                db.table("off_market_signals").upsert(
                    payload, on_conflict="source,source_id"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] Failed to upsert record")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _download(url: str) -> tuple[bytes, str]:
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            resp = c.get(url)
            if resp.status_code != 200:
                logger.warning(f"[{SOURCE}] HTTP {resp.status_code}")
                return b"", ""
            return resp.content, resp.headers.get("content-type", "")
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error: {e}")
        return b"", ""


def _parse(content: bytes, content_type: str) -> list[dict[str, Any]]:
    """Parse PDF (se pdfplumber disponível) ou texto/HTML."""
    ct = (content_type or "").lower()
    is_pdf = "pdf" in ct or content[:4] == b"%PDF"

    if is_pdf:
        return _parse_pdf(content)

    # Texto / HTML fallback
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        return []
    # Remove tags HTML simples
    text = re.sub(r"<[^>]+>", "\n", text)
    return _parse_text_lines(text)


def _parse_pdf(content: bytes) -> list[dict[str, Any]]:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning(
            f"[{SOURCE}] pdfplumber não instalado — pulando parse de PDF"
        )
        return []

    lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                lines.extend(txt.splitlines())
    except Exception:
        logger.exception(f"[{SOURCE}] pdfplumber failed")
        return []

    return _parse_text_lines("\n".join(lines))


# Padrões genéricos: linha com CPF/CNPJ ofuscado + nome + valor
RE_DOC = re.compile(r"(\d{3}\.\*{3}\.\*{3}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})")
RE_VALOR = re.compile(r"R?\$?\s*([\d\.]+,\d{2})")


def _parse_text_lines(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 10:
            continue

        m_doc = RE_DOC.search(line)
        if not m_doc:
            continue

        doc = m_doc.group(1)
        # nome = trecho antes do doc
        before = line[:m_doc.start()].strip(" -|\t")
        name = before[-120:] if before else None

        valor = None
        m_val = RE_VALOR.search(line[m_doc.end():])
        if m_val:
            try:
                valor = float(
                    m_val.group(1).replace(".", "").replace(",", ".")
                )
            except ValueError:
                valor = None

        # source_id: hash determinístico p/ idempotência
        source_id = hashlib.sha1(
            f"{doc}|{name or ''}".encode("utf-8")
        ).hexdigest()[:16]

        records.append({
            "source_id": source_id,
            "owner_name": name,
            "owner_doc": _mask_doc(doc),
            "estimated_value": valor,
            "raw_line": line[:500],
        })
    return records


def _mask_doc(doc: str) -> str:
    """Ofusca dígitos do meio. Já vem ofuscado em alguns formatos."""
    digits = re.sub(r"\D", "", doc)
    if len(digits) == 11:  # CPF
        return f"{digits[:3]}.***.***-{digits[-2:]}"
    if len(digits) == 14:  # CNPJ
        return f"{digits[:2]}.***.***/****-{digits[-2:]}"
    return doc


def _to_signal_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source": SOURCE,
        "source_id": rec["source_id"],
        "signal_type": SIGNAL_TYPE,
        "title": "Dívida ativa IPTU — Marília",
        "description": rec.get("raw_line"),
        "city": CITY,
        "state": STATE,
        "estimated_value": rec.get("estimated_value"),
        "owner_name": rec.get("owner_name"),
        "owner_doc": rec.get("owner_doc"),
        "url": IPTU_DEVEDORES_URL,
        "raw_payload": rec,
        "last_seen_at": now,
        "is_active": True,
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

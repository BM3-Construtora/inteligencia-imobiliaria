"""Coleta alvarás de construção publicados no Diário Oficial Municipal de Marília.

Endpoint configurável via env ALVARAS_FEED_URL (RSS/HTML/PDF). Sem URL setada,
faz log warning e retorna 0.

signal_type = 'permit'
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

SOURCE = "alvara_prefeitura"
SIGNAL_TYPE = "permit"
CITY = "Marília"
STATE = "SP"

ALVARAS_FEED_URL = os.getenv("ALVARAS_FEED_URL", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
TIMEOUT = 60

RE_ALVARA = re.compile(
    r"(alvará|alvara)[^\n]{0,200}",
    re.IGNORECASE,
)
RE_AREA = re.compile(r"(\d{2,5}[\.,]?\d*)\s*m²")
RE_PROCESSO = re.compile(r"(?:processo|protocolo)\s*[:nº#]*\s*([\d\./-]{4,})", re.IGNORECASE)


def run_collector() -> dict[str, int]:
    """Coleta alvarás municipais e upserta em off_market_signals."""
    stats = {"processed": 0, "created": 0, "failed": 0}

    if not ALVARAS_FEED_URL:
        logger.warning(
            f"[{SOURCE}] ALVARAS_FEED_URL não configurada — pulando coleta"
        )
        return stats

    db = get_client()
    run_id = _start_run(db)

    try:
        content, ct = _download(ALVARAS_FEED_URL)
        if not content:
            _finish_run(db, run_id, "completed", stats)
            return stats

        records = _parse(content, ct)
        logger.info(f"[{SOURCE}] Parsed {len(records)} permit records")

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
    ct = (content_type or "").lower()
    is_pdf = "pdf" in ct or content[:4] == b"%PDF"

    if is_pdf:
        text = _pdf_to_text(content)
    else:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            return []
        text = re.sub(r"<[^>]+>", "\n", text)

    return _extract_permits(text)


def _pdf_to_text(content: bytes) -> str:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning(f"[{SOURCE}] pdfplumber não instalado — pulando PDF")
        return ""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        logger.exception(f"[{SOURCE}] pdfplumber failed")
        return ""


def _extract_permits(text: str) -> list[dict[str, Any]]:
    """Heurística: procura linhas mencionando 'alvará' e contexto próximo."""
    if not text:
        return []

    records: list[dict[str, Any]] = []
    for m in RE_ALVARA.finditer(text):
        snippet = text[max(0, m.start() - 80): m.end() + 200]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        # processo / protocolo como source_id estável quando existir
        proc = None
        m_proc = RE_PROCESSO.search(snippet)
        if m_proc:
            proc = m_proc.group(1)

        area = None
        m_area = RE_AREA.search(snippet)
        if m_area:
            try:
                area = float(m_area.group(1).replace(",", "."))
            except ValueError:
                area = None

        source_id = (
            proc or hashlib.sha1(snippet.encode("utf-8")).hexdigest()[:16]
        )

        records.append({
            "source_id": source_id,
            "description": snippet[:500],
            "area_m2": area,
        })

    # Deduplicação dentro do batch
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in records:
        if r["source_id"] in seen:
            continue
        seen.add(r["source_id"])
        out.append(r)
    return out


def _to_signal_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source": SOURCE,
        "source_id": rec["source_id"],
        "signal_type": SIGNAL_TYPE,
        "title": "Alvará de construção — Marília",
        "description": rec.get("description"),
        "city": CITY,
        "state": STATE,
        "area_m2": rec.get("area_m2"),
        "url": ALVARAS_FEED_URL,
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

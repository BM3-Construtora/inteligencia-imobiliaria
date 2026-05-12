"""Coletor genérico de leilões/editais via feed HTML ou RSS configurável.

Alternativa pragmática ao Caixa (Radware-bloqueado). Permite apontar para
qualquer portal de leiloeiro regional, DJE-SP ou RSS que liste leilões com
referência a Marília-SP.

Configuração via env:
  LEILOES_FEED_URL = URL da página/feed com listagem
  LEILOES_FEED_TYPE = "html" (default) ou "rss"
  LEILOES_CITY_FILTER = "marilia" (default — filtra blocos contendo essa string)

Heurísticas de extração (best-effort):
  - Cada item: bloco entre <article>/<li>/<div class="lote">
  - Captura: título, link, valor mínimo (R$ X), área (m²)
  - source_id = sha1(url do lote) — único por leiloeiro

Se LEILOES_FEED_URL não setada, retorna 0 sem warning intrusivo.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "leilao_generico"
SIGNAL_TYPE = "auction"
CITY = "Marília"
STATE = "SP"

FEED_URL = os.getenv("LEILOES_FEED_URL", "").strip()
FEED_TYPE = os.getenv("LEILOES_FEED_TYPE", "html").lower()
CITY_FILTER = os.getenv("LEILOES_CITY_FILTER", "maril").lower()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xml,application/rss+xml,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
TIMEOUT = 30


def run_collector() -> dict[str, int]:
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    if not FEED_URL:
        logger.info(f"[{SOURCE}] LEILOES_FEED_URL não setada — pulando")
        _finish_run(db, run_id, "completed", stats)
        return stats

    try:
        items = _fetch_items()
        logger.info(f"[{SOURCE}] Fetched {len(items)} items matching '{CITY_FILTER}'")

        for item in items:
            stats["processed"] += 1
            try:
                payload = _to_signal_row(item)
                db.table("off_market_signals").upsert(
                    payload, on_conflict="source,source_id"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] upsert failed")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _fetch_items() -> list[dict[str, Any]]:
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            resp = c.get(FEED_URL)
            if resp.status_code != 200:
                logger.warning(f"[{SOURCE}] HTTP {resp.status_code}")
                return []
            body = resp.text
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error: {e}")
        return []

    if FEED_TYPE == "rss":
        return _parse_rss(body)
    return _parse_html(body)


def _parse_html(html: str) -> list[dict[str, Any]]:
    """Best-effort: split em <article>/<li class*=lote>/<div class*=imovel>."""
    if CITY_FILTER not in html.lower():
        return []

    # Divide em "blocos" — captura tudo entre tags estruturais comuns
    chunks = re.split(
        r"<(?:article|li class=\"[^\"]*(?:lote|imovel|leilao)[^\"]*\"|"
        r"div class=\"[^\"]*(?:lote|imovel|leilao)[^\"]*\")[^>]*>",
        html,
        flags=re.IGNORECASE,
    )

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        if CITY_FILTER not in chunk.lower():
            continue

        # URL absoluta ou relativa do item
        m_url = re.search(r"href=\"([^\"]+)\"", chunk)
        if not m_url:
            continue
        url = m_url.group(1)
        if url.startswith("/"):
            base = re.match(r"https?://[^/]+", FEED_URL)
            if base:
                url = base.group(0) + url

        source_id = hashlib.sha1(url.encode()).hexdigest()[:24]
        if source_id in seen:
            continue
        seen.add(source_id)

        text = re.sub(r"<[^>]+>", " ", chunk)
        text = re.sub(r"\s+", " ", text).strip()

        title = None
        m_title = re.search(r"<(?:h[1-4]|strong|b)[^>]*>([^<]+)", chunk, re.IGNORECASE)
        if m_title:
            title = m_title.group(1).strip()[:200]
        if not title:
            title = text[:80]

        value = None
        m_val = re.search(r"R\$\s*([\d\.]+,\d{2})", text)
        if m_val:
            try:
                value = float(m_val.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass

        area = None
        m_area = re.search(r"(\d+[\.,]?\d*)\s*m[²2]", text)
        if m_area:
            try:
                area = float(m_area.group(1).replace(",", "."))
            except ValueError:
                pass

        items.append({
            "source_id": source_id,
            "title": title,
            "url": url,
            "raw_text": text[:600],
            "estimated_value": value,
            "area_m2": area,
        })

    return items


def _parse_rss(xml: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.DOTALL | re.IGNORECASE):
        block = m.group(1)
        if CITY_FILTER not in block.lower():
            continue
        title = (re.search(r"<title>(.*?)</title>", block, re.DOTALL | re.IGNORECASE) or [None, ""])
        title_v = title[1] if isinstance(title, list) else (title.group(1) if title else "")
        link = re.search(r"<link>(.*?)</link>", block, re.DOTALL | re.IGNORECASE)
        link_v = link.group(1).strip() if link else ""
        if not link_v:
            continue
        desc = re.search(r"<description>(.*?)</description>", block, re.DOTALL | re.IGNORECASE)
        desc_v = re.sub(r"<[^>]+>", " ", desc.group(1)).strip() if desc else ""

        value = None
        m_val = re.search(r"R\$\s*([\d\.]+,\d{2})", desc_v + " " + (title_v or ""))
        if m_val:
            try:
                value = float(m_val.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass

        source_id = hashlib.sha1(link_v.encode()).hexdigest()[:24]
        items.append({
            "source_id": source_id,
            "title": (title_v or "Leilão")[:200],
            "url": link_v,
            "raw_text": desc_v[:600],
            "estimated_value": value,
            "area_m2": None,
        })
    return items


def _to_signal_row(item: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source": SOURCE,
        "source_id": item["source_id"],
        "signal_type": SIGNAL_TYPE,
        "title": item.get("title"),
        "description": item.get("raw_text"),
        "city": CITY,
        "state": STATE,
        "estimated_value": item.get("estimated_value"),
        "area_m2": item.get("area_m2"),
        "url": item.get("url"),
        "raw_payload": {k: v for k, v in item.items() if k != "raw_text"},
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
        pass

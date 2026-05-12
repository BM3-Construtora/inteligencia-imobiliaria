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
    """Best-effort: divide em blocos por anchors de itens ou containers."""
    if CITY_FILTER not in html.lower():
        return []

    # Estratégia 1: blocos com containers semânticos
    chunks = re.split(
        r"<(?:article|li class=\"[^\"]*(?:lote|imovel|leilao|card|item|property)[^\"]*\"|"
        r"div class=\"[^\"]*(?:lote|imovel|leilao|card|item|property)[^\"]*\")[^>]*>",
        html,
        flags=re.IGNORECASE,
    )
    # Estratégia 2 (fallback): se quase nenhum bloco match, divide por anchors
    # que apontam para /imovel/ /lote/ /leilao/ etc — typical de portais sem semantic markup
    if len(chunks) < 5:
        chunks = re.split(
            r"(?=<a\s[^>]*href=\"(?:https?://[^\"]+)?/"
            r"(?:imovel|lote|leilao|imoveis|leiloes)/[^\"]+\")",
            html,
            flags=re.IGNORECASE,
        )

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        if CITY_FILTER not in chunk.lower():
            continue

        # URL absoluta ou relativa do item — só aceita href HTTP/anchor
        m_url = re.search(r"href=\"((?:https?:|/)[^\"]+)\"", chunk)
        if not m_url:
            continue
        url = m_url.group(1)
        # Ignora tracking, scripts, recursos
        if any(bad in url.lower() for bad in (
            "google-analytics", "googletagmanager", "facebook.com/tr",
            ".js", ".css", ".png", ".jpg", ".gif", ".svg",
            "/cdn-cgi/", "mailto:", "javascript:", "tel:",
        )):
            continue
        # Ignora URLs de navegação do próprio site (não são itens)
        nav_paths = (
            "/login", "/cadastro", "/cadastrar", "/conta", "/perfil",
            "/sobre", "/contato", "/contact", "/about",
            "/termos", "/politica", "/privacidade",
            "/busca", "/buscar", "/search", "/pesquisa", "/filtros",
            "/blog/", "/noticias", "/ajuda", "/faq",
        )
        url_lower = url.lower()
        if any(seg in url_lower for seg in nav_paths):
            continue
        # Exige slug de item (não só /imovel/sp/marilia/ — precisa ter slug específico)
        if not re.search(r"/(?:imovel|lote|leilao|imoveis|leiloes)/[^/]+/[^/]+", url_lower):
            continue
        if url.startswith("/"):
            base = re.match(r"https?://[^/]+", FEED_URL)
            if base:
                url = base.group(0) + url

        source_id = hashlib.sha1(url.encode()).hexdigest()[:24]
        if source_id in seen:
            continue
        seen.add(source_id)

        # Remove blocos <script> e <style> antes de extrair texto
        clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", chunk, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", clean)
        text = re.sub(r"\s+", " ", text).strip()
        # Descarta itens com texto suspeito (inline JS sobreviveu)
        if any(bad in text.lower() for bad in ("datalayer.push", "ga(\\'", "gtag(", "window.")):
            continue
        if len(text) < 20:
            continue

        # Título — preferir slug do URL (mais limpo que badges %, etc do HTML)
        title = _title_from_url_slug(url) or None
        if not title:
            m_title = re.search(r"<(?:h[1-4]|strong|b)[^>]*>([^<]+)", chunk, re.IGNORECASE)
            if m_title:
                title = m_title.group(1).strip()[:200]
        if not title or len(title) < 5 or re.match(r"^\d+%?$", title.strip()):
            title = text[:120]

        # Bairro extraído do slug do URL (heurística)
        neighborhood = _neighborhood_from_slug(url)

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
            "neighborhood": neighborhood,
        })

    return items


def _title_from_url_slug(url: str) -> str | None:
    """Extrai título humano do slug do URL.
    Ex: '/imovel/sp/marilia/residencial-jardim-california-2-quartos-...'
        → 'Residencial Jardim California 2 Quartos'
    """
    m = re.search(r"/(?:imovel|lote|leilao|imoveis|leiloes)/[^/]*/[^/]*/([^/?#]+)", url, re.I)
    if not m:
        return None
    slug = m.group(1)
    # Remove ids numéricos longos e códigos no fim
    slug = re.sub(r"-\d{4,}.*$", "", slug)
    slug = re.sub(r"-(imovel|venda|direta|caixa|cef|economica|federal).*$", "", slug, flags=re.I)
    words = slug.replace("-", " ").split()
    # Limita a 8 palavras pra título compacto
    return " ".join(w.capitalize() for w in words[:8]) if words else None


def _neighborhood_from_slug(url: str) -> str | None:
    """Detecta bairro no slug procurando keywords (jardim/residencial/vila/parque...).
    Ex slug 'residencial-jardim-california-2-quartos...' → 'Jardim California'
    """
    m = re.search(r"/(?:imovel|lote|leilao|imoveis|leiloes)/[^/]*/[^/]*/([^/?#]+)", url, re.I)
    if not m:
        return None
    slug = m.group(1).lower()
    bairro_re = re.compile(
        r"(?:^|-)((?:jardim|residencial|vila|parque|nucleo|n\.?h\.?|conjunto|"
        r"loteamento|setor|bairro)-[a-z]+(?:-[a-z]+){0,2})"
    )
    mm = bairro_re.search(slug)
    if not mm:
        return None
    return " ".join(w.capitalize() for w in mm.group(1).split("-"))


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
        "neighborhood": item.get("neighborhood"),
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

"""Coleta leilões de imóveis Caixa filtrados por Marília-SP.

Fonte: https://venda-imoveis.caixa.gov.br/sistema/

Estratégia leve: baixa a página de listagem do estado SP e filtra cidade
"Marília" em memória. Sem JS rendering pesado. Se a fonte mudar/quebrar,
retorna 0 created e não trava o pipeline.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "leilao_caixa"
SIGNAL_TYPE = "auction"
CITY = "Marília"
STATE = "SP"

# Endpoint público da listagem de SP. O site da Caixa tem um form que
# faz POST pra esta URL. Em caso de bloqueio (Cloudflare/captcha) retornamos 0.
CAIXA_LIST_URL = (
    "https://venda-imoveis.caixa.gov.br/sistema/carregaListaImoveis.asp"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

TIMEOUT = 30


def run_collector() -> dict[str, int]:
    """Coleta leilões Caixa em Marília-SP e upserta em off_market_signals."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()

    run_id = _start_run(db)

    try:
        items = _fetch_marilia_listings()
        logger.info(f"[{SOURCE}] Fetched {len(items)} candidate listings")

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
                logger.exception(f"[{SOURCE}] Failed to upsert item")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _fetch_marilia_listings() -> list[dict[str, Any]]:
    """Busca listagem de SP e filtra Marília. Robusto a quebra de HTML."""
    # Body POST mínimo — formulário expõe estado/cidade. Mantém só estado=SP
    # e deixa cidade vazia (retorna todos os imóveis de SP).
    form = {
        "hdn_estado": STATE,
        "hdn_cidade": "",
        "hdn_bairro": "",
        "hdn_tp_venda": "",
        "hdn_tp_imovel": "",
        "hdn_area_util": "",
        "hdn_vr_venda": "",
        "hdn_quartos": "",
    }
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            resp = c.post(CAIXA_LIST_URL, data=form)
            if resp.status_code != 200:
                logger.warning(
                    f"[{SOURCE}] HTTP {resp.status_code} — fonte indisponível"
                )
                return []
            html = resp.text
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error: {e}")
        return []

    return _parse_listing_html(html)


def _parse_listing_html(html: str) -> list[dict[str, Any]]:
    """Parse best-effort do HTML da Caixa.

    O site renderiza cada imóvel em blocos com link
    `detalhe-imovel.asp?hdnImovel=<ID>`. Capturamos id e contexto próximo
    procurando "Marília".
    """
    if not html or "Marília" not in html and "Marilia" not in html:
        return []

    items: list[dict[str, Any]] = []
    # Heurística: bloco entre identificadores de imóvel.
    # Cada item tem um link com hdnimovel=ID
    pattern = re.compile(
        r"hdnimovel=(\d+)[^<]*</a>(.*?)(?=hdnimovel=\d+|</body>)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(html):
        imovel_id = m.group(1)
        block = m.group(2)
        # Só interessa se aparecer Marília no bloco
        if "marília" not in block.lower() and "marilia" not in block.lower():
            continue

        text = re.sub(r"<[^>]+>", " ", block)
        text = re.sub(r"\s+", " ", text).strip()

        # Tentativa de extrair valor (R$ X,XX)
        value = None
        m_val = re.search(r"R\$\s*([\d\.]+,\d{2})", text)
        if m_val:
            try:
                value = float(
                    m_val.group(1).replace(".", "").replace(",", ".")
                )
            except ValueError:
                value = None

        # Área m²
        area = None
        m_area = re.search(r"(\d+[\.,]?\d*)\s*m²", text)
        if m_area:
            try:
                area = float(m_area.group(1).replace(",", "."))
            except ValueError:
                area = None

        # Endereço aproximado: primeiros 200 chars do bloco textual
        address = text[:200] if text else None

        items.append({
            "id": imovel_id,
            "title": f"Leilão Caixa #{imovel_id}",
            "address": address,
            "estimated_value": value,
            "area_m2": area,
            "url": (
                f"https://venda-imoveis.caixa.gov.br/sistema/"
                f"detalhe-imovel.asp?hdnImovel={imovel_id}"
            ),
            "raw_text": text,
        })

    return items


def _to_signal_row(item: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source": SOURCE,
        "source_id": str(item["id"]),
        "signal_type": SIGNAL_TYPE,
        "title": item.get("title"),
        "description": item.get("raw_text"),
        "address": item.get("address"),
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

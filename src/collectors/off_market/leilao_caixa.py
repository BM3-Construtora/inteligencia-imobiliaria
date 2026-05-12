"""Coleta leilões de imóveis Caixa filtrados por Marília-SP.

Fonte: https://venda-imoveis.caixa.gov.br/sistema/

STATUS 2026-05-11: Site Caixa usa Radware Bot Manager + carregamento
multi-step de resultados via XHR pós-aprovação de fingerprint. O fluxo
abaixo (estado → cidade → next0 → next1) é estruturalmente correto mas
o container #listaimoveis fica vazio em modo headless mesmo com
evasão básica (UA + navigator.webdriver). Próximos passos para fechar:
  - Usar playwright-stealth lib (rebrowser-patches)
  - OU rodar headless=False com xvfb em servidor
  - OU usar o endpoint público de PDF semanal (gov.br/caixa/leilões)
  - OU substituir por scraping de portais de leiloeiros oficiais (megaleiloes, etc)

Como uso interno BM3 prioriza Marília-SP (cidade pequena, poucos leilões
Caixa típicos), recomendação: aguardar iteração e usar enquanto isso
inventário TJ-SP + IPTU devedores que são mais confiáveis.

Se Playwright não instalado ou fonte indisponível, retorna 0 created sem
travar o pipeline. Instale com: `pip install playwright && playwright install chromium`.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "leilao_caixa"
SIGNAL_TYPE = "auction"
CITY = "Marília"
STATE = "SP"

CAIXA_SEARCH_URL = "https://venda-imoveis.caixa.gov.br/sistema/busca-imovel.asp?sltTipoBusca=imoveis"
CAIXA_BASE = "https://venda-imoveis.caixa.gov.br/sistema/"

TIMEOUT_MS = 45_000


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
    """Renderiza busca-imovel.asp com Playwright, filtra Marília-SP, extrai items.

    Fluxo:
    1. Abre busca-imovel.asp
    2. Aguarda <select id=cmb_estado>, seleciona SP
    3. Aguarda popular <select id=cmb_cidade> via JS, seleciona Marília
    4. Submete (btn_next1) — espera lista renderizar
    5. Extrai blocos com `hdnImovel=<id>` + valor + área + endereço
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.warning(
            f"[{SOURCE}] Playwright não instalado. "
            "Instale: `pip install playwright && playwright install chromium`. Pulando."
        )
        return []

    html = ""
    try:
        with sync_playwright() as pw:
            # Anti-detecção: site Caixa usa Radware Bot Manager,
            # bloqueia HeadlessChrome UA + navigator.webdriver true
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 768},
                locale="pt-BR",
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined});"
            )
            page = ctx.new_page()
            page.set_default_timeout(TIMEOUT_MS)
            page.goto(CAIXA_SEARCH_URL, wait_until="domcontentloaded")

            page.wait_for_selector("#cmb_estado", state="visible")
            page.select_option("#cmb_estado", value=STATE)

            # cidade é populada via XHR após mudar estado; aguarda opções carregarem
            page.wait_for_function(
                "() => document.querySelector('#cmb_cidade')"
                " && document.querySelector('#cmb_cidade').options.length > 1",
                timeout=TIMEOUT_MS,
            )
            # Marília pode aparecer com acento ou sem — tenta ambos
            try:
                page.select_option("#cmb_cidade", label="MARILIA")
            except Exception:
                try:
                    page.select_option("#cmb_cidade", label="MARÍLIA")
                except Exception:
                    # Última tentativa: procura option contendo "MARIL"
                    page.evaluate(
                        "() => {"
                        "  const sel = document.querySelector('#cmb_cidade');"
                        "  const opt = Array.from(sel.options).find("
                        "    o => o.text.toUpperCase().includes('MARIL'));"
                        "  if (opt) { sel.value = opt.value;"
                        "    sel.dispatchEvent(new Event('change', {bubbles:true})); }"
                        "}"
                    )

            # Submete em 2 cliques: next0 (estado+cidade) → next1 (filtros opcionais)
            page.click("#btn_next0")
            page.wait_for_selector("#btn_next1", state="visible", timeout=TIMEOUT_MS)
            page.wait_for_timeout(800)
            page.click("#btn_next1")

            # Resultados ficam em #listaimoveis. Aguarda popular.
            page.wait_for_function(
                "() => { const e = document.querySelector('#listaimoveis');"
                " return e && e.innerText.trim().length > 100; }",
                timeout=TIMEOUT_MS,
            )
            page.wait_for_timeout(1500)

            html = page.content()
            browser.close()
    except PWTimeout:
        logger.warning(f"[{SOURCE}] Playwright timeout — fonte lenta/indisponível")
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Playwright run failed")
        return []

    return _parse_listing_html(html)


def _parse_listing_html(html: str) -> list[dict[str, Any]]:
    """Parse do HTML pós-render. Cada item tem link hdnImovel=<id>."""
    if not html:
        return []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Cada bloco de imóvel: <a href="...hdnImovel=ID..."> ... contexto ... </a>
    # Captura ID + texto subsequente até próximo hdnImovel ou fim do bloco listagem
    pattern = re.compile(
        r"hdnImovel=(\d+)(.*?)(?=hdnImovel=\d+|</body>)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(html):
        imovel_id = m.group(1)
        if imovel_id in seen:
            continue
        seen.add(imovel_id)

        block = m.group(2)
        text = re.sub(r"<[^>]+>", " ", block)
        text = re.sub(r"\s+", " ", text).strip()[:600]

        # Só aceita item com menção a Marília (defesa caso filtro falhe)
        if "maril" not in text.lower():
            continue

        value = None
        m_val = re.search(r"R\$\s*([\d\.]+,\d{2})", text)
        if m_val:
            try:
                value = float(m_val.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                value = None

        area = None
        m_area = re.search(r"(\d+[\.,]?\d*)\s*m²", text)
        if m_area:
            try:
                area = float(m_area.group(1).replace(",", "."))
            except ValueError:
                area = None

        items.append({
            "id": imovel_id,
            "title": f"Leilão Caixa #{imovel_id}",
            "address": text[:200] if text else None,
            "estimated_value": value,
            "area_m2": area,
            "url": f"{CAIXA_BASE}detalhe-imovel.asp?hdnImovel={imovel_id}",
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

"""Coletor Leroy Merlin.

Plataforma própria (não VTEX). API JSON pública e estável:
    GET /search?term={query}&page={n}&pageSize={k}

Resposta contém `products[]` com:
  _id, name, brand (em characteristics.Marca), price.to_price (base nacional),
  price.region_price (preço Marília quando IP detecta), productSchema.mpn (EAN),
  weight, url.

Auto-geo via IP costuma colocar a sessão em Marília — `region_price` reflete
preço com frete embutido. Coletor usa region_price quando presente, senão
cai pra to_price.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import cloudscraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.leroymerlin.com.br"
SUPPLIER_SLUG = "leroy_merlin"

DEFAULT_TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": f"{BASE_URL}/",
    # Leroy detecta geo por IP — sem cookie. GitHub Actions runner está em
    # outros estados; preço regional Marília só vem se runner estiver no Brasil.
    # Para forçar geo, passar cookie 'userLocation' no futuro.
}

HTML_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": HEADERS["Accept-Language"],
}


@dataclass
class LeroyItem:
    supplier_sku: str
    supplier_name: str
    brand: str | None
    ean: str | None
    weight_kg: float | None
    price: float | None        # melhor preço efetivo (region_price > to_price)
    list_price: float | None
    region_price: float | None
    base_price: float | None
    is_available: bool
    url: str | None
    raw: dict[str, Any]


def search_products(
    query: str,
    *,
    page_size: int = 50,
    max_results: int = 200,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[LeroyItem]:
    """Busca produtos. Pagina até max_results."""
    results: list[LeroyItem] = []

    # cloudscraper já injeta UA + bot challenge tokens. NÃO sobrescrever
    # User-Agent — só passar Accept pra o endpoint responder JSON.
    client = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "desktop": True}
    )
    # Warm-up na home pra capturar cookies do Akamai bot manager.
    try:
        client.get(BASE_URL, timeout=timeout)
    except Exception as e:
        logger.debug(f"[leroy] warm-up falhou (segue): {e}")

    json_headers = {"Accept": "application/json"}
    page = 1
    while len(results) < max_results:
        params = {"term": query, "page": page, "pageSize": page_size}
        try:
            resp = client.get(
                f"{BASE_URL}/search", params=params, headers=json_headers, timeout=timeout
            )
        except Exception as e:
            logger.warning(f"[leroy] HTTP error em '{query}' page={page}: {e}")
            break

        if resp.status_code != 200:
            logger.warning(f"[leroy] HTTP {resp.status_code} em '{query}' page={page}")
            break

        try:
            data = resp.json()
        except ValueError:
            logger.warning(f"[leroy] JSON inválido em '{query}' page={page}")
            break

        products = data.get("products") or []
        if not products:
            break

        for prod in products:
            item = _parse_product(prod)
            if item is not None:
                results.append(item)
            if len(results) >= max_results:
                break

        if len(products) < page_size:
            break
        page += 1

    return results


def _parse_product(prod: dict[str, Any]) -> LeroyItem | None:
    sku = prod.get("_id")
    if sku is None:
        return None

    price_obj = prod.get("price") or {}
    chars = prod.get("characteristics") or {}
    schema = prod.get("productSchema") or {}

    base_price = _to_float(price_obj.get("to_price"))
    region_price = _to_float(price_obj.get("region_price"))
    list_price = _to_float(price_obj.get("from_price"))
    effective = region_price if region_price is not None else base_price

    ean = schema.get("mpn")
    if ean is not None:
        ean = str(ean).strip() or None

    url = prod.get("url")
    if url and not url.startswith("http"):
        url = f"{BASE_URL}{url}"

    return LeroyItem(
        supplier_sku=str(sku),
        supplier_name=prod.get("name") or "",
        brand=chars.get("Marca") or prod.get("brand"),
        ean=ean,
        weight_kg=_to_float(prod.get("weight")),
        price=effective,
        list_price=list_price,
        region_price=region_price,
        base_price=base_price,
        is_available=bool(prod.get("isAvailableOnEcommerce") and not prod.get("isSoldOut")),
        url=url,
        raw=prod,
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

"""Coletor Cassol Centerlar (Magento 2).

Loja física em Bauru-SP, entrega em Marília. Plataforma Magento 2.
URL de busca: https://www.cassol.com.br/catalogsearch/result/?q={query}

HTML scraping via cloudscraper + BeautifulSoup. A página retorna produtos
em `li.product-item`, preço em `span[data-price-amount]` (atributo) ou
`span.price`. EAN em JSON-LD (`@type: Product`, campo `gtin13/sku`).

Throttle: 5-10s entre queries (Magento tem rate-limit por IP mais brando
que CDNs especializadas, mas ainda bloqueia runs agressivos).
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urljoin

import cloudscraper
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cassol.com.br"
SUPPLIER_SLUG = "cassol_centerlar"


@dataclass
class CassolItem:
    supplier_sku: str
    supplier_name: str
    brand: str | None
    ean: str | None
    price: float | None
    list_price: float | None
    is_available: bool
    url: str | None
    weight_kg: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def search_products(query: str, *, max_results: int = 50) -> list[CassolItem]:
    """Busca produtos no Cassol. Retorna lista de CassolItem."""
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "desktop": True}
    )

    # Warm-up (session cookie + Akamai challenge)
    try:
        scraper.get(BASE_URL, timeout=15)
        time.sleep(random.uniform(1.5, 3.0))
    except Exception:
        logger.debug("[cassol] warm-up falhou, continuando mesmo assim")

    items: list[CassolItem] = []
    page = 1

    while len(items) < max_results:
        url = f"{BASE_URL}/catalogsearch/result/?q={quote_plus(query)}&p={page}"
        try:
            resp = scraper.get(url, timeout=20, headers={"Accept": "text/html"})
        except Exception:
            logger.exception(f"[cassol] GET falhou page={page} query={query!r}")
            break

        if resp.status_code == 404:
            break
        if resp.status_code != 200:
            logger.warning(f"[cassol] HTTP {resp.status_code} page={page}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        product_items = soup.select("li.product-item")

        if not product_items:
            break

        for li in product_items:
            if len(items) >= max_results:
                break
            item = _parse_product_item(li)
            if item:
                items.append(item)

        # Verifica se há próxima página
        next_page = soup.select_one("a.action.next")
        if not next_page:
            break

        page += 1
        time.sleep(random.uniform(5.0, 10.0))

    logger.info(f"[cassol] query={query!r} → {len(items)} items")
    return items


def _parse_product_item(li) -> CassolItem | None:
    """Extrai campos de um <li class="product-item">."""
    try:
        # Nome
        name_el = li.select_one(".product-item-name a, .product-item-link")
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        url = name_el.get("href")

        # SKU interno (data-product-id ou sku no script JSON-LD quando inline)
        sku = None
        sku_el = li.select_one("[data-product-id]")
        if sku_el:
            sku = sku_el.get("data-product-id")
        if not sku:
            # fallback: extrair do link /product-slug-NNNN.html
            if url:
                m = re.search(r"-(\d{4,})\.html$", url)
                if m:
                    sku = m.group(1)
        if not sku:
            return None

        # Preço
        price = None
        list_price = None
        price_el = li.select_one("span[data-price-amount]")
        if price_el:
            try:
                price = float(price_el["data-price-amount"])
            except (ValueError, KeyError):
                pass

        if price is None:
            price_text = li.select_one(".price")
            if price_text:
                price = _parse_price_text(price_text.get_text(strip=True))

        old_price_el = li.select_one(".old-price .price")
        if old_price_el:
            list_price = _parse_price_text(old_price_el.get_text(strip=True))

        # Disponibilidade
        unavail = li.select_one(".unavailable, .out-of-stock, [data-available='false']")
        is_available = unavail is None

        # EAN — Magento raramente coloca EAN no listing, mas pode estar no JSON-LD
        ean = _extract_ean_from_jsonld(li)

        # Marca
        brand_el = li.select_one(".product-item-brand, [itemprop='brand']")
        brand = brand_el.get_text(strip=True) if brand_el else None

        return CassolItem(
            supplier_sku=str(sku),
            supplier_name=name,
            brand=brand or None,
            ean=ean,
            price=price,
            list_price=list_price,
            is_available=is_available,
            url=url if url and url.startswith("http") else (urljoin(BASE_URL, url) if url else None),
            raw={"cassol_sku": sku, "cassol_url": url},
        )
    except Exception:
        logger.debug("[cassol] _parse_product_item falhou", exc_info=True)
        return None


def _parse_price_text(text: str) -> float | None:
    """Converte 'R$ 1.234,56' → 1234.56."""
    text = re.sub(r"[^\d,\.]", "", text)
    if "," in text and "." in text:
        # Ex: 1.234,56
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _extract_ean_from_jsonld(el) -> str | None:
    """Procura script JSON-LD com @type=Product dentro do elemento."""
    for script in el.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "Product":
                for field_name in ("gtin13", "gtin8", "gtin", "sku"):
                    val = data.get(field_name)
                    if val and re.match(r"^\d{8,14}$", str(val)):
                        return str(val)
        except (json.JSONDecodeError, TypeError):
            continue
    return None

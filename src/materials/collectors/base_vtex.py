"""Coletor genérico para lojas VTEX.

Várias redes de material de construção rodam em VTEX (Obramax, Telhanorte,
C&C, etc). A API pública de catálogo é idêntica entre elas — muda só o domínio.

Endpoint base:
    GET {base_url}/api/catalog_system/pub/products/search/{query}?_from=0&_to=49

Simulação de entrega CEP:
    POST {base_url}/api/checkout/pub/orderForms/simulation?sc={sales_channel}
    body: {"items":[{"id": sku, "quantity": 1, "seller": "1"}],
           "postalCode": "17500000", "country": "BRA"}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


@dataclass
class VtexItem:
    """Listing normalizado vindo de uma loja VTEX."""
    supplier_sku: str
    supplier_name: str
    brand: str | None
    ean: str | None
    categories: list[str]
    price: float | None
    list_price: float | None
    is_available: bool
    seller_id: str | None
    url: str | None
    raw: dict[str, Any]


def search_products(
    base_url: str,
    query: str,
    *,
    page_size: int = 50,
    max_results: int = 200,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[VtexItem]:
    """Busca produtos via API VTEX. Pagina até max_results."""
    results: list[VtexItem] = []
    base = base_url.rstrip("/")
    encoded_query = httpx.URL(f"{base}/api/catalog_system/pub/products/search/{query}").path

    with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
        offset = 0
        while offset < max_results:
            end = min(offset + page_size, max_results) - 1
            url = f"{base}{encoded_query}?_from={offset}&_to={end}"
            try:
                resp = client.get(url)
            except httpx.HTTPError as e:
                logger.warning(f"[vtex:{base}] HTTP error em '{query}' off={offset}: {e}")
                break

            # VTEX retorna 206 (Partial Content) em buscas paginadas — resposta válida
            if resp.status_code not in (200, 206):
                logger.warning(
                    f"[vtex:{base}] HTTP {resp.status_code} em '{query}' off={offset}"
                )
                break

            try:
                page = resp.json()
            except ValueError:
                logger.warning(f"[vtex:{base}] JSON inválido em '{query}' off={offset}")
                break

            if not page:
                break

            for product in page:
                item = _parse_product(product, base)
                if item is not None:
                    results.append(item)

            if len(page) < page_size:
                break
            offset += page_size

    return results


def simulate_delivery(
    base_url: str,
    sku: str,
    *,
    seller: str = "1",
    sales_channel: int = 1,
    quantity: int = 1,
    postal_code: str = "17500000",
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Simula entrega para um CEP. Retorna dict com slas, can_deliver, msg.

    can_deliver = True quando há pelo menos uma SLA disponível.
    """
    base = base_url.rstrip("/")
    url = f"{base}/api/checkout/pub/orderForms/simulation?sc={sales_channel}"
    body = {
        "items": [{"id": sku, "quantity": quantity, "seller": seller}],
        "postalCode": postal_code,
        "country": "BRA",
    }

    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout) as client:
            resp = client.post(url, json=body)
    except httpx.HTTPError as e:
        return {"can_deliver": False, "error": str(e), "slas": []}

    if resp.status_code != 200 or not resp.content:
        return {"can_deliver": False, "error": f"HTTP {resp.status_code}", "slas": []}

    try:
        data = resp.json()
    except ValueError:
        return {"can_deliver": False, "error": "invalid json", "slas": []}

    logistics = data.get("logisticsInfo") or []
    slas = logistics[0].get("slas") if logistics else []
    slas = slas or []
    messages = data.get("messages") or []

    return {
        "can_deliver": len(slas) > 0,
        "slas": [
            {
                "name": s.get("name"),
                "price": (s.get("price") or 0) / 100,
                "shipping_estimate": s.get("shippingEstimate"),
            }
            for s in slas
        ],
        "msg": messages[0].get("code") if messages else None,
    }


def _parse_product(product: dict[str, Any], base_url: str) -> VtexItem | None:
    """Extrai campos relevantes do payload VTEX."""
    items = product.get("items") or []
    if not items:
        return None
    first = items[0]
    sellers = first.get("sellers") or []
    seller = sellers[0] if sellers else {}
    offer = seller.get("commertialOffer") or {}

    link = product.get("link")
    if not link:
        link_text = product.get("linkText")
        if link_text:
            link = f"{base_url.rstrip('/')}/{link_text}/p"

    return VtexItem(
        supplier_sku=str(first.get("itemId") or ""),
        supplier_name=product.get("productName") or "",
        brand=product.get("brand"),
        ean=first.get("ean") or None,
        categories=product.get("categories") or [],
        price=_to_float(offer.get("Price")),
        list_price=_to_float(offer.get("ListPrice")),
        is_available=bool(offer.get("IsAvailable")),
        seller_id=str(seller.get("sellerId")) if seller.get("sellerId") else None,
        url=link,
        raw=product,
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

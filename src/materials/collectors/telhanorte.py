"""Coletor Telhanorte — instância de base_vtex."""

from __future__ import annotations

from src.materials.collectors.base_vtex import (
    VtexItem,
    search_products as vtex_search,
    simulate_delivery as vtex_simulate,
)

BASE_URL = "https://www.telhanorte.com.br"
SUPPLIER_SLUG = "telhanorte"


def search_products(query: str, **kwargs) -> list[VtexItem]:
    return vtex_search(BASE_URL, query, **kwargs)


def simulate_delivery(sku: str, **kwargs) -> dict:
    return vtex_simulate(BASE_URL, sku, **kwargs)

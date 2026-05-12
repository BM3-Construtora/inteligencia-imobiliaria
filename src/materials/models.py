"""DTO comum para listings vindos de qualquer coletor de materiais."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.materials.collectors.base_vtex import VtexItem
from src.materials.collectors.leroy import LeroyItem


@dataclass
class CommonListing:
    """Listing normalizado independente de coletor."""
    supplier_slug: str
    supplier_sku: str
    supplier_name: str
    brand: str | None
    ean: str | None
    price: float | None
    list_price: float | None
    region_price: float | None
    is_available: bool
    url: str | None
    weight_kg: float | None = None
    categories: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def from_leroy(item: LeroyItem) -> CommonListing:
    return CommonListing(
        supplier_slug="leroy_merlin",
        supplier_sku=item.supplier_sku,
        supplier_name=item.supplier_name,
        brand=item.brand,
        ean=item.ean,
        price=item.price,
        list_price=item.list_price,
        region_price=item.region_price,
        is_available=item.is_available,
        url=item.url,
        weight_kg=item.weight_kg,
        raw=item.raw,
    )


def from_vtex(item: VtexItem, supplier_slug: str) -> CommonListing:
    return CommonListing(
        supplier_slug=supplier_slug,
        supplier_sku=item.supplier_sku,
        supplier_name=item.supplier_name,
        brand=item.brand,
        ean=item.ean,
        price=item.price,
        list_price=item.list_price,
        region_price=None,
        is_available=item.is_available,
        url=item.url,
        categories=item.categories,
        raw=item.raw,
    )

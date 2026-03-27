"""Collector for ZAP Imóveis (HTML scraper with JSON-LD extraction).

ZAP and VivaReal share the same OLX Group backend, so the JSON-LD
ItemList structure is identical. This collector reuses the same parsing logic.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from src.config import MAX_PAGES_PER_SPIDER
from src.collectors.base import BaseCollector
from src.collectors.http import fetch_page

logger = logging.getLogger(__name__)

BASE_URL = "https://www.zapimoveis.com.br/venda/imoveis/sp+marilia/"


class ZapImoveisCollector(BaseCollector):
    """Collects listings from ZAP Imóveis using JSON-LD ItemList data."""

    source = "zapimoveis"

    async def fetch_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        for page in range(1, MAX_PAGES_PER_SPIDER + 1):
            url = BASE_URL if page == 1 else f"{BASE_URL}?pagina={page}"
            logger.info(f"[zapimoveis] Fetching page {page}")

            try:
                html = fetch_page(url, delay=3.0)  # Slightly longer delay for ZAP
            except Exception as e:
                logger.error(f"[zapimoveis] Failed to fetch page {page}: {e}")
                break

            items = self._parse_page(html)
            if not items:
                logger.info(f"[zapimoveis] No items on page {page}, stopping")
                break

            all_items.extend(items)
            logger.info(
                f"[zapimoveis] Page {page}: {len(items)} items "
                f"(total: {len(all_items)})"
            )

        logger.info(f"[zapimoveis] Total fetched: {len(all_items)} items")
        return all_items

    def _parse_page(self, html: str) -> list[dict[str, Any]]:
        """Extract listings from JSON-LD ItemList."""
        soup = BeautifulSoup(html, "lxml")
        items = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            if data.get("@type") != "ItemList":
                continue

            for entry in data.get("itemListElement", []):
                item = entry.get("item", {})
                if not item:
                    continue

                listing = self._parse_item(item)
                if listing:
                    items.append(listing)

        return items

    def _parse_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a single JSON-LD item into a raw listing dict."""
        url = item.get("url", "")
        item_id = item.get("@id", "")

        if not item_id:
            id_match = re.search(r"id-(\d+)", url)
            if id_match:
                item_id = id_match.group(1)

        if not item_id:
            return None

        url_data = self._parse_url(url)

        name = item.get("name", "")
        area_match = re.search(r"(\d+)\s*m²", name)
        rooms_match = re.search(r"(\d+)\s*quarto", name, re.IGNORECASE)
        bath_match = re.search(r"(\d+)\s*banheir", name, re.IGNORECASE)
        parking_match = re.search(r"(\d+)\s*vaga", name, re.IGNORECASE)

        price = url_data.get("price")

        images = item.get("image", [])
        if isinstance(images, str):
            images = [images]

        schema_type = item.get("@type", "").lower()
        prop_type = _map_schema_type(schema_type) or url_data.get("type", "other")

        area = int(area_match.group(1)) if area_match else url_data.get("area")
        if area is not None and area <= 15:
            desc = item.get("description", "")
            desc_area = re.search(r"(\d{2,})\s*m[²2]", desc)
            if desc_area:
                area = int(desc_area.group(1))
            else:
                area = None

        return {
            "id": item_id,
            "url": url,
            "name": name,
            "description": item.get("description", ""),
            "type": prop_type,
            "price": price,
            "area": area,
            "bedrooms": int(rooms_match.group(1)) if rooms_match else None,
            "bathrooms": int(bath_match.group(1)) if bath_match else None,
            "parking": int(parking_match.group(1)) if parking_match else None,
            "neighborhood": url_data.get("neighborhood"),
            "city": "Marília",
            "state": "SP",
            "images": images,
        }

    def _parse_url(self, url: str) -> dict[str, Any]:
        """Extract structured data from ZAP listing URL."""
        data: dict[str, Any] = {}

        price_match = re.search(r"RS(\d+)", url)
        if price_match:
            data["price"] = int(price_match.group(1))

        area_match = re.search(r"-(\d+)m2-", url)
        if area_match:
            data["area"] = int(area_match.group(1))

        path = url.split("/imovel/")[-1] if "/imovel/" in url else ""
        if path.startswith("casa"):
            data["type"] = "house"
        elif path.startswith("apartamento"):
            data["type"] = "apartment"
        elif path.startswith("terreno"):
            data["type"] = "land"
        elif path.startswith("comercial") or path.startswith("sala"):
            data["type"] = "commercial"

        neigh_match = re.search(
            r"quartos?-([\w-]+)-marilia", path, re.IGNORECASE
        )
        if neigh_match:
            raw = neigh_match.group(1)
            data["neighborhood"] = raw.replace("-", " ").title()

        return data

    def extract_source_id(self, item: dict[str, Any]) -> str:
        return str(item["id"])


def _map_schema_type(schema_type: str) -> str | None:
    """Map schema.org @type to our property_type enum."""
    mapping = {
        "house": "house",
        "singlefamilyresidence": "house",
        "apartment": "apartment",
        "place": "land",
        "residence": "other",
    }
    return mapping.get(schema_type)

"""Collector for VivaReal (HTML scraper with JSON-LD extraction)."""

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

BASE_URL = "https://www.vivareal.com.br/venda/sp/marilia/"


class VivaRealCollector(BaseCollector):
    """Collects listings from VivaReal using JSON-LD ItemList data."""

    source = "vivareal"

    async def fetch_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        for page in range(1, MAX_PAGES_PER_SPIDER + 1):
            url = BASE_URL if page == 1 else f"{BASE_URL}?pagina={page}"
            logger.info(f"[vivareal] Fetching page {page}")

            try:
                html = fetch_page(url, delay=2.0)
            except Exception as e:
                logger.error(f"[vivareal] Failed to fetch page {page}: {e}")
                break

            items = self._parse_page(html)
            if not items:
                logger.info(f"[vivareal] No items on page {page}, stopping")
                break

            all_items.extend(items)
            logger.info(
                f"[vivareal] Page {page}: {len(items)} items "
                f"(total: {len(all_items)})"
            )

        logger.info(f"[vivareal] Total fetched: {len(all_items)} items")
        return all_items

    def _parse_page(self, html: str) -> list[dict[str, Any]]:
        """Extract listings from JSON-LD ItemList + URL parsing."""
        soup = BeautifulSoup(html, "lxml")
        items = []

        # Extract from JSON-LD ItemList
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
            # Try extracting from URL
            id_match = re.search(r"id-(\d+)", url)
            if id_match:
                item_id = id_match.group(1)

        if not item_id:
            return None

        # Parse structured data from URL
        url_data = self._parse_url(url)

        # Parse area and rooms from name
        name = item.get("name", "")
        area_match = re.search(r"(\d+)\s*m²", name)
        rooms_match = re.search(r"(\d+)\s*quarto", name, re.IGNORECASE)
        bath_match = re.search(r"(\d+)\s*banheir", name, re.IGNORECASE)
        parking_match = re.search(r"(\d+)\s*vaga", name, re.IGNORECASE)

        # Parse price from URL
        price = url_data.get("price")

        # Images
        images = item.get("image", [])
        if isinstance(images, str):
            images = [images]

        # Property type from @type or URL
        schema_type = item.get("@type", "").lower()
        prop_type = _map_schema_type(schema_type) or url_data.get("type", "other")

        # Area: prefer name (JSON-LD), fallback to URL
        # Discard implausible areas (<=15m² is likely a parsing artifact)
        area = int(area_match.group(1)) if area_match else url_data.get("area")
        if area is not None and area <= 15:
            # Try description for real area
            desc = item.get("description", "")
            desc_area = re.search(r"(\d{2,})\s*m[²2]", desc)
            if desc_area:
                area = int(desc_area.group(1))
            else:
                area = None  # Discard unreliable data

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
        """Extract structured data from VivaReal listing URL.

        Example URL:
        /imovel/casa-2-quartos-jardim-domingos-de-leo-marilia-100m2-venda-RS250000-id-2873227806/
        """
        data: dict[str, Any] = {}

        # Price: RS followed by digits
        price_match = re.search(r"RS(\d+)", url)
        if price_match:
            data["price"] = int(price_match.group(1))

        # Area: digits followed by m2
        area_match = re.search(r"-(\d+)m2-", url)
        if area_match:
            data["area"] = int(area_match.group(1))

        # Type from URL path
        path = url.split("/imovel/")[-1] if "/imovel/" in url else ""
        if path.startswith("casa"):
            data["type"] = "house"
        elif path.startswith("apartamento"):
            data["type"] = "apartment"
        elif path.startswith("terreno"):
            data["type"] = "land"
        elif path.startswith("comercial") or path.startswith("sala"):
            data["type"] = "commercial"

        # Neighborhood: between type-quartos and city
        # e.g., casa-2-quartos-jardim-domingos-de-leo-marilia
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

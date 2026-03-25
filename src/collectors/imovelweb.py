"""Collector for Imovelweb (HTML scraper)."""

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

BASE_URL = "https://www.imovelweb.com.br/imoveis-venda-marilia-sp"


class ImovelwebCollector(BaseCollector):
    """Collects listings from Imovelweb by parsing HTML cards + JSON-LD."""

    source = "imovelweb"

    async def fetch_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        for page in range(1, MAX_PAGES_PER_SPIDER + 1):
            if page == 1:
                url = f"{BASE_URL}.html"
            else:
                url = f"{BASE_URL}-pagina-{page}.html"

            logger.info(f"[imovelweb] Fetching page {page}")

            try:
                html = fetch_page(url, delay=3.0)
            except Exception as e:
                logger.error(f"[imovelweb] Failed to fetch page {page}: {e}")
                break

            items = self._parse_page(html)
            if not items:
                logger.info(f"[imovelweb] No items on page {page}, stopping")
                break

            all_items.extend(items)
            logger.info(
                f"[imovelweb] Page {page}: {len(items)} items "
                f"(total: {len(all_items)})"
            )

        logger.info(f"[imovelweb] Total fetched: {len(all_items)} items")
        return all_items

    def _parse_page(self, html: str) -> list[dict[str, Any]]:
        """Extract listings from cards with data-id + JSON-LD enrichment."""
        soup = BeautifulSoup(html, "lxml")

        # Build a map of JSON-LD data by position for enrichment
        jsonld_items = self._extract_jsonld(soup)

        # Parse cards
        cards = soup.select("[data-qa='posting PROPERTY']")
        items = []

        for i, card in enumerate(cards):
            try:
                item = self._parse_card(card, jsonld_items.get(i))
                if item:
                    items.append(item)
            except Exception:
                logger.debug("[imovelweb] Failed to parse card", exc_info=True)

        return items

    def _extract_jsonld(self, soup: BeautifulSoup) -> dict[int, dict[str, Any]]:
        """Extract JSON-LD items indexed by position."""
        items = {}
        idx = 0
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            schema_type = data.get("@type", "")
            # Skip non-listing types
            if schema_type in ("Organization", "BreadcrumbList", "RealEstateListing"):
                continue

            # These are individual listing JSON-LD (House, Apartment, Place, Residence)
            items[idx] = data
            idx += 1

        return items

    def _parse_card(
        self, card: Any, jsonld: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Parse a single listing card."""
        data_id = card.get("data-id")
        if not data_id:
            return None

        # URL from data-to-posting attribute
        href = card.get("data-to-posting", "")
        url = f"https://www.imovelweb.com.br{href}" if href else None

        # Image
        img = card.select_one("img[src*='imovelwebcdn']")
        image_url = None
        if img:
            image_url = img.get("src", "")
            # Get higher res version
            image_url = image_url.replace("360x266", "720x532")

        # Alt text has structured info: "Casa · 60m² · 2 Quartos · 2 Vagas · ..."
        alt = img.get("alt", "") if img else ""

        # Parse from alt text — discard implausible areas (<=15m²)
        area_match = re.search(r"(\d+)\s*m²", alt)
        if area_match and int(area_match.group(1)) <= 15:
            area_match = None  # Likely parsing artifact
        rooms_match = re.search(r"(\d+)\s*Quarto", alt)
        parking_match = re.search(r"(\d+)\s*Vaga", alt)

        # Price from card text
        price_el = card.select_one("[data-qa='POSTING_CARD_PRICE']")
        price = None
        if price_el:
            price_match = re.search(r"([\d.,]+)", price_el.text.replace(".", "").replace(",", "."))
            if price_match:
                try:
                    price = float(price_match.group(1))
                except ValueError:
                    pass

        # Location from card
        location_el = card.select_one("[data-qa='POSTING_CARD_LOCATION']")
        address_text = location_el.text.strip() if location_el else ""

        # Parse neighborhood from address
        neighborhood = None
        street = None
        if address_text:
            parts = [p.strip() for p in address_text.split(",")]
            if len(parts) >= 2:
                street = parts[0]
                neighborhood = parts[1]
            elif parts:
                neighborhood = parts[0]

        # Enrich from JSON-LD if available
        prop_type = "other"
        name = alt

        if jsonld:
            schema_type = jsonld.get("@type", "").lower()
            prop_type = _map_schema_type(schema_type)
            name = jsonld.get("name", name)

            # Address from JSON-LD
            jaddr = jsonld.get("address", {})
            if isinstance(jaddr, dict):
                addr_name = jaddr.get("name", "")
                if addr_name and not neighborhood:
                    # Format: "Casas Venda Rua X, Bairro, Cidade"
                    parts = addr_name.split(",")
                    if len(parts) >= 2:
                        neighborhood = parts[-2].strip()

        # Infer type from name/alt if not from JSON-LD
        if prop_type == "other":
            name_lower = name.lower()
            if "casa" in name_lower:
                prop_type = "house"
            elif "apartamento" in name_lower:
                prop_type = "apartment"
            elif "terreno" in name_lower:
                prop_type = "land"
            elif "comercial" in name_lower:
                prop_type = "commercial"
            elif "rural" in name_lower:
                prop_type = "rural"

        return {
            "id": data_id,
            "url": url,
            "name": name,
            "type": prop_type,
            "price": price,
            "area": int(area_match.group(1)) if area_match else None,
            "bedrooms": int(rooms_match.group(1)) if rooms_match else None,
            "bathrooms": None,  # Not reliably in alt text
            "parking": int(parking_match.group(1)) if parking_match else None,
            "street": street,
            "neighborhood": neighborhood,
            "city": "Marília",
            "state": "SP",
            "image_url": image_url,
        }

    def extract_source_id(self, item: dict[str, Any]) -> str:
        return str(item["id"])


def _map_schema_type(schema_type: str) -> str:
    mapping = {
        "house": "house",
        "apartment": "apartment",
        "place": "land",
        "residence": "other",
    }
    return mapping.get(schema_type, "other")

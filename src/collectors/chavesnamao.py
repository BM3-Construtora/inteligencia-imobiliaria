"""Collector for Chaves na Mão (HTML scraper)."""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from src.config import MAX_PAGES_PER_SPIDER
from src.collectors.base import BaseCollector
from src.collectors.http import fetch_page

logger = logging.getLogger(__name__)

BASE_URL = "https://www.chavesnamao.com.br/imoveis-a-venda/sp-marilia/"


class ChavesNaMaoCollector(BaseCollector):
    """Collects listings from Chaves na Mão by parsing HTML cards."""

    source = "chavesnamao"

    async def fetch_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        for page in range(1, MAX_PAGES_PER_SPIDER + 1):
            url = BASE_URL if page == 1 else f"{BASE_URL}?pg={page}"
            logger.info(f"[chavesnamao] Fetching page {page}")

            try:
                html = fetch_page(url, delay=1.5)
            except Exception as e:
                logger.error(f"[chavesnamao] Failed to fetch page {page}: {e}")
                break

            items = self._parse_page(html)
            if not items:
                logger.info(f"[chavesnamao] No items on page {page}, stopping")
                break

            all_items.extend(items)
            logger.info(
                f"[chavesnamao] Page {page}: {len(items)} items "
                f"(total: {len(all_items)})"
            )

        logger.info(f"[chavesnamao] Total fetched: {len(all_items)} items")
        return all_items

    def _parse_page(self, html: str) -> list[dict[str, Any]]:
        """Extract listings from HTML cards."""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(".card_card__ENqoy")
        items = []

        for card in cards:
            try:
                item = self._parse_card(card)
                if item:
                    items.append(item)
            except Exception:
                logger.debug("[chavesnamao] Failed to parse card", exc_info=True)

        return items

    def _parse_card(self, card: Any) -> dict[str, Any] | None:
        """Parse a single listing card."""
        # ID from card element
        card_id = card.get("id", "")
        if card_id.startswith("rc-"):
            card_id = card_id[3:]
        if not card_id:
            return None

        # Link and title
        link = card.select_one("a[href*='/imovel/']")
        if not link:
            return None

        href = link.get("href", "")
        url = f"https://www.chavesnamao.com.br{href}" if href.startswith("/") else href

        title_el = card.select_one("h2")
        title = title_el.text.strip() if title_el else ""

        # Address
        address_lines = [p.text.strip() for p in card.select("address p")]
        street = address_lines[0] if address_lines else None
        location = address_lines[1] if len(address_lines) > 1 else None

        # Parse neighborhood and city from location like "Bairro, Cidade/SP"
        neighborhood = None
        if location:
            parts = location.split(",")
            if parts:
                neighborhood = parts[0].strip()

        # Features from aria-label attributes
        features = {}
        for p in card.select("p[aria-label]"):
            label = p.get("aria-label", "")
            if not label or label in ("strong", "list"):
                continue
            # Format: "123 Área útil", "3 Quartos", "2 Banheiros", "1 Garagens"
            match = re.match(r"([\d.,]+)\s+(.+)", label)
            if match:
                value = match.group(1).replace(".", "").replace(",", ".")
                key = match.group(2).lower().strip()
                features[key] = value

        # Price from card text
        all_text = card.get_text(" ", strip=True)
        price = None
        price_match = re.search(r"R\$\s*([\d.,]+)", all_text)
        if price_match:
            price_str = price_match.group(1).replace(".", "").replace(",", ".")
            try:
                price = float(price_str)
            except ValueError:
                pass

        # Parse URL for additional data
        url_data = self._parse_url(href)

        # Image
        img = card.select_one("img[src*='chavesnamao']")
        image_url = img.get("src") if img else None

        # Property type from URL or title
        prop_type = url_data.get("type", "other")

        # Area logic:
        # - "Área útil" from features = built area (área construída)
        # - URL area = total area (terreno) — more reliable for total
        # - For land: total_area is what matters
        feat_area_raw = features.get("área útil") or features.get("área total")
        feat_area = None
        if feat_area_raw and feat_area_raw not in ("undefined", "0"):
            try:
                feat_area = float(feat_area_raw)
                if feat_area <= 0:
                    feat_area = None
            except ValueError:
                feat_area = None

        url_area = url_data.get("area")

        # Use URL area as total_area (more reliable for land/total)
        # Use feature area as built_area
        # For land, prefer the larger value (feature "Área útil" is actually total for land)
        if prop_type == "land":
            total_area = max(url_area or 0, feat_area or 0) or None
            built_area = None
        else:
            total_area = url_area if url_area and url_area > (feat_area or 0) else feat_area
            built_area = feat_area if feat_area and url_area and url_area > feat_area else None

        # Also try to extract area from title as last resort
        if not total_area and title:
            title_area = re.search(r"([\d.,]+)\s*m[²2]", title)
            if title_area:
                try:
                    total_area = float(title_area.group(1).replace(".", "").replace(",", "."))
                except ValueError:
                    pass

        return {
            "id": card_id,
            "url": url,
            "title": title,
            "type": prop_type,
            "price": price or url_data.get("price"),
            "area": total_area,
            "built_area": built_area,
            "bedrooms": _safe_int(features.get("quartos")),
            "bathrooms": _safe_int(features.get("banheiros")),
            "parking": _safe_int(features.get("garagens")),
            "street": street if street != "Endereço indisponível" else None,
            "neighborhood": neighborhood,
            "city": "Marília",
            "state": "SP",
            "image_url": image_url,
        }

    def _parse_url(self, href: str) -> dict[str, Any]:
        """Extract data from structured URL.

        Example: /imovel/casa-a-venda-3-quartos-com-garagem-sp-marilia-jardim-xxx-120m2-RS350000/id-12345/
        """
        data: dict[str, Any] = {}

        # Type
        path = href.lower()
        if "/terreno" in path or "/area-" in path:
            data["type"] = "land"
        elif "/casa-em-condominio" in path:
            data["type"] = "condo_house"
        elif "/casa" in path:
            data["type"] = "house"
        elif "/apartamento" in path:
            data["type"] = "apartment"
        elif "/fazenda" in path or "/chacara" in path or "/sitio" in path:
            data["type"] = "farm"
        elif "/comercial" in path or "/sala" in path or "/galpao" in path:
            data["type"] = "commercial"

        # Price
        price_match = re.search(r"RS(\d+)", href)
        if price_match:
            data["price"] = int(price_match.group(1))

        # Area
        area_match = re.search(r"-(\d+)m2", href)
        if area_match:
            data["area"] = int(area_match.group(1))

        return data

    def extract_source_id(self, item: dict[str, Any]) -> str:
        return str(item["id"])


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

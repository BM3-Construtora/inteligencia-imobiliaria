"""Collector for União Imobiliária (DreamKeys public API)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import UNIAO_API_URL, MAX_PAGES_PER_SPIDER
from src.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

PAGE_SIZE = 50


class UniaoCollector(BaseCollector):
    """Collects properties from DreamKeys public API (União Imobiliária)."""

    source = "uniao"

    async def fetch_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30) as client:
            page = 1
            total_pages = 1  # will be updated from first response

            while page <= min(total_pages, MAX_PAGES_PER_SPIDER):
                logger.info(f"[uniao] Fetching page {page}/{total_pages}")

                resp = await client.get(
                    UNIAO_API_URL,
                    params={
                        "city": "Marília",
                        "page": page,
                        "limit": PAGE_SIZE,
                        "business": "SALE",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                total_pages = data.get("totalPages", 1)
                items = data.get("properties", [])

                if not items:
                    break

                all_items.extend(items)
                logger.info(
                    f"[uniao] Page {page}: {len(items)} items "
                    f"(total so far: {len(all_items)})"
                )
                page += 1

        logger.info(f"[uniao] Total fetched: {len(all_items)} items")
        return all_items

    def extract_source_id(self, item: dict[str, Any]) -> str:
        return item["id"]

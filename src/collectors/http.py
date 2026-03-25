"""HTTP helpers for HTML scrapers using cloudscraper."""

from __future__ import annotations

import time
import logging
from typing import Optional

import cloudscraper

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Reuse a single scraper instance across requests
_scraper: Optional[cloudscraper.CloudScraper] = None


def get_scraper() -> cloudscraper.CloudScraper:
    global _scraper
    if _scraper is None:
        _scraper = cloudscraper.create_scraper()
        _scraper.headers.update(DEFAULT_HEADERS)
    return _scraper


def fetch_page(url: str, delay: float = 1.0) -> str:
    """Fetch a page with cloudscraper, respecting a delay between requests."""
    scraper = get_scraper()
    logger.debug(f"Fetching {url}")
    time.sleep(delay)
    resp = scraper.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text

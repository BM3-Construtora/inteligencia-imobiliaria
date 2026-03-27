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

MAX_RETRIES = 3

# Reuse a single scraper instance across requests
_scraper: Optional[cloudscraper.CloudScraper] = None


def get_scraper() -> cloudscraper.CloudScraper:
    global _scraper
    if _scraper is None:
        _scraper = cloudscraper.create_scraper()
        _scraper.headers.update(DEFAULT_HEADERS)
    return _scraper


def fetch_page(url: str, delay: float = 1.0) -> str:
    """Fetch a page with cloudscraper, with retry and exponential backoff."""
    scraper = get_scraper()
    logger.debug(f"Fetching {url}")
    time.sleep(delay)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = scraper.get(url, timeout=20)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            wait = delay * (2 ** attempt)
            logger.warning(f"Fetch failed (attempt {attempt}/{MAX_RETRIES}): {e}. Retrying in {wait:.0f}s")
            time.sleep(wait)

    raise RuntimeError("Unreachable")

"""HTTP helpers for HTML scrapers using cloudscraper."""

from __future__ import annotations

import threading
import time
import logging

import cloudscraper

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com.br/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

MAX_RETRIES = 3

# Thread-local scraper instances (safe for parallel scrapers)
_local = threading.local()


def get_scraper() -> cloudscraper.CloudScraper:
    if not hasattr(_local, "scraper"):
        _local.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False},
        )
        _local.scraper.headers.update(DEFAULT_HEADERS)
    return _local.scraper


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

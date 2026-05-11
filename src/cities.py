"""Multi-city support — fetch active cities from DB with caching."""

from __future__ import annotations

from functools import lru_cache

from src.db import get_client


@lru_cache(maxsize=1)
def get_active_cities() -> list[dict]:
    """Returns list of active cities with name, aliases, centroid, bbox."""
    sb = get_client()
    r = sb.table("cities").select("*").eq("is_active", True).execute()
    return r.data or []


def is_target_city(name: str | None) -> bool:
    """Fuzzy check across all active cities + their aliases."""
    if not name:
        return False
    n = name.strip().lower()
    for c in get_active_cities():
        if n == c["name"].lower():
            return True
        for alias in (c.get("aliases") or []):
            if n == alias.lower():
                return True
    return False


def primary_city() -> str:
    """First active city — fallback for backward compat."""
    cities = get_active_cities()
    return cities[0]["name"] if cities else "Marília"

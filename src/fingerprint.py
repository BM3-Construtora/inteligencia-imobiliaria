"""Deterministic listing fingerprint for fast dedup shortcut.

Two listings with the same fingerprint are very likely the same property,
even across portals or across re-listings within the same portal.

Components: neighborhood | street_name | number | area_bucket(50m²)

Missing components yield None — only return a key when we have enough
signal to be useful (street_name + (number OR neighborhood)).
"""

from __future__ import annotations

from typing import Any

from src.address import extract_components, normalize_neighborhood


def compute_fingerprint(listing: dict[str, Any]) -> str | None:
    neigh = normalize_neighborhood(listing.get("neighborhood") or "")
    raw_addr = listing.get("address") or listing.get("street") or ""
    comps = extract_components(raw_addr) if raw_addr else {"street_name": None, "number": None}

    street = (comps.get("street_name") or "").strip()
    number = (comps.get("number") or "").strip()

    if not street and not listing.get("street"):
        return None
    if not street:
        street = (listing.get("street") or "").lower().strip()

    if not street or (not number and not neigh):
        return None

    area = listing.get("total_area")
    try:
        area_bucket = int(float(area) // 50) if area else "x"
    except (TypeError, ValueError):
        area_bucket = "x"

    return f"{neigh.lower()}|{street}|{number}|{area_bucket}"

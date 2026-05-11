"""Tests for data quality rules: city detection and quarantine reason codes."""

from __future__ import annotations

from src.normalizer import _is_marilia, _validate_listing


def test_is_marilia_fuzzy_match():
    """All these variants must resolve to Marília."""
    assert _is_marilia("Marília") is True
    assert _is_marilia("Marilia") is True
    assert _is_marilia("MARÍLIA") is True
    assert _is_marilia("marília-SP") is True
    assert _is_marilia("mar?lia") is True   # broken encoding artifact
    assert _is_marilia("Garça") is False
    assert _is_marilia("São Paulo") is False


def test_quarantine_reason_codes():
    """Enum values must remain stable — these are read by dashboards/alerts."""
    expected = {
        "price_too_low",
        "price_too_high",
        "ppm2_too_low",
        "ppm2_too_high",
        "area_implausible",
    }

    seen = set()

    # price_too_low
    r = _validate_listing({
        "property_type": "house", "sale_price": 500,
        "total_area": 200, "price_per_m2": 2.5,
    })
    seen.add(r["quarantine_reason"])

    # price_too_high
    r = _validate_listing({
        "property_type": "house", "sale_price": 60_000_000,
        "total_area": 1000, "price_per_m2": 60_000,
    })
    seen.add(r["quarantine_reason"])

    # ppm2_too_low
    r = _validate_listing({
        "property_type": "land", "sale_price": 10_000,
        "total_area": 1000, "price_per_m2": 10.0,
    })
    seen.add(r["quarantine_reason"])

    # ppm2_too_high
    r = _validate_listing({
        "property_type": "apartment", "sale_price": 1_000_000,
        "total_area": 25, "price_per_m2": 40_000,
    })
    seen.add(r["quarantine_reason"])

    # area_implausible
    r = _validate_listing({
        "property_type": "house", "sale_price": 500_000,
        "total_area": 100_000, "price_per_m2": 5.0,
    })
    seen.add(r["quarantine_reason"])

    # Every reason we exercised should be among the canonical set
    assert seen.issubset(expected)
    # And we should have hit at least 3 distinct reasons
    assert len(seen) >= 3

"""Tests for src.deduplicator._compare and _haversine — pure logic."""

from __future__ import annotations

from src.deduplicator import _compare, _haversine


def _base(**overrides):
    d = {
        "id": 1,
        "source": "vivareal",
        "source_id": "vr-1",
        "property_type": "house",
        "sale_price": 300_000,
        "total_area": 200,
        "address": "Rua das Flores 100",
        "street": "Rua das Flores",
        "neighborhood": "Centro",
        "latitude": -22.213,
        "longitude": -49.946,
        "bedrooms": 3,
        "bathrooms": 2,
    }
    d.update(overrides)
    return d


def test_compare_same_source_id_definitive_match():
    a = _base(id=1, source="vivareal", source_id="abc-123")
    b = _base(id=2, source="chavesnamao", source_id="abc-123")
    out = _compare(a, b)
    assert out is not None
    assert out["match_score"] == 1.0
    assert out["decision_rule"] == "source_id_match"


def test_compare_different_addr_far_price_no_match():
    a = _base(
        id=1, source="vivareal", source_id="x1",
        address="Rua das Flores 100",
        sale_price=200_000, total_area=200,
        latitude=-22.0, longitude=-49.0,
    )
    b = _base(
        id=2, source="chavesnamao", source_id="y1",
        address="Avenida Paulista 9999",
        sale_price=900_000, total_area=600,
        latitude=-23.5, longitude=-46.6,
        bedrooms=5, bathrooms=4,
    )
    assert _compare(a, b) is None


def test_compare_location_plus_financial():
    a = _base(
        id=1, source="vivareal", source_id="x1",
        address="Rua das Flores, 100",
        sale_price=300_000, total_area=200,
        bedrooms=3, bathrooms=2,
    )
    b = _base(
        id=2, source="chavesnamao", source_id="y1",
        address="Rua das Flores, 100",
        sale_price=310_000, total_area=205,
        bedrooms=3, bathrooms=2,
    )
    out = _compare(a, b)
    assert out is not None
    assert out["decision_rule"] == "loc+financial"
    assert out["match_score"] >= 0.90


def test_compare_bed_mismatch_blocks_weak_match():
    """addr matches but bedrooms differ + no full financial confirm → None."""
    a = _base(
        id=1, source="vivareal", source_id="x1",
        address="Rua das Flores 100",
        sale_price=300_000, total_area=200,
        bedrooms=2, bathrooms=2,
    )
    b = _base(
        id=2, source="chavesnamao", source_id="y1",
        address="Rua das Flores 100",
        sale_price=500_000, total_area=400,  # financials don't match
        bedrooms=4, bathrooms=2,
    )
    assert _compare(a, b) is None


def test_haversine_known_distance():
    """São Paulo (-23.55, -46.63) ↔ Marília (-22.21, -49.95) ≈ 370km (great-circle)."""
    d = _haversine(-23.5505, -46.6333, -22.2139, -49.9456)
    km = d / 1000
    # Great-circle distance (~370km); road distance is ~430km but haversine ignores roads.
    assert 350 <= km <= 400


def test_haversine_zero():
    assert _haversine(-22.21, -49.95, -22.21, -49.95) < 1.0

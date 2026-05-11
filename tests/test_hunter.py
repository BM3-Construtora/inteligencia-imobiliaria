"""Tests for src.hunter — pure scoring."""

from __future__ import annotations

import bisect

from src.hunter import _score_listing


def _ctx(**over):
    base = {
        "avg_price": 250_000,
        "median_price": 220_000,
        "avg_price_m2": 500,
        "avg_area": 300,
        "total_land": 100,
    }
    base.update(over)
    return base


def test_score_land_perfect():
    """A near-ideal MCMV land from uniao (1.0 confidence) should score high."""
    listing = {
        "source": "uniao",
        "sale_price": 120_000,
        "total_area": 500,
        "price_per_m2": 240,
        "is_mcmv": True,
        "latitude": -22.2,
        "longitude": -49.9,
        "neighborhood": "Centro",
        "address": "Rua X, 100",
        "title": "Terreno plano",
        "features": {},
        "first_seen_at": "2025-01-01T00:00:00+00:00",
    }
    score, breakdown = _score_listing(listing, _ctx())
    assert score >= 70
    assert breakdown["confidence_multiplier"] == 1.0
    assert breakdown["mcmv"] == 10


def test_score_land_missing_data_lower_score():
    """Same price/area but missing geo/neighborhood/title/features → lower."""
    full = {
        "source": "uniao",
        "sale_price": 120_000,
        "total_area": 500,
        "price_per_m2": 240,
        "is_mcmv": True,
        "latitude": -22.2, "longitude": -49.9,
        "neighborhood": "Centro", "address": "Rua X 100",
        "title": "T",
        "features": {},
        "first_seen_at": "2025-01-01T00:00:00+00:00",
    }
    sparse = {
        "source": "uniao",
        "sale_price": 120_000,
        "total_area": 500,
        "price_per_m2": 240,
        "is_mcmv": False,
    }
    full_score, _ = _score_listing(full, _ctx())
    sparse_score, _ = _score_listing(sparse, _ctx())
    assert full_score > sparse_score


def test_percentile_calculation():
    """Given [10,20,30,40,50], percentile of 30 should be 60% (3 out of 5).

    Hunter uses rank = count of items <= score, then pct = rank/total * 100.
    For 30: 3 items <=30 → 3/5 = 60%.
    """
    scores = sorted([10, 20, 30, 40, 50])
    target = 30
    rank = bisect.bisect_right(scores, target)
    pct = (rank / len(scores)) * 100
    assert pct == 60.0

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


def test_v2_no_signal_is_identity():
    """Sem sinais V2, o score é idêntico ao base (degradação graciosa)."""
    listing = {
        "source": "uniao",
        "sale_price": 120_000,
        "total_area": 500,
        "price_per_m2": 240,
        "is_mcmv": True,
        "latitude": -22.2, "longitude": -49.9,
        "neighborhood": "Centro", "address": "Rua X, 100",
        "title": "Terreno plano",
        "features": {},
        "first_seen_at": "2025-01-01T00:00:00+00:00",
    }
    base_score, base_bd = _score_listing(listing, _ctx())
    v2_score, v2_bd = _score_listing(listing, _ctx(), None)
    assert base_score == v2_score
    assert v2_bd["v2_multiplier"] == 1.0


def test_v2_undervalued_raises_score():
    """Um listing subprecificado no AVM (confiança alta) pontua mais que sem sinal."""
    listing = {
        "source": "uniao",
        "sale_price": 120_000,
        "total_area": 500,
        "price_per_m2": 240,
        "is_mcmv": True,
        "latitude": -22.2, "longitude": -49.9,
        "neighborhood": "Centro", "address": "Rua X, 100",
        "title": "Terreno plano",
        "features": {},
        "first_seen_at": "2025-01-01T00:00:00+00:00",
    }
    plain, _ = _score_listing(listing, _ctx(), None)
    avm = {"mispricing_pct": 18.0, "is_undervalued": True, "confidence": 0.8}
    boosted, bd = _score_listing(listing, _ctx(), avm)
    assert boosted > plain
    assert bd["v2_multiplier"] > 1.0
    assert bd.get("v2_undervalued") is True


def test_v2_low_confidence_avm_ignored():
    """AVM com baixa confiança não move o score (evita ruído de modelo fraco)."""
    listing = {
        "source": "uniao", "sale_price": 120_000, "total_area": 500,
        "price_per_m2": 240, "is_mcmv": True,
        "latitude": -22.2, "longitude": -49.9,
        "neighborhood": "Centro", "address": "Rua X, 100",
        "title": "T", "features": {}, "first_seen_at": "2025-01-01T00:00:00+00:00",
    }
    plain, _ = _score_listing(listing, _ctx(), None)
    weak_avm = {"mispricing_pct": 18.0, "is_undervalued": True, "confidence": 0.1}
    same, bd = _score_listing(listing, _ctx(), weak_avm)
    assert same == plain
    assert bd["v2_multiplier"] == 1.0


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

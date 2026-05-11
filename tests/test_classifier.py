"""Tests for src.classifier."""

from __future__ import annotations

from src.classifier import DEFAULT_MCMV_MAX_PRICE, classify_listing


def test_mcmv_threshold():
    """price=200k, built=55, type=house → casa_mcmv."""
    listing = {
        "property_type": "house",
        "sale_price": 200_000,
        "built_area": 55,
        "total_area": 250,
    }
    assert classify_listing(listing) == "casa_mcmv"


def test_mcmv_too_expensive():
    """price=400k > MCMV teto (350k default) → not casa_mcmv."""
    listing = {
        "property_type": "house",
        "sale_price": 400_000,
        "built_area": 55,
    }
    tier = classify_listing(listing)
    assert tier != "casa_mcmv"
    # 400k > 350k threshold → casa_medio_padrao
    assert tier == "casa_medio_padrao"


def test_mcmv_too_large():
    """built=120m² > MCMV_MAX_AREA(60)+tolerance(10) → not MCMV."""
    listing = {
        "property_type": "house",
        "sale_price": 250_000,
        "built_area": 120,
    }
    tier = classify_listing(listing)
    assert tier != "casa_mcmv"
    assert tier == "casa_baixo_padrao"


def test_tier_assignments():
    samples = [
        ({"property_type": "apartment", "sale_price": 250_000}, "apto_economico"),
        ({"property_type": "apartment", "sale_price": 500_000}, "apto_medio"),
        ({"property_type": "apartment", "sale_price": 900_000}, "apto_alto"),
        ({"property_type": "land", "sale_price": 80_000, "total_area": 250}, "terreno_economico"),
        ({"property_type": "land", "sale_price": 200_000, "total_area": 300}, "terreno_medio"),
        ({"property_type": "land", "sale_price": 500_000, "total_area": 300}, "terreno_alto"),
        ({"property_type": "land", "sale_price": 600_000, "total_area": 1500}, "terreno_grande"),
        ({"property_type": "house", "sale_price": 800_000, "built_area": 200}, "casa_alto_padrao"),
    ]
    for listing, expected in samples:
        assert classify_listing(listing, DEFAULT_MCMV_MAX_PRICE) == expected, listing


def test_no_classification_when_price_zero():
    assert classify_listing({"property_type": "house", "sale_price": 0}) is None

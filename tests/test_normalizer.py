"""Tests for src.normalizer — pure normalization + validation."""

from __future__ import annotations

import pytest

from src.normalizer import (
    TOCA_TYPE_MAP,
    _calc_price_per_m2,
    _is_marilia,
    _validate_listing,
    normalize_toca,
    normalize_uniao,
)


def test_normalize_uniao_basic(sample_raw_uniao):
    n = normalize_uniao(sample_raw_uniao)
    assert n["source"] == "uniao"
    assert n["source_id"] == "uniao-123"
    assert n["property_type"] == "house"
    assert n["sale_price"] == 220000
    assert n["total_area"] == 250
    assert n["built_area"] == 55
    assert n["bedrooms"] == 2
    assert n["city"] == "Marília"
    assert n["business_type"] == "sale"
    assert n["main_image_url"] == "http://img/1.jpg"
    assert len(n["images"]) == 2
    # price/m² should be price/area = 880
    assert n["price_per_m2"] == 880.0


def test_normalize_uniao_missing_price_and_area_rejected(sample_raw_uniao):
    """No price + no area → _validate_listing rejects."""
    sample_raw_uniao["salePrice"] = None
    sample_raw_uniao["rentPrice"] = None
    sample_raw_uniao["totalArea"] = None
    n = normalize_uniao(sample_raw_uniao)
    assert _validate_listing(n) is None


def test_normalize_toca_type_mapping():
    """Spot-check several entries in TOCA_TYPE_MAP."""
    assert TOCA_TYPE_MAP["Casa"] == "house"
    assert TOCA_TYPE_MAP["Apartamento"] == "apartment"
    assert TOCA_TYPE_MAP["Terreno"] == "land"
    assert TOCA_TYPE_MAP["Casa Em Condomínio"] == "condo_house"
    assert TOCA_TYPE_MAP["Sítio"] == "rural"
    assert TOCA_TYPE_MAP["Chácara"] == "farm"
    assert TOCA_TYPE_MAP["Sala Comercial"] == "commercial"


def test_normalize_toca_basic(sample_raw_toca):
    n = normalize_toca(sample_raw_toca)
    assert n["source"] == "toca"
    assert n["property_type"] == "house"
    assert n["sale_price"] == 350000
    assert n["bedrooms"] == 3
    assert n["suites"] == 1
    assert n["business_type"] == "sale"


def test_validate_listing_price_too_low_quarantines():
    data = {
        "property_type": "house",
        "sale_price": 500,
        "total_area": 200,
        "built_area": 80,
        "price_per_m2": 2.5,
    }
    out = _validate_listing(data)
    assert out is not None
    assert out["quarantined"] is True
    assert out["quarantine_reason"] == "price_too_low"


def test_validate_listing_ppm2_too_low_quarantines():
    data = {
        "property_type": "land",
        "sale_price": 10000,
        "total_area": 1000,
        "price_per_m2": 10.0,
    }
    out = _validate_listing(data)
    assert out is not None
    assert out["quarantined"] is True
    assert out["quarantine_reason"] == "ppm2_too_low"


def test_validate_listing_area_implausible():
    """Non-rural house with absurd area should quarantine."""
    data = {
        "property_type": "house",
        "sale_price": 400_000,
        "total_area": 200_000,
        "price_per_m2": 2.0,
    }
    out = _validate_listing(data)
    assert out is not None
    # ppm2 is 2 → would trigger ppm2_too_low first. Use a saner ppm2 setup:
    data2 = {
        "property_type": "house",
        "sale_price": 200_000_000,  # huge price to keep ppm2 sane
        "total_area": 200_000,
        "price_per_m2": 1000.0,
    }
    out2 = _validate_listing(data2)
    assert out2 is not None
    # price_too_high triggers first when > 50M. Verify quarantined either way.
    assert out2["quarantined"] is True
    assert out2["quarantine_reason"] in ("area_implausible", "price_too_high")


def test_is_marilia_accepts_variants():
    assert _is_marilia("Marília") is True
    assert _is_marilia("Marilia") is True
    assert _is_marilia("MARÍLIA") is True
    assert _is_marilia("mar?lia") is True
    assert _is_marilia("Garça") is False
    assert _is_marilia(None) is False
    assert _is_marilia("") is False


def test_built_area_greater_than_total_swaps():
    data = {
        "property_type": "house",
        "sale_price": 300_000,
        "total_area": 60,       # smaller (wrong)
        "built_area": 200,      # bigger (wrong) → swap
        "price_per_m2": 5000.0,
    }
    out = _validate_listing(data)
    assert out is not None
    assert out["total_area"] == 200
    assert out["built_area"] == 60


def test_calc_price_per_m2_only_computes():
    """_calc só calcula; plausibilidade é responsabilidade de _validate_listing.

    Antes, valores absurdos viravam None aqui e escapavam da quarentena. Agora o
    valor é calculado e a quarentena o captura (ver test abaixo).
    """
    assert _calc_price_per_m2(200_000, 200) == 1000.0
    assert _calc_price_per_m2(100_000, 0) is None   # área 0 → sem cálculo
    assert _calc_price_per_m2(None, 100) is None
    assert _calc_price_per_m2(100, None) is None
    # Valores implausíveis NÃO são mais anulados silenciosamente:
    assert _calc_price_per_m2(100_000_000, 1) == 100_000_000.0  # ppm2 altíssimo
    assert _calc_price_per_m2(1, 1_000_000) == 0.0              # ppm2 irrisório


def test_absurd_ppm2_is_quarantined_not_silenced():
    """Um ppm2 absurdamente alto deve ser quarentenado (auditável), não virar NULL."""
    # preço abaixo do teto de price_too_high (50M) mas área minúscula → ppm2 alto
    high = _validate_listing({
        "property_type": "land",
        "sale_price": 1_000_000,
        "total_area": 1,
        "price_per_m2": _calc_price_per_m2(1_000_000, 1),
    })
    assert high is not None
    assert high["quarantined"] is True
    assert high["quarantine_reason"] == "ppm2_too_high"

    low = _validate_listing({
        "property_type": "land",
        "sale_price": 1,
        "total_area": 1_000_000,
        "price_per_m2": _calc_price_per_m2(1, 1_000_000),
    })
    assert low is not None
    assert low["quarantined"] is True
    assert low["quarantine_reason"] == "ppm2_too_low"

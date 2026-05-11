"""Tests for src.address."""

from __future__ import annotations

from src.address import (
    address_similarity,
    normalize_address,
    normalize_neighborhood,
    remove_accents,
)


def test_normalize_address_strips_accents():
    assert "á" not in normalize_address("Rua São João")
    assert remove_accents("Marília") == "Marilia"


def test_normalize_address_expands_abbreviations():
    out = normalize_address("R. das Flores 100")
    assert "rua" in out
    assert "das" in out
    assert "flores" in out


def test_address_similarity_identical():
    assert address_similarity("Rua das Flores 100", "Rua das Flores 100") == 1.0


def test_address_similarity_different():
    score = address_similarity("Rua das Flores 100", "Avenida Paulista 9999")
    assert score < 0.4


def test_address_similarity_empty_returns_zero():
    assert address_similarity("", "Rua X") == 0.0
    assert address_similarity("Rua X", "") == 0.0


def test_normalize_neighborhood_title_case():
    assert normalize_neighborhood("jardim maria izabel") == "Jardim Maria Izabel"
    assert normalize_neighborhood("jd. califórnia") == "Jardim California"

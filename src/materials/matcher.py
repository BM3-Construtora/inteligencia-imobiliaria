"""Matching de listings de fornecedor → SKU canônico.

Estratégia em ordem:
1. EAN exato (quando ambos têm)
2. Marca + nome (rapidfuzz token_set_ratio) com threshold

Sem match → listing fica órfão (sku_id NULL) e pode ser triado depois.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz

from src.materials.models import CommonListing

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 78  # token_set_ratio


@dataclass
class SkuCandidate:
    """Candidato canônico do banco para matching."""
    id: int
    canonical_name: str
    brand: str | None
    ean: str | None
    model: str | None = None


def match(listing: CommonListing, candidates: Iterable[SkuCandidate]) -> int | None:
    """Retorna sku_id do melhor match ou None."""
    cands = list(candidates)
    if not cands:
        return None

    # 1. EAN exato
    if listing.ean:
        normalized = _norm_ean(listing.ean)
        for c in cands:
            if c.ean and _norm_ean(c.ean) == normalized:
                return c.id

    # 2. Fuzzy nome + marca
    listing_text = _build_text(listing.supplier_name, listing.brand)
    if not listing_text:
        return None

    best_id: int | None = None
    best_score = 0
    for c in cands:
        candidate_text = _build_text(c.canonical_name, c.brand, c.model)
        score = fuzz.token_set_ratio(listing_text, candidate_text)
        # Bonus quando marca bate exatamente
        if listing.brand and c.brand and _norm_text(listing.brand) == _norm_text(c.brand):
            score += 5
        if score > best_score:
            best_score = score
            best_id = c.id

    if best_score >= FUZZY_THRESHOLD:
        return best_id

    return None


def _norm_ean(ean: str) -> str:
    return re.sub(r"\D", "", ean or "")


def _norm_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower().strip())


def _build_text(*parts: str | None) -> str:
    return " ".join(_norm_text(p) for p in parts if p)

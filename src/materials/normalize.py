"""Normalização de preço por unidade + detecção de outliers.

Funções puras chamadas pelo runner antes de persistir price_history.

price_per_kg: usa material_sku.weight_kg ou tenta extrair do nome
price_per_m2: para porcelanato/cerâmica em m2
price_per_unit: para itens vendidos por unidade (bloco, tubo)

Outlier: heurística simples — preço fora de [0.1×, 10×] da mediana da
categoria é flagged. Mediana é cacheada por categoria/run.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Faixas razoáveis de preço por kg, em R$ (Brasil 2026, MCMV-friendly).
# Usado pra outlier detection quando price_per_kg está disponível.
PRICE_PER_KG_RANGE: dict[str, tuple[float, float]] = {
    "cimento": (0.5, 3.0),       # ~R$0,75/kg saco 50kg
    "argamassa": (0.8, 6.0),
    "aco": (4.0, 15.0),          # vergalhão
    "bloco": (0.4, 4.0),         # bloco cerâmico
}

PRICE_PER_M2_RANGE: dict[str, tuple[float, float]] = {
    "revestimento": (20.0, 250.0),
    "cobertura": (15.0, 200.0),
}

# Regex para extrair peso/volume do nome
WEIGHT_PATTERNS = [
    (re.compile(r"(\d{1,4})\s*kgs?\b", re.IGNORECASE), 1.0),
    (re.compile(r"(\d{1,4})\s*g\b(?!ra)", re.IGNORECASE), 0.001),
]
VOLUME_PATTERNS = [
    (re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*l\b(?!a)", re.IGNORECASE), 1.0),
    (re.compile(r"(\d{1,4})\s*ml\b", re.IGNORECASE), 0.001),
]


@dataclass
class Normalized:
    price_per_kg: float | None = None
    price_per_m2: float | None = None
    price_per_unit: float | None = None
    is_outlier: bool = False
    outlier_reason: str | None = None


def extract_weight_kg(name: str | None) -> float | None:
    """Tenta achar peso em kg no nome do produto."""
    if not name:
        return None
    for pattern, mult in WEIGHT_PATTERNS:
        m = pattern.search(name)
        if m:
            try:
                value = float(m.group(1).replace(",", "."))
                kg = value * mult
                if 0.1 <= kg <= 500:
                    return kg
            except ValueError:
                continue
    return None


def compute(
    price: float | None,
    category: str | None,
    unit: str | None,
    weight_kg: float | None,
    supplier_name: str | None,
) -> Normalized:
    out = Normalized()
    if price is None or price <= 0:
        out.is_outlier = True
        out.outlier_reason = "price<=0"
        return out

    # Preço por unidade (kg)
    effective_kg = weight_kg or extract_weight_kg(supplier_name)
    if effective_kg and effective_kg > 0:
        out.price_per_kg = round(price / effective_kg, 4)

    # price_per_m2 quando unit indica m2
    if unit == "m2":
        out.price_per_m2 = round(price, 4)
    elif unit and unit.startswith("milheiro"):
        out.price_per_unit = round(price / 1000, 4)
    elif unit in {"un", "barra_12m", "barra_6m", "barra_3m", "rolo_100m", "rolo_50m"}:
        out.price_per_unit = round(price, 4)

    # Outlier por faixa esperada
    cat = (category or "").lower()
    if out.price_per_kg is not None and cat in PRICE_PER_KG_RANGE:
        lo, hi = PRICE_PER_KG_RANGE[cat]
        if not (lo <= out.price_per_kg <= hi):
            out.is_outlier = True
            out.outlier_reason = f"price_per_kg {out.price_per_kg} fora [{lo},{hi}]"

    if out.price_per_m2 is not None and cat in PRICE_PER_M2_RANGE:
        lo, hi = PRICE_PER_M2_RANGE[cat]
        if not (lo <= out.price_per_m2 <= hi):
            out.is_outlier = True
            out.outlier_reason = f"price_per_m2 {out.price_per_m2} fora [{lo},{hi}]"

    return out

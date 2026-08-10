"""Extract land/total area from listing titles and descriptions.

Used as a fallback when the source doesn't provide total_area (common for
chavesnamao and vivareal land listings, where ~48% of rows are null).
"""

from __future__ import annotations

import re

_AREA_PATTERNS = [
    # "350 m²", "350m²", "350 m2", "350m2", "350 metros"
    re.compile(r"(\d{2,5}(?:[.,]\d{1,2})?)\s*(?:m²|m2|metros\s*quadrados|metros)", re.IGNORECASE),
    # "área de 350", "area: 350"
    re.compile(r"[áa]rea\s*(?:de|:)?\s*(\d{2,5}(?:[.,]\d{1,2})?)", re.IGNORECASE),
    # "terreno de 350", "lote de 350"
    re.compile(r"(?:terreno|lote)\s*(?:de|com)?\s*(\d{2,5}(?:[.,]\d{1,2})?)", re.IGNORECASE),
    # "medindo 350", "medindo aproximadamente 350"
    re.compile(r"medindo\s*(?:aproximadamente|aprox\.?|cerca\s*de)?\s*(\d{2,5}(?:[.,]\d{1,2})?)", re.IGNORECASE),
    # "área total de 350", "área total: 350"
    re.compile(r"[áa]rea\s*total\s*(?:de|:)?\s*(\d{2,5}(?:[.,]\d{1,2})?)", re.IGNORECASE),
]

# Dimensões "12x30", "12 x 30", "12m x 30m", "12,5 por 30"
_DIMS_PATTERN = re.compile(
    r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:m|metros)?\s*(?:x|por|×)\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:m|metros)?",
    re.IGNORECASE,
)

MIN_AREA = 50.0
MAX_AREA = 50000.0


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


_THOUSANDS = re.compile(r"(?<=\d)\.(?=\d{3}(\D|$))")


def extract_area(text: str | None) -> float | None:
    """Best-effort extraction of total area in m² from free text.

    Returns None if no plausible value found. Plausible range: 50–50.000 m².
    """
    if not text:
        return None

    # Normalize Brazilian thousand separator: "1.200" -> "1200" (keep decimal comma)
    text = _THOUSANDS.sub("", text)

    for pat in _AREA_PATTERNS:
        for m in pat.finditer(text):
            v = _to_float(m.group(1))
            if v and MIN_AREA <= v <= MAX_AREA:
                return v

    m = _DIMS_PATTERN.search(text)
    if m:
        a = _to_float(m.group(1))
        b = _to_float(m.group(2))
        if a and b:
            area = a * b
            if MIN_AREA <= area <= MAX_AREA:
                return area

    return None

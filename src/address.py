"""Brazilian address normalization and structured comparison."""

from __future__ import annotations

import re
import unicodedata

# Common abbreviation expansions for Brazilian addresses
ABBREVIATIONS = {
    "r": "rua", "r.": "rua",
    "av": "avenida", "av.": "avenida",
    "al": "alameda", "al.": "alameda",
    "tv": "travessa", "tv.": "travessa",
    "trav": "travessa", "trav.": "travessa",
    "pca": "praca", "pç": "praca", "pça": "praca", "pça.": "praca",
    "rod": "rodovia", "rod.": "rodovia",
    "est": "estrada", "est.": "estrada",
    "lg": "largo", "lg.": "largo",
    "bc": "beco", "bc.": "beco",
    # Neighborhood abbreviations
    "jd": "jardim", "jd.": "jardim",
    "pq": "parque", "pq.": "parque",
    "res": "residencial", "res.": "residencial",
    "vl": "vila", "vl.": "vila",
    "cj": "conjunto", "cj.": "conjunto",
    "n.h.": "nucleo habitacional", "n.h": "nucleo habitacional",
    "nh": "nucleo habitacional",
    "cond": "condominio", "cond.": "condominio",
}

# Street types (logradouro)
STREET_TYPES = {
    "rua", "avenida", "alameda", "travessa", "praca", "rodovia",
    "estrada", "largo", "beco", "viela",
}


def remove_accents(text: str) -> str:
    """Remove diacritics from text."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_address(addr: str) -> str:
    """Normalize a Brazilian address to a canonical form for comparison.

    Returns a flat lowercase string with expanded abbreviations and no accents.
    """
    if not addr:
        return ""

    addr = addr.lower().strip()
    addr = remove_accents(addr)

    # Expand abbreviations
    words = addr.split()
    expanded = []
    for w in words:
        clean = w.rstrip(",.")
        expanded.append(ABBREVIATIONS.get(clean, clean))

    addr = " ".join(expanded)

    # Remove punctuation except hyphens
    addr = re.sub(r"[^\w\s-]", "", addr)
    # Collapse whitespace
    addr = re.sub(r"\s+", " ", addr).strip()

    return addr


def extract_components(addr: str) -> dict[str, str | None]:
    """Extract structured components from a normalized address.

    Returns: {street_type, street_name, number, complement}
    """
    normalized = normalize_address(addr)
    parts = normalized.split()

    result: dict[str, str | None] = {
        "street_type": None,
        "street_name": None,
        "number": None,
        "complement": None,
    }

    if not parts:
        return result

    # Extract street type
    if parts[0] in STREET_TYPES:
        result["street_type"] = parts[0]
        parts = parts[1:]

    # Extract number (look for isolated digits or "nº X" or "n X")
    remaining = []
    found_number = False
    for i, p in enumerate(parts):
        if not found_number and re.match(r"^\d+[a-z]?$", p):
            # Check if it looks like a street number (not part of street name)
            # Street numbers are usually after the name, not at the start
            if i > 0 or result["street_type"]:
                result["number"] = p
                found_number = True
                # Everything after is complement
                if i + 1 < len(parts):
                    result["complement"] = " ".join(parts[i + 1:])
                break
        if p in ("n", "no", "nro", "numero"):
            continue  # skip "nº" prefix, grab next
        remaining.append(p)

    result["street_name"] = " ".join(remaining) if remaining else None

    return result


def address_similarity(addr_a: str, addr_b: str) -> float:
    """Compare two addresses and return similarity score 0-1.

    Uses component-based comparison for higher accuracy.
    """
    norm_a = normalize_address(addr_a)
    norm_b = normalize_address(addr_b)

    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0

    comp_a = extract_components(addr_a)
    comp_b = extract_components(addr_b)

    score = 0.0
    weights = 0.0

    # Street name comparison (heaviest weight)
    name_a = comp_a["street_name"] or ""
    name_b = comp_b["street_name"] or ""
    if name_a and name_b:
        name_sim = _token_similarity(name_a, name_b)
        score += name_sim * 0.6
        weights += 0.6
    elif not name_a and not name_b:
        pass  # Both empty, skip
    else:
        weights += 0.6  # One empty, counts as 0

    # Street type comparison
    type_a = comp_a["street_type"]
    type_b = comp_b["street_type"]
    if type_a and type_b:
        score += (1.0 if type_a == type_b else 0.0) * 0.1
        weights += 0.1

    # Number comparison
    num_a = comp_a["number"]
    num_b = comp_b["number"]
    if num_a and num_b:
        score += (1.0 if num_a == num_b else 0.0) * 0.3
        weights += 0.3
    elif num_a or num_b:
        weights += 0.3  # One has number, other doesn't

    return score / weights if weights > 0 else _token_similarity(norm_a, norm_b)


def _token_similarity(a: str, b: str) -> float:
    """Token-based Jaccard similarity."""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def normalize_neighborhood(name: str) -> str:
    """Normalize a neighborhood name."""
    if not name:
        return ""
    name = remove_accents(name.lower().strip())
    words = name.split()
    expanded = [ABBREVIATIONS.get(w.rstrip(".,"), w.rstrip(".,")) for w in words]
    result = " ".join(expanded)
    result = re.sub(r"[^\w\s]", "", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result.title()

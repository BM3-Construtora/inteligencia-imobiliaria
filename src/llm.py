"""LLM helpers — Claude API integration for enrichment tasks."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_HAIKU = "claude-haiku-4-5-20251001"


def extract_listing_attributes(description: str, title: str = "") -> Optional[dict[str, Any]]:
    """Use Claude Haiku to extract structured attributes from a listing description.

    Returns dict with: neighborhood_normalized, features_extracted, zoning_mentioned,
    infrastructure, nearby_amenities, is_condominium, has_water, has_electricity, etc.
    """
    if not ANTHROPIC_API_KEY:
        return None

    if not description or len(description.strip()) < 20:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""Analise este anúncio imobiliário de Marília-SP e extraia atributos estruturados.

Título: {title}
Descrição: {description[:1500]}

Retorne APENAS um JSON válido (sem markdown) com estes campos:
{{
  "bairro_normalizado": "nome padronizado do bairro (ex: 'Jardim Cavallari', não 'Jd. Cavalari')",
  "infraestrutura": ["lista de itens mencionados: asfalto, agua, esgoto, luz, gas, internet"],
  "proximidades": ["escola", "mercado", "hospital", "ponto de ônibus", etc.],
  "caracteristicas_terreno": ["plano", "aclive", "declive", "esquina", "frente pra rua principal"],
  "zoneamento_mencionado": "residencial/comercial/misto/null se não mencionado",
  "permite_construcao": true/false/null,
  "tem_agua": true/false/null,
  "tem_luz": true/false/null,
  "eh_condominio": true/false,
  "observacoes": "qualquer info relevante para compra que não caiba nos campos acima"
}}

Se não souber o valor, use null. Se a descrição não tiver info útil, retorne {{}}.
"""

        response = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Clean potential markdown wrapping
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]

        return json.loads(text)

    except json.JSONDecodeError:
        logger.debug(f"[llm] Failed to parse JSON from Haiku response")
        return None
    except Exception:
        logger.debug("[llm] Haiku call failed", exc_info=True)
        return None


def normalize_neighborhood(name: str) -> Optional[str]:
    """Use Claude Haiku to normalize a neighborhood name for Marília-SP.

    Handles: abbreviations (Jd. → Jardim), typos, casing, variants.
    """
    if not ANTHROPIC_API_KEY:
        return None

    if not name or len(name.strip()) < 2:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=50,
            messages=[{"role": "user", "content": (
                f"Normalize este nome de bairro de Marília-SP para a forma padrão oficial. "
                f"Corrija abreviações (Jd.→Jardim, Pq.→Parque, Res.→Residencial, Vl.→Vila), "
                f"erros de digitação, e casing. "
                f"Retorne APENAS o nome normalizado, nada mais.\n\n"
                f"Bairro: {name}"
            )}],
        )

        normalized = response.content[0].text.strip()
        # Sanity: should be similar length, not a full sentence
        if len(normalized) > len(name) * 3 or "\n" in normalized:
            return None
        return normalized

    except Exception:
        logger.debug(f"[llm] Failed to normalize neighborhood: {name}", exc_info=True)
        return None


def batch_normalize_neighborhoods(names: list[str]) -> dict[str, str]:
    """Normalize a batch of neighborhood names in one API call."""
    if not ANTHROPIC_API_KEY or not names:
        return {}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        names_list = "\n".join(f"- {n}" for n in names[:50])

        response = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=2000,
            messages=[{"role": "user", "content": (
                f"Normalize estes nomes de bairros de Marília-SP para a forma padrão oficial. "
                f"Corrija abreviações (Jd.→Jardim, Pq.→Parque, Res.→Residencial, Vl.→Vila, "
                f"N.H.→Núcleo Habitacional), erros de digitação, e casing.\n\n"
                f"Retorne APENAS um JSON: {{\"original\": \"normalizado\", ...}}\n\n"
                f"Bairros:\n{names_list}"
            )}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]

        return json.loads(text)

    except Exception:
        logger.debug("[llm] Batch normalize failed", exc_info=True)
        return {}

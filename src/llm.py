"""LLM helpers — Google Gemini API integration for enrichment tasks."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = "gemini-2.0-flash-lite"

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _generate(prompt: str, max_tokens: int = 1000) -> Optional[str]:
    """Call Gemini and return the text response."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google.genai import types

        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=0.2,
            ),
        )
        # Extract text — try .text first, then parts
        if response.text:
            return response.text.strip()
        if response.candidates:
            parts = response.candidates[0].content.parts
            text = "".join(p.text for p in parts if hasattr(p, "text") and p.text)
            return text.strip() if text else None
        return None
    except Exception:
        logger.debug("[llm] Gemini call failed", exc_info=True)
        return None


def _parse_json(text: str) -> Optional[dict[str, Any]]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    if not text:
        return None
    # Strip markdown code blocks
    if "```" in text:
        lines = text.split("\n")
        clean = []
        inside = False
        for line in lines:
            if line.strip().startswith("```"):
                inside = not inside
                continue
            if inside or not text.startswith("```"):
                clean.append(line)
        text = "\n".join(clean) if clean else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON within text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return None


def extract_listing_attributes(description: str, title: str = "") -> Optional[dict[str, Any]]:
    """Extract structured attributes from a listing description.

    Returns dict with: neighborhood_normalized, infrastructure, nearby_amenities, etc.
    """
    if not description or len(description.strip()) < 20:
        return None

    prompt = f"""Analise este anúncio imobiliário de Marília-SP e extraia atributos estruturados.

Título: {title}
Descrição: {description[:1500]}

Retorne APENAS um JSON válido com estes campos:
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

    text = _generate(prompt, max_tokens=2000)
    return _parse_json(text)


def batch_normalize_neighborhoods(names: list[str]) -> dict[str, str]:
    """Normalize a batch of neighborhood names in one API call."""
    if not names:
        return {}

    names_list = "\n".join(f"- {n}" for n in names[:50])

    prompt = (
        f"Normalize estes nomes de bairros de Marília-SP para a forma padrão oficial. "
        f"Corrija abreviações (Jd.→Jardim, Pq.→Parque, Res.→Residencial, Vl.→Vila, "
        f"N.H.→Núcleo Habitacional), erros de digitação, e casing.\n\n"
        f"Retorne APENAS um JSON: {{\"original\": \"normalizado\", ...}}\n\n"
        f"Bairros:\n{names_list}"
    )

    text = _generate(prompt, max_tokens=2000)
    result = _parse_json(text)
    return result if isinstance(result, dict) else {}


def generate_market_report(data: dict[str, Any]) -> Optional[str]:
    """Generate a weekly market report in Portuguese."""
    prompt = (
        "Voce e um analista imobiliario especialista em Marilia-SP. "
        "Gere um resumo executivo COMPLETO para um construtor que quer comprar terrenos para MCMV. "
        "3 secoes obrigatorias:\n\n"
        "TENDENCIAS: O que mudou nos precos? Quais bairros se destacaram?\n"
        "OPORTUNIDADES: Quais os 3 melhores terrenos disponiveis?\n"
        "RECOMENDACAO: Comprar agora ou esperar? Qual bairro focar?\n\n"
        f"Dados: {json.dumps(data, ensure_ascii=False)[:2500]}\n\n"
        "REGRAS: Sem markdown. Sem asteriscos. Sem bullet points. "
        "Texto corrido em portugues informal. Maximo 600 palavras. "
        "Comece direto pela analise, sem introducao."
    )

    return _generate(prompt, max_tokens=8000)


def score_opportunity(listing_data: dict[str, Any], numeric_score: float) -> Optional[dict[str, Any]]:
    """Get LLM second opinion on a land opportunity."""
    prompt = f"""Avalie este terreno para construção MCMV em Marília-SP:

Preço: R$ {listing_data.get('sale_price', '?')}
Área: {listing_data.get('total_area', '?')} m²
Bairro: {listing_data.get('neighborhood', '?')}
Infraestrutura: {listing_data.get('infra', '?')}
Proximidades: {listing_data.get('proximidades', '?')}
Score numérico: {numeric_score:.0f}/100

Dê uma nota de 0 a 10 para potencial de investimento e justifique em 1 frase curta.
Retorne JSON: {{"nota": N, "justificativa": "..."}}"""

    text = _generate(prompt, max_tokens=2000)
    return _parse_json(text)


def assess_risk(listing_data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Assess risks for a land opportunity."""
    prompt = (
        f"Terreno em {listing_data.get('neighborhood', '?')}, Marília-SP. "
        f"Zoneamento: {listing_data.get('zoning', '?')}. "
        f"Infra: {listing_data.get('infra', '?')}. "
        f"Terreno: {listing_data.get('terrain', '?')}. "
        f"Classifique riscos de 1-5. Retorne APENAS JSON curto: "
        f"{{\"zoneamento\":N,\"ambiental\":N,\"infra\":N,\"legal\":N,\"mercado\":N,\"resumo\":\"max 10 palavras\"}}"
    )

    text = _generate(prompt, max_tokens=4000)
    result = _parse_json(text)
    if not result:
        return None
    return {
        "risco_zoneamento": result.get("zoneamento", result.get("risco_zoneamento", 0)),
        "risco_ambiental": result.get("ambiental", result.get("risco_ambiental", 0)),
        "risco_infraestrutura": result.get("infra", result.get("risco_infraestrutura", 0)),
        "risco_legal": result.get("legal", result.get("risco_legal", 0)),
        "risco_mercado": result.get("mercado", result.get("risco_mercado", 0)),
        "resumo": result.get("resumo", ""),
    }

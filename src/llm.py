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
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

VERTEX_PROJECT = os.getenv("VERTEX_PROJECT", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
USE_VERTEX = bool(VERTEX_PROJECT)

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        if USE_VERTEX:
            _client = genai.Client(
                vertexai=True,
                project=VERTEX_PROJECT,
                location=VERTEX_LOCATION,
            )
            logger.info(f"[llm] Usando Vertex AI (project={VERTEX_PROJECT})")
        else:
            _client = genai.Client(api_key=GEMINI_API_KEY)
            logger.debug("[llm] Usando AI Studio (sem DPA — apenas dev local)")
    return _client


def _record_usage(model: str, task: str, response: Any) -> None:
    """Registra tokens/custo da chamada na telemetria. Nunca quebra o fluxo."""
    try:
        from src.llm_usage import record_llm_usage
        record_llm_usage(model, task, response, llm_mode=get_llm_mode())
    except Exception:
        logger.debug("[llm] Falha ao registrar telemetria de uso", exc_info=True)


def _generate(
    prompt: str,
    max_tokens: int = 1000,
    thinking: bool = False,
    task: str = "generate",
) -> Optional[str]:
    """Call Gemini and return the text response.

    `thinking=False` (default) disables Gemini 2.5 reasoning tokens — big cost cut for
    structured-output batch tasks. Set True only when answer quality needs reasoning.
    `task` rotula a chamada na telemetria de custo (tabela llm_usage).
    """
    if not GEMINI_API_KEY:
        return None
    try:
        from google.genai import types

        client = _get_client()
        cfg_kwargs: dict[str, Any] = {
            "max_output_tokens": max_tokens,
            "temperature": 0.2,
        }
        if not thinking:
            try:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                # SDK older than thinking support — ignore silently
                pass

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        _record_usage(MODEL, task, response)
        # Extract text — try .text first, then parts
        if response.text:
            return response.text.strip()
        if response.candidates:
            parts = response.candidates[0].content.parts
            text = "".join(p.text for p in parts if hasattr(p, "text") and p.text)
            return text.strip() if text else None
        return None
    except Exception:
        logger.warning("[llm] Gemini call failed", exc_info=True)
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

    text = _generate(prompt, max_tokens=800, task="extract_attributes")
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

    text = _generate(prompt, max_tokens=1500, task="normalize_neighborhoods")
    result = _parse_json(text)
    return result if isinstance(result, dict) else {}


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

    text = _generate(prompt, max_tokens=200, task="score_opportunity")
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

    text = _generate(prompt, max_tokens=300, task="assess_risk")
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


def generate_vision(
    prompt: str, image_bytes: bytes, max_tokens: int = 1000, task: str = "vision"
) -> Optional[str]:
    """Call Gemini Vision with prompt + image bytes. Returns raw text response.

    Uses the same client/protections as `_generate`. Returns None if GEMINI_API_KEY
    is missing or the call fails.
    """
    if not GEMINI_API_KEY:
        return None
    if not image_bytes:
        return None
    try:
        from google.genai import types

        client = _get_client()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")

        cfg_kwargs: dict[str, Any] = {
            "max_output_tokens": max_tokens,
            "temperature": 0.2,
        }
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass

        response = client.models.generate_content(
            model=MODEL,
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        _record_usage(MODEL, task, response)
        if response.text:
            return response.text.strip()
        if response.candidates:
            parts = response.candidates[0].content.parts
            text = "".join(p.text for p in parts if hasattr(p, "text") and p.text)
            return text.strip() if text else None
        return None
    except Exception:
        logger.warning("[llm] Gemini vision call failed", exc_info=True)
        return None


def get_llm_mode() -> str:
    """Retorna 'vertex_ai' ou 'ai_studio' — para audit log."""
    return "vertex_ai" if USE_VERTEX else "ai_studio"

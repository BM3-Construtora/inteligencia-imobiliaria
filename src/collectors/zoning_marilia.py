"""Collector — zoneamento do Plano Diretor de Marília-SP.

Baixa o PDF do plano diretor (PLANO_DIRETOR_PDF_URL), extrai texto com pdfplumber
e usa Gemini para estruturar zonas urbanas. Upserta em `zoning_zones`.

Fallback: se PDF indisponível ou pdfplumber não instalado, popula 5 zonas comuns
de Marília-SP via dict hardcoded — substituir quando scraping real rodar.

TODO: integrar shapefile do GeoMaps Marília para `geom_wkt` + `get_zone_for_coords`.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import httpx

from src.db import get_client
from src.llm import _generate, _parse_json

logger = logging.getLogger(__name__)


# Fallback hardcoded — zoneamento comum de Marília-SP até parsing real do PDF.
# Valores aproximados baseados na Lei Complementar 753/2017 (Plano Diretor).
FALLBACK_ZONES: list[dict[str, Any]] = [
    {
        "zone_code": "ZR1",
        "zone_name": "Zona Residencial 1 (baixa densidade)",
        "allowed_uses": ["residencial"],
        "min_lot_area_m2": 250,
        "max_height_m": 9.0,
        "max_coverage_pct": 50,
        "max_far": 1.0,
        "description": "Bairros residenciais consolidados, uso predominante unifamiliar. Fallback hardcoded.",
    },
    {
        "zone_code": "ZR2",
        "zone_name": "Zona Residencial 2 (média densidade)",
        "allowed_uses": ["residencial", "misto"],
        "min_lot_area_m2": 200,
        "max_height_m": 15.0,
        "max_coverage_pct": 60,
        "max_far": 2.0,
        "description": "Residencial com pequeno comércio de bairro permitido. Fallback hardcoded.",
    },
    {
        "zone_code": "ZM",
        "zone_name": "Zona Mista",
        "allowed_uses": ["residencial", "comercial", "misto"],
        "min_lot_area_m2": 200,
        "max_height_m": 25.0,
        "max_coverage_pct": 70,
        "max_far": 3.0,
        "description": "Corredores e eixos viários — uso misto residencial + comercial. Fallback hardcoded.",
    },
    {
        "zone_code": "ZC",
        "zone_name": "Zona Central",
        "allowed_uses": ["comercial", "misto", "servicos"],
        "min_lot_area_m2": 150,
        "max_height_m": 40.0,
        "max_coverage_pct": 80,
        "max_far": 4.0,
        "description": "Centro urbano principal — comércio e serviços. Fallback hardcoded.",
    },
    {
        "zone_code": "ZE",
        "zone_name": "Zona Especial / Industrial",
        "allowed_uses": ["industrial", "comercial"],
        "min_lot_area_m2": 500,
        "max_height_m": 20.0,
        "max_coverage_pct": 70,
        "max_far": 2.0,
        "description": "Distritos industriais e empresariais. NÃO permite residencial. Fallback hardcoded.",
    },
]


def _upsert_zone(zone: dict[str, Any], source_url: Optional[str] = None) -> bool:
    """Upsert single zone on `zoning_zones` por zone_code."""
    db = get_client()
    payload = {
        "zone_code": zone["zone_code"],
        "zone_name": zone.get("zone_name"),
        "allowed_uses": zone.get("allowed_uses") or [],
        "min_lot_area_m2": zone.get("min_lot_area_m2"),
        "max_height_m": zone.get("max_height_m"),
        "max_coverage_pct": zone.get("max_coverage_pct"),
        "max_far": zone.get("max_far"),
        "description": zone.get("description"),
        "source_doc_url": source_url,
    }
    try:
        db.table("zoning_zones").upsert(
            payload, on_conflict="zone_code"
        ).execute()
        return True
    except Exception:
        logger.warning(
            f"[zoning] upsert failed for {zone.get('zone_code')}", exc_info=True
        )
        return False


def _seed_fallback() -> int:
    """Popula zoning_zones com fallback hardcoded — só se tabela vazia/parcial."""
    count = 0
    for zone in FALLBACK_ZONES:
        if _upsert_zone(zone, source_url=None):
            count += 1
    logger.info(f"[zoning] Fallback seed: {count}/{len(FALLBACK_ZONES)} zones upserted")
    return count


def _download_pdf(url: str) -> Optional[bytes]:
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as c:
            resp = c.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception:
        logger.warning(f"[zoning] PDF download failed: {url}", exc_info=True)
        return None


def _extract_pdf_text(pdf_bytes: bytes) -> Optional[list[str]]:
    """Extrai texto por página do PDF. Returns None se pdfplumber indisponível."""
    try:
        import io

        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning("[zoning] pdfplumber não instalado — pulando parsing do PDF")
        return None

    try:
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    pages.append(txt)
        return pages
    except Exception:
        logger.warning("[zoning] erro extraindo PDF", exc_info=True)
        return None


def _llm_extract_zones(section: str) -> list[dict[str, Any]]:
    """Pede ao Gemini que estruture zonas urbanas a partir de uma seção do PDF."""
    prompt = f"""Você está lendo o plano diretor de Marília-SP. Extraia zonas urbanas mencionadas.

Texto:
\"\"\"{section[:3500]}\"\"\"

Retorne APENAS JSON (lista). Cada item:
{{
  "zone_code": "ex: ZR1, ZM, ZC, ZI",
  "zone_name": "nome completo",
  "allowed_uses": ["residencial", "comercial", "misto", "industrial", "servicos"],
  "min_lot_area_m2": número ou null,
  "max_height_m": número ou null,
  "max_coverage_pct": número (0-100) ou null,
  "max_far": número (coef. aproveitamento) ou null,
  "description": "1 frase curta"
}}

Se não houver zonas claras nessa seção, retorne []."""

    text = _generate(prompt, max_tokens=1500)
    if not text:
        return []
    # Tenta parsear como lista
    try:
        # _parse_json é dict-only; manual:
        cleaned = text
        if "```" in cleaned:
            # remove fences
            parts = cleaned.split("```")
            # pega o maior bloco entre fences
            cleaned = max(parts, key=len)
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start >= 0 and end > start:
            data = json.loads(cleaned[start:end])
            return data if isinstance(data, list) else []
    except Exception:
        logger.debug("[zoning] LLM JSON parse failed", exc_info=True)
    return []


def parse_plano_diretor(pdf_url: str | None = None) -> int:
    """Baixa PDF do plano diretor, extrai zonas via Gemini, upserta em zoning_zones.

    Args:
        pdf_url: URL do PDF. Default lê env PLANO_DIRETOR_PDF_URL.

    Returns:
        Número de zonas upserted. Se PDF indisponível, faz fallback hardcoded.
    """
    pdf_url = pdf_url or os.getenv("PLANO_DIRETOR_PDF_URL")
    if not pdf_url:
        logger.warning(
            "[zoning] PLANO_DIRETOR_PDF_URL não definido — usando fallback hardcoded"
        )
        return _seed_fallback()

    pdf_bytes = _download_pdf(pdf_url)
    if not pdf_bytes:
        return _seed_fallback()

    pages = _extract_pdf_text(pdf_bytes)
    if pages is None:
        # pdfplumber faltando
        return _seed_fallback()

    if not pages:
        logger.warning("[zoning] PDF sem texto extraível — fallback")
        return _seed_fallback()

    # Concatena páginas em "seções" ~ 3 páginas cada pra reduzir chamadas LLM
    upserted = 0
    seen_codes: set[str] = set()
    chunk_size = 3
    for i in range(0, len(pages), chunk_size):
        section = "\n\n".join(pages[i:i + chunk_size])
        zones = _llm_extract_zones(section)
        for z in zones:
            code = (z.get("zone_code") or "").strip().upper()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            z["zone_code"] = code
            if _upsert_zone(z, source_url=pdf_url):
                upserted += 1

    if upserted == 0:
        logger.warning("[zoning] LLM não retornou zonas — fallback")
        return _seed_fallback()

    logger.info(f"[zoning] {upserted} zones upserted from PDF {pdf_url}")
    return upserted


def get_zone_for_coords(lat: float, lng: float) -> Optional[dict[str, Any]]:
    """Resolve qual zona urbana cobre as coordenadas dadas.

    TODO: requer shapefile do plano diretor com geometria das zonas.
    Hoje retorna None — bloco preparado para futura integração PostGIS / shapely.

    Args:
        lat: latitude WGS84.
        lng: longitude WGS84.

    Returns:
        dict com colunas de `zoning_zones` ou None se sem dados.
    """
    _ = (lat, lng)  # silenciar lint até implementação
    return None

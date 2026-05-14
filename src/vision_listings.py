"""Vision de fotos de anúncios — analisa imagens dos listings via Gemini Vision.

Complementa vision.py (que analisa satélite do lote) com análise das fotos
internas/externas do imóvel publicadas nos portais.

Extrai: score de conservação (0-10), acabamento, cômodos, problemas visíveis.
Preenche: listings.vision_conservation_score, vision_acabamento, vision_reformado,
          vision_problemas, vision_fotos_analisadas + tabela listing_vision_details.

Criado por sql/050_heritage_vision.sql.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client
from src.llm import _get_client as _get_llm_client, _parse_json

logger = logging.getLogger(__name__)

MAX_FOTOS_PER_LISTING = 4
SLEEP_BETWEEN_LISTINGS = 1.5
GEMINI_VISION_MODEL = "gemini-2.0-flash"

LISTING_VISION_PROMPT = """Você é um vistoriador imobiliário experiente analisando fotos de um imóvel em Marília-SP.

Analise a imagem e retorne APENAS um JSON válido (sem markdown):

{
  "conservation": <0-10>,
  "acabamento": "basico | medio | alto | luxo",
  "reformado": true | false,
  "comodos": ["sala", "quarto", "banheiro", "cozinha", "area_servico", "garagem", "externo"],
  "problemas": ["umidade", "rachadura", "pintura_velha", "mofo", "piso_danificado", "telhado_ruim", "infiltracao"],
  "pontos_positivos": ["bem_conservado", "luminoso", "novo", "reformado_recente", "acabamento_fino"],
  "observacao": "uma frase curta objetiva"
}

Critérios de conservation:
9-10: Imóvel novo ou completamente reformado, acabamento excelente
7-8: Bom estado, bem conservado, possíveis pequenos reparos
5-6: Estado mediano, precisa de pintura e pequenas reformas
3-4: Problemas visíveis (umidade, rachaduras), reforma significativa necessária
1-2: Mau estado, reformas extensas ou demolição necessária

Seja objetivo e conservador. Retorne lista vazia se não identificar problemas/pontos positivos."""


def run_vision_listings(limit: int = 100) -> dict[str, int]:
    """Analisa fotos de listings via Gemini Vision."""
    stats = {"listings_analyzed": 0, "photos_analyzed": 0, "failed": 0, "skipped": 0}
    db = get_client()

    listings = _fetch_listings_with_photos(db, limit)
    if not listings:
        logger.info("[vision_listings] Nenhum listing com fotos para analisar")
        return stats

    logger.info(f"[vision_listings] Analisando {len(listings)} listings")

    for listing in listings:
        try:
            result = _analyze_listing(listing)
            if result is None:
                stats["skipped"] += 1
                continue
            _save_result(db, listing["id"], result)
            stats["listings_analyzed"] += 1
            stats["photos_analyzed"] += result.get("fotos_analisadas", 0)
            time.sleep(SLEEP_BETWEEN_LISTINGS)
        except Exception:
            stats["failed"] += 1
            logger.exception(f"[vision_listings] Falhou listing {listing.get('id')}")

    logger.info(
        f"[vision_listings] Done: analyzed={stats['listings_analyzed']} "
        f"photos={stats['photos_analyzed']} failed={stats['failed']}"
    )
    return stats


def _fetch_listings_with_photos(db: Any, limit: int) -> list[dict]:
    try:
        result = (
            db.table("listings")
            .select("id, neighborhood, property_type, raw_payload, vision_listing_analyzed_at")
            .eq("is_active", True)
            .is_("vision_listing_analyzed_at", "null")
            .not_.is_("raw_payload", "null")
            .limit(limit)
            .execute()
        )
        # Filtrar apenas listings com fotos no raw_payload
        listings_with_photos = []
        for row in result.data or []:
            photos = _extract_photo_urls(row.get("raw_payload") or {})
            if photos:
                row["_photos"] = photos
                listings_with_photos.append(row)
        return listings_with_photos
    except Exception:
        logger.exception("[vision_listings] Falhou ao buscar listings")
        return []


def _extract_photo_urls(raw_payload: dict) -> list[str]:
    """Extrai URLs de fotos do raw_payload de portais diferentes."""
    urls: list[str] = []
    for key in ("photos", "images", "fotos", "imagens", "gallery", "galeria", "media"):
        val = raw_payload.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.startswith("http"):
                    urls.append(item)
                elif isinstance(item, dict):
                    url = item.get("url") or item.get("src") or item.get("link") or ""
                    if url and url.startswith("http"):
                        urls.append(url)
    return urls[:MAX_FOTOS_PER_LISTING]


def _analyze_listing(listing: dict) -> dict[str, Any] | None:
    photos = listing.get("_photos") or []
    if not photos:
        return None

    client = _get_llm_client()
    all_results: list[dict] = []

    for i, url in enumerate(photos[:MAX_FOTOS_PER_LISTING]):
        image_bytes = _fetch_image(url)
        if not image_bytes:
            continue
        result = _call_gemini_vision(client, image_bytes, url)
        if result:
            result["foto_url"] = url
            result["foto_index"] = i
            all_results.append(result)

    if not all_results:
        return None

    # Agregar resultados das múltiplas fotos
    scores = [r["conservation"] for r in all_results if r.get("conservation") is not None]
    avg_conservation = sum(scores) / len(scores) if scores else None

    # Problemas e pontos positivos: union de todas as fotos
    all_problemas: set[str] = set()
    all_positivos: set[str] = set()
    acabamentos: list[str] = []
    reformado_flags: list[bool] = []
    comodos: set[str] = set()

    for r in all_results:
        all_problemas.update(r.get("problemas") or [])
        all_positivos.update(r.get("pontos_positivos") or [])
        if r.get("acabamento"):
            acabamentos.append(r["acabamento"])
        if r.get("reformado") is not None:
            reformado_flags.append(r["reformado"])
        comodos.update(r.get("comodos") or [])

    # Acabamento: mais conservador (menor) entre as fotos
    acabamento_order = {"basico": 0, "medio": 1, "alto": 2, "luxo": 3}
    acabamento_final = min(acabamentos, key=lambda x: acabamento_order.get(x, 1)) if acabamentos else "medio"

    reformado = any(reformado_flags) if reformado_flags else False

    return {
        "conservation_score": round(avg_conservation, 1) if avg_conservation else None,
        "acabamento": acabamento_final,
        "reformado": reformado,
        "problemas": sorted(all_problemas),
        "comodos": sorted(comodos),
        "fotos_analisadas": len(all_results),
        "photo_details": all_results,
    }


def _call_gemini_vision(client: Any, image_bytes: bytes, url: str) -> dict | None:
    try:
        from google.genai import types
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=_guess_mime(url),
        )
        response = client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[LISTING_VISION_PROMPT, image_part],
            config=types.GenerateContentConfig(
                max_output_tokens=400,
                temperature=0.1,
            ),
        )
        text = response.text or ""
        data = _parse_json(text)
        if not data:
            return None
        # Validar e sanitizar
        conservation = data.get("conservation")
        if conservation is not None:
            try:
                conservation = max(0.0, min(10.0, float(conservation)))
            except (ValueError, TypeError):
                conservation = None
        return {
            "conservation": conservation,
            "acabamento": data.get("acabamento", "medio"),
            "reformado": bool(data.get("reformado", False)),
            "comodos": [c for c in (data.get("comodos") or []) if isinstance(c, str)],
            "problemas": [p for p in (data.get("problemas") or []) if isinstance(p, str)],
            "pontos_positivos": [p for p in (data.get("pontos_positivos") or []) if isinstance(p, str)],
            "observacao": str(data.get("observacao", ""))[:300],
        }
    except Exception:
        logger.warning(f"[vision_listings] Gemini call falhou para {url}")
        return None


def _fetch_image(url: str) -> bytes | None:
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200 or len(resp.content) < 1000:
                return None
            return resp.content
    except Exception:
        logger.debug(f"[vision_listings] fetch falhou: {url}")
        return None


def _guess_mime(url: str) -> str:
    url_lower = url.lower()
    if ".png" in url_lower:
        return "image/png"
    if ".webp" in url_lower:
        return "image/webp"
    return "image/jpeg"


def _save_result(db: Any, listing_id: int, result: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()

    # Atualiza listing principal
    db.table("listings").update({
        "vision_conservation_score": result.get("conservation_score"),
        "vision_acabamento": result.get("acabamento"),
        "vision_reformado": result.get("reformado"),
        "vision_problemas": result.get("problemas") or [],
        "vision_fotos_analisadas": result.get("fotos_analisadas", 0),
        "vision_listing_analyzed_at": now,
    }).eq("id", listing_id).execute()

    # Detalhe por foto
    for detail in result.get("photo_details") or []:
        try:
            db.table("listing_vision_details").upsert({
                "listing_id": listing_id,
                "foto_url": detail["foto_url"],
                "foto_index": detail["foto_index"],
                "conservation": detail.get("conservation"),
                "acabamento": detail.get("acabamento"),
                "comodos": detail.get("comodos") or [],
                "problemas": detail.get("problemas") or [],
                "pontos_positivos": detail.get("pontos_positivos") or [],
                "raw_response": detail,
                "analyzed_at": now,
                "model": GEMINI_VISION_MODEL,
            }, on_conflict="listing_id,foto_url").execute()
        except Exception:
            logger.debug(f"[vision_listings] detalhe foto falhou listing {listing_id}")

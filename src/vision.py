"""Computer Vision Extractor — Track F do MaríliaBot.

Para cada listing com coordenadas, baixa imagem satélite via Google Static Maps,
manda pro Gemini Vision e extrai features visuais estruturadas (topografia,
vegetação, vizinhança construída, etc). Resultado vira `vision_score` 0-10 que
o Hunter usa como feature adicional.

# ============ HUNTER INTEGRATION ============
# Em src/hunter.py, dentro de _score_listing, adicione (depois de breakdown["stale_bonus"]):
#   try:
#     v = db.table("vision_features").select("vision_score").eq("listing_id", listing["id"]).limit(1).execute()
#     if v.data and v.data[0].get("vision_score") is not None:
#         breakdown["vision"] = round(float(v.data[0]["vision_score"]), 1)
#     else:
#         breakdown["vision"] = 0
#   except Exception:
#     breakdown["vision"] = 0
# NOTE: isso adiciona até 10pts ao raw_total — recalibrar pesos se necessario.
# =============================================
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from src.config import GOOGLE_MAPS_KEY
from src.db import get_client
from src.llm import generate_vision, _parse_json  # type: ignore

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/mariliabot_satellite")
STATIC_MAPS_URL = "https://maps.googleapis.com/maps/api/staticmap"
DEFAULT_ZOOM = 19
IMAGE_SIZE = "640x640"


def _build_image_url(lat: float, lng: float, zoom: int, with_key: bool = False) -> str:
    """Monta URL Static Maps. with_key=False omite a chave (versão para storage)."""
    base = (
        f"{STATIC_MAPS_URL}?center={lat},{lng}&zoom={zoom}"
        f"&size={IMAGE_SIZE}&maptype=satellite"
    )
    if with_key and GOOGLE_MAPS_KEY:
        base += f"&key={GOOGLE_MAPS_KEY}"
    return base


def _image_cache_key(lat: float, lng: float, zoom: int) -> str:
    raw = f"{round(lat, 6)},{round(lng, 6)},{zoom}".encode()
    return hashlib.sha256(raw).hexdigest()


def fetch_satellite_image(
    lat: float, lng: float, zoom: int = DEFAULT_ZOOM
) -> Optional[bytes]:
    """Baixa imagem satélite via Google Static Maps API. Cache local em /tmp.

    Retorna bytes da imagem PNG ou None (sem key / falha de rede).
    """
    if not GOOGLE_MAPS_KEY:
        logger.warning("[vision] GOOGLE_MAPS_KEY ausente — pulando fetch")
        return None

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.warning("[vision] Falha ao criar cache dir", exc_info=True)

    cache_key = _image_cache_key(lat, lng, zoom)
    cache_path = CACHE_DIR / f"{cache_key}.png"

    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except Exception:
            logger.warning("[vision] Falha ao ler cache %s", cache_path, exc_info=True)

    url = _build_image_url(lat, lng, zoom, with_key=True)
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            logger.warning(
                "[vision] Static Maps status=%s para (%s,%s)", resp.status_code, lat, lng
            )
            return None
        data = resp.content
        if not data or len(data) < 1000:
            return None
        try:
            cache_path.write_bytes(data)
        except Exception:
            pass
        return data
    except Exception:
        logger.warning("[vision] Erro fetch satélite (%s,%s)", lat, lng, exc_info=True)
        return None


VISION_PROMPT = """Você é um especialista em avaliação de terrenos urbanos para construção (MCMV)
analisando uma imagem de satélite (zoom alto) de um lote em Marília-SP.

Analise a imagem e retorne APENAS um JSON válido (sem markdown) com estes campos:

{
  "topography": "plano | aclive_suave | aclive_acentuado | declive_suave | declive_acentuado | irregular | unknown",
  "vegetation_pct": 0-100,  // % aproximado da área coberta por mato/vegetação
  "paved_access": true | false,  // rua de acesso é asfaltada?
  "sidewalk_present": true | false,  // tem calçada visível?
  "drainage_visible": true | false,  // bocas de lobo / guias / drenagem visíveis?
  "neighbors_built_pct": 0-100,  // % de lotes vizinhos no entorno visível JÁ construídos
  "lot_shape": "regular | irregular | esquina | encravado | unknown",
  "visible_obstacles": ["postes", "transformador", "arvore_grande", "torre", ...],  // lista, pode ser vazia
  "socioeconomic_signal": "baixo | medio_baixo | medio | medio_alto | alto | unknown",  // padrão das construções vizinhas
  "raw_observations": "1-2 frases curtas com observações relevantes para compra"
}

Se não conseguir inferir, use "unknown" / null / [] conforme o tipo. Seja conservador.
Não invente dados que não conseguir ver.
"""

_TOPOGRAPHY_VALID = {
    "plano", "aclive_suave", "aclive_acentuado",
    "declive_suave", "declive_acentuado", "irregular", "unknown",
}
_LOT_SHAPE_VALID = {"regular", "irregular", "esquina", "encravado", "unknown"}
_SOCIO_VALID = {"baixo", "medio_baixo", "medio", "medio_alto", "alto", "unknown"}


def _clamp_pct(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f < 0:
        return 0.0
    if f > 100:
        return 100.0
    return round(f, 2)


def _enum(value: Any, valid: set[str]) -> str:
    if isinstance(value, str) and value in valid:
        return value
    return "unknown"


def analyze_image(image_bytes: bytes) -> Optional[dict[str, Any]]:
    """Chama Gemini Vision e devolve dict estruturado de features."""
    if not image_bytes:
        return None

    raw_text = generate_vision(VISION_PROMPT, image_bytes, max_tokens=800)
    if not raw_text:
        return None

    parsed = _parse_json(raw_text)
    if not isinstance(parsed, dict):
        return None

    obstacles = parsed.get("visible_obstacles") or []
    if not isinstance(obstacles, list):
        obstacles = []
    obstacles = [str(o).strip().lower() for o in obstacles if o]

    return {
        "topography": _enum(parsed.get("topography"), _TOPOGRAPHY_VALID),
        "vegetation_pct": _clamp_pct(parsed.get("vegetation_pct")),
        "paved_access": _coerce_bool(parsed.get("paved_access")),
        "sidewalk_present": _coerce_bool(parsed.get("sidewalk_present")),
        "drainage_visible": _coerce_bool(parsed.get("drainage_visible")),
        "neighbors_built_pct": _clamp_pct(parsed.get("neighbors_built_pct")),
        "lot_shape": _enum(parsed.get("lot_shape"), _LOT_SHAPE_VALID),
        "visible_obstacles": obstacles,
        "socioeconomic_signal": _enum(parsed.get("socioeconomic_signal"), _SOCIO_VALID),
        "raw_observations": str(parsed.get("raw_observations") or "")[:500],
        "_raw": parsed,
    }


def _coerce_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "sim", "yes", "1"):
            return True
        if s in ("false", "nao", "não", "no", "0"):
            return False
    return None


def compute_vision_score(features: dict[str, Any]) -> float:
    """Score composto 0-10 a partir das features extraídas."""
    if not features:
        return 0.0

    score = 0.0

    topo = features.get("topography")
    if topo == "plano":
        score += 2.0
    if topo in ("aclive_acentuado", "declive_acentuado", "irregular"):
        score -= 2.0

    veg = features.get("vegetation_pct")
    if veg is not None and 5 <= veg <= 30:
        score += 1.0

    if features.get("paved_access"):
        score += 1.0
    if features.get("sidewalk_present"):
        score += 0.5
    if features.get("drainage_visible"):
        score += 1.0

    nb = features.get("neighbors_built_pct")
    if nb is not None and nb >= 50:
        score += 2.0

    if features.get("lot_shape") == "regular":
        score += 1.0

    if features.get("socioeconomic_signal") in ("medio", "medio_alto"):
        score += 1.0

    obstacles = features.get("visible_obstacles") or []
    if any("transformador" in o for o in obstacles):
        score -= 1.0

    # Clamp 0-10
    if score < 0:
        return 0.0
    if score > 10:
        return 10.0
    return round(score, 2)


def _fetch_candidate_listings(db: Any, limit: int) -> list[dict[str, Any]]:
    """Lista listings ativos com coords sem vision_features.

    Prioriza listings que aparecem em opportunities com score >= 60.
    """
    # IDs já processados
    existing = db.table("vision_features").select("listing_id").execute()
    existing_ids = {r["listing_id"] for r in (existing.data or [])}

    # Top opportunities primeiro
    top_ids: list[int] = []
    try:
        opp = (
            db.table("opportunities")
            .select("listing_id, score")
            .gte("score", 60)
            .order("score", desc=True)
            .limit(limit * 3)
            .execute()
        )
        top_ids = [
            r["listing_id"]
            for r in (opp.data or [])
            if r.get("listing_id") and r["listing_id"] not in existing_ids
        ]
    except Exception:
        logger.warning("[vision] Falha ao buscar opportunities", exc_info=True)

    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _add(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            lid = row.get("id")
            if not lid or lid in seen or lid in existing_ids:
                continue
            if row.get("latitude") is None or row.get("longitude") is None:
                continue
            seen.add(lid)
            candidates.append(row)
            if len(candidates) >= limit:
                return

    # Fase 1: top opportunities
    if top_ids:
        try:
            chunk = (
                db.table("listings")
                .select("id, latitude, longitude, is_active")
                .in_("id", top_ids[: limit * 2])
                .eq("is_active", True)
                .execute()
            )
            _add(chunk.data or [])
        except Exception:
            logger.warning("[vision] Falha ao puxar top listings", exc_info=True)

    # Fase 2: fallback — qualquer listing ativo com coords
    if len(candidates) < limit:
        remaining = limit - len(candidates)
        try:
            fallback = (
                db.table("listings")
                .select("id, latitude, longitude, is_active")
                .eq("is_active", True)
                .not_.is_("latitude", "null")
                .not_.is_("longitude", "null")
                .limit(remaining * 5)
                .execute()
            )
            _add(fallback.data or [])
        except Exception:
            logger.warning("[vision] Falha fallback listings", exc_info=True)

    return candidates[:limit]


def _finish_run(
    db: Any,
    run_id: Optional[int],
    status: str,
    stats: dict[str, int],
    error: Optional[str] = None,
) -> None:
    if not run_id:
        return
    update = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats.get("processed", 0),
        "items_created": stats.get("extracted", 0),
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.warning("[vision] Falha ao finalizar agent_run", exc_info=True)


def run_vision_extractor(limit: int = 50) -> dict[str, int]:
    """Extrai features visuais para até `limit` listings sem vision_features."""
    stats = {"processed": 0, "extracted": 0, "failed": 0, "skipped_no_coords": 0}

    # Pré-checagem: precisa das duas keys; sem isso retorna zerado.
    from src.llm import GEMINI_API_KEY  # import tardio p/ refletir env

    if not GOOGLE_MAPS_KEY or not GEMINI_API_KEY:
        logger.warning(
            "[vision] Chaves ausentes (GOOGLE_MAPS_KEY=%s, GEMINI_API_KEY=%s) — abortando",
            bool(GOOGLE_MAPS_KEY), bool(GEMINI_API_KEY),
        )
        return stats

    db = get_client()

    run_id: Optional[int] = None
    try:
        run_result = (
            db.table("agent_runs")
            .insert({"agent_name": "vision_extractor", "status": "running"})
            .execute()
        )
        run_id = run_result.data[0]["id"] if run_result.data else None
    except Exception:
        logger.warning("[vision] Falha ao criar agent_run", exc_info=True)

    try:
        candidates = _fetch_candidate_listings(db, limit)
        logger.info("[vision] %s listings candidatos", len(candidates))

        for listing in candidates:
            stats["processed"] += 1
            lid = listing["id"]
            lat = listing.get("latitude")
            lng = listing.get("longitude")

            if lat is None or lng is None:
                stats["skipped_no_coords"] += 1
                continue

            try:
                lat_f = float(lat)
                lng_f = float(lng)
            except (TypeError, ValueError):
                stats["skipped_no_coords"] += 1
                continue

            try:
                image = fetch_satellite_image(lat_f, lng_f, DEFAULT_ZOOM)
                if not image:
                    stats["failed"] += 1
                    continue

                features = analyze_image(image)
                if not features:
                    stats["failed"] += 1
                    continue

                score = compute_vision_score(features)
                image_hash = hashlib.sha256(image).hexdigest()

                row = {
                    "listing_id": lid,
                    "latitude": lat_f,
                    "longitude": lng_f,
                    "image_url": _build_image_url(lat_f, lng_f, DEFAULT_ZOOM, with_key=False),
                    "image_zoom": DEFAULT_ZOOM,
                    "image_hash": image_hash,
                    "topography": features["topography"],
                    "vegetation_pct": features["vegetation_pct"],
                    "paved_access": features["paved_access"],
                    "sidewalk_present": features["sidewalk_present"],
                    "drainage_visible": features["drainage_visible"],
                    "neighbors_built_pct": features["neighbors_built_pct"],
                    "lot_shape": features["lot_shape"],
                    "visible_obstacles": features["visible_obstacles"],
                    "socioeconomic_signal": features["socioeconomic_signal"],
                    "raw_vision_response": features.get("_raw") or {},
                    "vision_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    "vision_score": score,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }

                db.table("vision_features").upsert(row, on_conflict="listing_id").execute()
                stats["extracted"] += 1

            except Exception:
                logger.warning("[vision] Falha listing %s", lid, exc_info=True)
                stats["failed"] += 1

        logger.info(
            "[vision] Done: processed=%s extracted=%s failed=%s skipped=%s",
            stats["processed"], stats["extracted"], stats["failed"], stats["skipped_no_coords"],
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[vision] Run falhou")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats

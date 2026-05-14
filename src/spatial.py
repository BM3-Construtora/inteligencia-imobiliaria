"""Spatial utilities — proximity enrichment using PostGIS data in Supabase.

Calcula distâncias de listings para POIs e centros econômicos.
Requer: PostGIS ativado no Supabase (sql/042_postgis.sql aplicado)

Funções principais:
  run_proximity_enrichment() — enriquece listings com distâncias a POIs
  get_economic_centroid_distances(lat, lng) → dict[str, float]
  get_mcmv_accessibility_score(lat, lng) → float (0-100)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

# Critérios de acessibilidade MCMV (baseados nos critérios reais da Caixa)
MCMV_ACCESSIBILITY_WEIGHTS = {
    "school":       {"max_m": 1500, "weight": 0.30},  # escola pública ≤1500m
    "bus_stop":     {"max_m": 800,  "weight": 0.25},  # ponto de ônibus ≤800m
    "hospital":     {"max_m": 5000, "weight": 0.20},  # UBS/hospital ≤5km
    "supermarket":  {"max_m": 2000, "weight": 0.15},  # comércio ≤2km
    "park":         {"max_m": 1000, "weight": 0.10},  # área de lazer ≤1km
}


def run_proximity_enrichment(batch_size: int = 500) -> dict[str, int]:
    """Calcula e armazena distâncias de listings a POIs via PostGIS.

    Usa ST_Distance geoespacial do Supabase. Requer pois populados via osm_collector.
    """
    db = get_client()
    stats = {"processed": 0, "updated": 0, "skipped": 0, "failed": 0}

    run_result = db.table("agent_runs").insert({
        "agent_name": "proximity_enricher", "status": "running"
    }).execute()
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Listings com coordenadas mas sem proximidade calculada ainda
        listings_result = db.table("listings").select(
            "id, latitude, longitude"
        ).eq("is_active", True).not_.is_("latitude", "null").not_.is_("longitude", "null").limit(batch_size).execute()

        listings = listings_result.data or []
        logger.info(f"[spatial] Enriquecendo {len(listings)} listings com proximidade a POIs")

        for listing in listings:
            try:
                listing_id = listing["id"]
                lat = listing["latitude"]
                lng = listing["longitude"]

                proximities = _calculate_proximities(db, listing_id, lat, lng)
                stats["processed"] += 1

                if proximities:
                    # Upsert em listing_poi_proximity
                    for row in proximities:
                        db.table("listing_poi_proximity").upsert(
                            row, on_conflict="listing_id,category"
                        ).execute()
                    stats["updated"] += 1

                # Calcular e salvar MCMV accessibility score
                mcmv_score = _calculate_mcmv_score_from_proximities(proximities)
                if mcmv_score is not None:
                    db.table("listings").update({
                        "mcmv_accessibility_score": mcmv_score,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", listing_id).execute()

            except Exception:
                logger.debug(f"[spatial] Erro no listing {listing.get('id')}", exc_info=True)
                stats["failed"] += 1

        _finish_run(db, run_id, "completed", stats)
        logger.info(f"[spatial] Done: {stats}")

    except Exception as e:
        logger.exception("[spatial] Falha geral")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _calculate_proximities(
    db: Any, listing_id: int, lat: float, lng: float
) -> list[dict]:
    """Busca POI mais próximo de cada categoria via PostGIS no Supabase."""
    proximities: list[dict] = []
    categories = list(MCMV_ACCESSIBILITY_WEIGHTS.keys()) + ["university", "industrial"]

    for category in categories:
        try:
            # Query PostGIS: POI mais próximo desta categoria
            # Usa RPC do Supabase ou query direta
            result = db.rpc("nearest_poi", {
                "p_lat": lat,
                "p_lng": lng,
                "p_category": category,
                "p_max_distance_m": 10000,
            }).execute()

            if result.data:
                row = result.data[0] if isinstance(result.data, list) else result.data
                proximities.append({
                    "listing_id":    listing_id,
                    "category":      category,
                    "poi_id":        row.get("poi_id"),
                    "distance_m":    row.get("distance_m"),
                    "poi_name":      row.get("poi_name"),
                    "calculated_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception:
            # Fallback: calcular haversine direto se RPC não existir
            dist = _nearest_poi_haversine(db, lat, lng, category)
            if dist:
                proximities.append({
                    "listing_id":    listing_id,
                    "category":      category,
                    "poi_id":        dist["poi_id"],
                    "distance_m":    dist["distance_m"],
                    "poi_name":      dist["poi_name"],
                    "calculated_at": datetime.now(timezone.utc).isoformat(),
                })

    return proximities


def _nearest_poi_haversine(
    db: Any, lat: float, lng: float, category: str
) -> Optional[dict]:
    """Fallback: busca POIs da categoria e calcula haversine localmente."""
    try:
        result = db.table("pois").select(
            "id, name, latitude, longitude"
        ).eq("category", category).not_.is_("latitude", "null").execute()

        pois = result.data or []
        if not pois:
            return None

        best = min(pois, key=lambda p: haversine_m(lat, lng, p["latitude"], p["longitude"]))
        return {
            "poi_id":    best["id"],
            "distance_m": haversine_m(lat, lng, best["latitude"], best["longitude"]),
            "poi_name":  best.get("name"),
        }
    except Exception:
        return None


def _calculate_mcmv_score_from_proximities(proximities: list[dict]) -> Optional[float]:
    """Calcula score de acessibilidade MCMV (0-100) baseado nas distâncias calculadas."""
    if not proximities:
        return None

    prox_map = {p["category"]: p.get("distance_m") for p in proximities}
    total_score = 0.0
    total_weight = 0.0

    for category, criteria in MCMV_ACCESSIBILITY_WEIGHTS.items():
        dist = prox_map.get(category)
        weight = criteria["weight"]
        max_m = criteria["max_m"]

        if dist is None:
            # Sem POI desta categoria: score 0 para este critério
            total_weight += weight
            continue

        if dist <= max_m:
            # Score proporcional: 100 se distância=0, 0 se distância=max_m
            score = max(0.0, (1 - dist / max_m)) * 100
        else:
            score = 0.0

        total_score += score * weight
        total_weight += weight

    if total_weight == 0:
        return None

    return round(total_score / total_weight, 2)


def get_economic_centroid_distances(lat: float, lng: float) -> dict[str, float]:
    """Retorna distância em km de um ponto para cada centro econômico de Marília.

    Usa dados hardcoded (não precisa de DB) para ser chamado no price_model.
    """
    CENTROIDS = {
        "commercial": (-22.2163, -49.9491),   # Av. Sampaio Vidal + Shopping
        "health":     (-22.2089, -49.9433),   # Famema + Amaral Carvalho
        "education":  (-22.2237, -49.9601),   # Unimar + Unesp
        "industrial": (-22.1978, -49.9752),   # Distrito industrial
        "historic":   (-22.2141, -49.9466),   # Marco zero
    }

    return {
        name: round(haversine_km(lat, lng, clat, clng), 3)
        for name, (clat, clng) in CENTROIDS.items()
    }


def get_mcmv_accessibility_score(lat: float, lng: float, db: Any = None) -> Optional[float]:
    """Score de acessibilidade MCMV (0-100) para uma coordenada.

    Se db fornecido, consulta pois table. Senão retorna None.
    """
    if db is None:
        return None

    proximities = _nearest_poi_haversine_all(db, lat, lng)
    return _calculate_mcmv_score_from_proximities(proximities)


def _nearest_poi_haversine_all(db: Any, lat: float, lng: float) -> list[dict]:
    """Calcula POI mais próximo de cada categoria via haversine."""
    results = []
    for category in MCMV_ACCESSIBILITY_WEIGHTS:
        dist = _nearest_poi_haversine(db, lat, lng, category)
        if dist:
            results.append({"category": category, **dist})
    return results


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância haversine em km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância haversine em metros."""
    return haversine_km(lat1, lng1, lat2, lng2) * 1000


def _finish_run(db: Any, run_id: Any, status: str, stats: dict, error: str = "") -> None:
    if not run_id:
        return
    try:
        db.table("agent_runs").update({
            "status": status,
            "items_processed": stats.get("processed", 0),
            "items_created": stats.get("updated", 0),
            "items_failed": stats.get("failed", 0),
            "metadata": {"error": error} if error else stats,
        }).eq("id", run_id).execute()
    except Exception:
        pass

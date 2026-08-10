"""Coleta POIs (Pontos de Interesse) de Marília-SP via OpenStreetMap (OSMnx).

Fonte: OpenStreetMap via Overpass API (osmnx library)
Tabela destino: pois

Categorias coletadas:
  - hospital, health_post (UBS/postinho), university, school, daycare (creche)
  - pharmacy, supermarket, shopping, marketplace (feira), bank, fuel, police
  - bus_stop, park, industrial

Ver OSM_TAGS_BY_CATEGORY para as tags OSM exatas de cada categoria.

Requer: osmnx, geopandas (adicionar ao pyproject.toml)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)

MARILIA_PLACE = "Marília, São Paulo, Brazil"

# Tags OSM por categoria
OSM_TAGS_BY_CATEGORY: dict[str, dict] = {
    "hospital":     {"amenity": ["hospital"]},
    "health_post":  {"amenity": ["clinic", "doctors", "health_post"]},  # UBS / postinho
    "university":   {"amenity": ["university", "college"]},
    "school":       {"amenity": "school"},
    "daycare":      {"amenity": "kindergarten"},                        # creche / pré-escola
    "pharmacy":     {"amenity": "pharmacy"},
    "supermarket":  {"shop": ["supermarket", "convenience"]},
    "shopping":     {"shop": ["mall", "department_store"]},             # shopping center
    "marketplace":  {"amenity": "marketplace"},                         # feira / mercado municipal
    "bank":         {"amenity": ["bank"]},
    "fuel":         {"amenity": "fuel"},                                # posto de combustível
    "police":       {"amenity": "police"},
    "bus_stop":     {"highway": "bus_stop", "amenity": "bus_station"},
    "park":         {"leisure": ["park", "garden", "playground"]},
    "industrial":   {"landuse": "industrial"},
}

# Mapeamento subcategoria OSM → categoria interna
SUBCATEGORY_MAP: dict[str, str] = {
    "hospital": "hospital",
    "clinic": "health_post", "doctors": "health_post", "health_post": "health_post",
    "university": "university", "college": "university",
    "school": "school",
    "kindergarten": "daycare",
    "pharmacy": "pharmacy",
    "supermarket": "supermarket", "convenience": "supermarket",
    "mall": "shopping", "department_store": "shopping",
    "marketplace": "marketplace",
    "bank": "bank",
    "fuel": "fuel",
    "police": "police",
    "bus_stop": "bus_stop", "bus_station": "bus_stop",
    "park": "park", "garden": "park", "playground": "park",
    "industrial": "industrial",
}


def run_osm_collector() -> dict[str, int]:
    """Coleta todos os POIs de Marília via OSMnx e faz upsert no Supabase."""
    db = get_client()
    stats = {"collected": 0, "upserted": 0, "failed": 0}

    run_result = db.table("agent_runs").insert({
        "agent_name": "osm_collector", "status": "running"
    }).execute()
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        import osmnx as ox
        import geopandas as gpd

        ox.settings.log_console = False
        ox.settings.use_cache = True
        ox.settings.timeout = 180

        all_pois: list[dict] = []

        for category, tags in OSM_TAGS_BY_CATEGORY.items():
            logger.info(f"[osm] Coletando: {category}")
            try:
                gdf = ox.features_from_place(MARILIA_PLACE, tags=tags)
                pois = _gdf_to_pois(gdf, category)
                all_pois.extend(pois)
                stats["collected"] += len(pois)
                logger.info(f"[osm] {category}: {len(pois)} POIs")
                time.sleep(1.5)  # respeita rate limit do Overpass
            except Exception:
                logger.warning(f"[osm] Falha ao coletar {category}", exc_info=True)
                stats["failed"] += 1

        # Dedup por osm_id antes de upsert
        seen: set[str] = set()
        unique_pois: list[dict] = []
        for p in all_pois:
            if p["osm_id"] not in seen:
                seen.add(p["osm_id"])
                unique_pois.append(p)

        logger.info(f"[osm] Total: {len(unique_pois)} POIs únicos")

        # Upsert em batches de 100
        batch_size = 100
        for i in range(0, len(unique_pois), batch_size):
            batch = unique_pois[i:i + batch_size]
            try:
                db.table("pois").upsert(
                    batch, on_conflict="osm_id"
                ).execute()
                stats["upserted"] += len(batch)
            except Exception:
                logger.exception(f"[osm] Falha no upsert batch {i}")
                stats["failed"] += len(batch)

        _finish_run(db, run_id, "completed", stats)
        logger.info(f"[osm] Done: {stats}")

    except ImportError:
        logger.error("[osm] osmnx não instalado. Adicione ao pyproject.toml: osmnx>=1.9, geopandas>=0.14")
        _finish_run(db, run_id, "failed", stats, "osmnx not installed")
        raise
    except Exception as e:
        logger.exception("[osm] Falha geral")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _gdf_to_pois(gdf: Any, category: str) -> list[dict]:
    """Converte GeoDataFrame OSMnx em lista de dicts para upsert."""
    pois: list[dict] = []

    for idx, row in gdf.iterrows():
        try:
            # OSMnx usa MultiIndex (element_type, osmid)
            osm_id = f"{idx[0]}_{idx[1]}" if isinstance(idx, tuple) else str(idx)

            # Centroide para geometrias complexas (polígonos, etc)
            geom = row.geometry
            if geom is None:
                continue
            if hasattr(geom, "centroid"):
                point = geom.centroid
            else:
                point = geom

            lat = point.y
            lng = point.x

            # Valida coordenadas dentro de Marília (bounding box aproximado)
            if not (-22.32 < lat < -22.10 and -50.10 < lng < -49.85):
                continue

            # Detecta subcategoria
            subcategory = None
            for tag_key in ["amenity", "shop", "highway", "leisure", "landuse"]:
                val = row.get(tag_key)
                if val and isinstance(val, str):
                    subcategory = val
                    break

            name = row.get("name") or row.get("name:pt") or ""
            address_parts = []
            for field in ["addr:street", "addr:housenumber", "addr:neighbourhood"]:
                val = row.get(field)
                if val:
                    address_parts.append(str(val))
            address = ", ".join(address_parts) if address_parts else None

            pois.append({
                "osm_id":      osm_id,
                "category":    category,
                "subcategory": subcategory,
                "name":        str(name)[:200] if name else None,
                "address":     address,
                "latitude":    round(lat, 7),
                "longitude":   round(lng, 7),
                "geom":        f"SRID=4326;POINT({lng} {lat})",
                "source":      "osmnx",
                "updated_at":  datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            logger.debug(f"[osm] Erro processando POI {idx}", exc_info=True)

    return pois


def _finish_run(db: Any, run_id: Any, status: str, stats: dict, error: str = "") -> None:
    if not run_id:
        return
    try:
        db.table("agent_runs").update({
            "status": status,
            "items_processed": stats.get("collected", 0),
            "items_created": stats.get("upserted", 0),
            "items_failed": stats.get("failed", 0),
            "metadata": {"error": error} if error else stats,
        }).eq("id", run_id).execute()
    except Exception:
        pass

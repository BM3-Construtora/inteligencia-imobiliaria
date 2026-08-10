"""Coleta setores censitários de Marília-SP (Censo 2022, IBGE).

A API de malhas do IBGE (v3/v4) NÃO expõe setores — só o contorno do município.
Os setores 2022 (polígono) vêm do GeoPackage por UF no geoftp, e os atributos
(população, domicílios) do "Agregados por Setor — básico". A renda por setor
NÃO foi publicada neste release; a camada usa densidade populacional como proxy.

Fontes (baixadas e cacheadas em cache/, estáticas — Censo 2022):
  - Geometria: geoftp .../censo_2022/setores/gpkg/UF/SP/SP_setores_CD2022.gpkg
  - Atributos: .../Agregados_por_Setor_csv/Agregados_por_setores_basico_BR_*.zip

Tabela destino: census_sectors (migration *_postgis + *_ibge_sectors).
Idempotente: pula se census_sectors já tem geometria de Marília, salvo
FORCE_IBGE_REFRESH=1. Roda localmente (download pesado); não é passo de CI.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

MARILIA_CODE = "3529005"

GPKG_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/"
    "gpkg/UF/SP/SP_setores_CD2022.gpkg"
)
BASICO_URL = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/"
    "Agregados_por_setores_basico_BR_20260520.zip"
)

CACHE_DIR = os.getenv("IBGE_CACHE_DIR", "cache")
GPKG_PATH = os.path.join(CACHE_DIR, "sp_setores_CD2022.gpkg")
BASICO_PATH = os.path.join(CACHE_DIR, "basico_BR.zip")

BATCH_SIZE = 100


def run_ibge_sectors_collector() -> dict[str, int]:
    """Popula census_sectors com os setores de Marília (geometria + população)."""
    db = get_client()
    stats = {"sectors_fetched": 0, "upserted": 0, "failed": 0}

    run = db.table("agent_runs").insert(
        {"agent_name": "collector_ibge_sectors", "status": "running"}
    ).execute()
    run_id = run.data[0]["id"] if run.data else None

    try:
        if not _needs_refresh(db):
            logger.info("[ibge_sectors] census_sectors já populado; FORCE_IBGE_REFRESH=1 para refazer")
            _finish_run(db, run_id, "completed", stats)
            return stats

        _ensure_file(GPKG_PATH, GPKG_URL)
        _ensure_file(BASICO_PATH, BASICO_URL)

        attrs = _load_basico_attrs()
        logger.info(f"[ibge_sectors] atributos básicos: {len(attrs)} setores de Marília")

        rows = _load_sector_rows(attrs)
        stats["sectors_fetched"] = len(rows)
        logger.info(f"[ibge_sectors] {len(rows)} setores com geometria")

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            try:
                db.table("census_sectors").upsert(batch, on_conflict="sector_code").execute()
                stats["upserted"] += len(batch)
            except Exception:
                stats["failed"] += len(batch)
                logger.exception(f"[ibge_sectors] upsert batch falhou (offset {i})")

        logger.info(f"[ibge_sectors] Done: {stats}")
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[ibge_sectors] Falha geral")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _needs_refresh(db: Any) -> bool:
    if os.getenv("FORCE_IBGE_REFRESH") == "1":
        return True
    try:
        r = (
            db.table("census_sectors")
            .select("id", count="exact")
            .not_.is_("geom", "null")
            .limit(1)
            .execute()
        )
        return not (r.count and r.count > 0)
    except Exception:
        return True


def _ensure_file(path: str, url: str) -> None:
    """Baixa `url` para `path` se ainda não existir (cache estático do Censo 2022)."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    logger.info(f"[ibge_sectors] baixando {url.rsplit('/', 1)[-1]}...")
    with httpx.stream("GET", url, timeout=300, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"}) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_bytes(1 << 20):
                f.write(chunk)


def _load_basico_attrs() -> dict[str, dict[str, Any]]:
    """CD_SETOR -> {populacao (v0001), domicilios (v0002)} para Marília."""
    attrs: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(BASICO_PATH) as z:
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(csv_name) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1"), delimiter=";")
            header = next(reader)
            idx = {h.lower(): i for i, h in enumerate(header)}
            i_cod, i_pop, i_dom = idx["cd_setor"], idx["v0001"], idx["v0002"]
            for row in reader:
                cod = row[i_cod]
                if cod.startswith(MARILIA_CODE):
                    attrs[cod] = {
                        "populacao": _to_int(row[i_pop]),
                        "domicilios": _to_int(row[i_dom]),
                    }
    return attrs


def _load_sector_rows(attrs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Lê os setores de Marília do GeoPackage e monta as linhas de census_sectors."""
    import geopandas as gpd
    from shapely.geometry import MultiPolygon

    gdf = gpd.read_file(GPKG_PATH, where=f"CD_MUN = '{MARILIA_CODE}'")
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    rows: list[dict[str, Any]] = []
    for _, feat in gdf.iterrows():
        geom = feat.geometry
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])

        cod = str(feat["CD_SETOR"])
        area = feat.get("AREA_KM2")
        a = attrs.get(cod, {})
        pop = a.get("populacao")
        densidade = round(pop / area, 1) if (pop and area and area > 0) else None

        rows.append({
            "sector_code": cod,
            "municipality_code": MARILIA_CODE,
            "geom": f"SRID=4326;{geom.wkt}",
            "populacao": pop,
            "total_domicilios": a.get("domicilios"),
            "densidade_demo": densidade,
            "renda_per_capita": None,  # não publicada por setor no Censo 2022
            "source_year": 2022,
        })
    return rows


def _to_int(val: str | None) -> Optional[int]:
    if not val:
        return None
    v = val.strip().replace(".", "")
    if not v or v in ("X", "-"):
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _finish_run(db: Any, run_id: Any, status: str, stats: dict, error: str = "") -> None:
    if not run_id:
        return
    try:
        update = {
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "items_processed": stats.get("sectors_fetched", 0),
            "items_created": stats.get("upserted", 0),
            "items_failed": stats.get("failed", 0),
            "metadata": stats,
        }
        if error:
            update["error_message"] = error[:1000]
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.debug("[ibge_sectors] finish_run falhou", exc_info=True)

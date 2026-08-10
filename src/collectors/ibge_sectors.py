"""Coleta setores censitários de Marília-SP via API IBGE.

Fontes:
  - Malha geográfica: https://servicodados.ibge.gov.br/api/v3/malhas/municipios/3529005
  - Dados de renda: IBGE Censo 2022 tabelas SIDRA (onde disponível)

Tabela destino: census_sectors (criada em sql/042_postgis.sql)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

MARILIA_CODE = "3529005"

# API de malha censitária (GeoJSON com setores censitários)
IBGE_MESH_URL = (
    f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{MARILIA_CODE}"
    f"?formato=application/vnd.geo+json&resolucao=5&qualidade=maxima"
)

# Dados de renda por setor (IBGE Censo 2022 — renda per capita média por setor)
# Nota: IBGE não publica renda por setor diretamente — usamos setores de SP como proxy
# atualizado com dados do Censo 2022 quando disponíveis via SIDRA
IBGE_SIDRA_RENDA_URL = (
    f"https://servicodados.ibge.gov.br/api/v3/agregados/6691/periodos/2022"
    f"/variaveis/10605?localidades=N8[{MARILIA_CODE}[all]]"
)

TIMEOUT = 60


def run_ibge_sectors_collector() -> dict[str, int]:
    """Baixa malha de setores censitários de Marília e faz upsert no Supabase."""
    db = get_client()
    stats = {"sectors_fetched": 0, "upserted": 0, "failed": 0}

    run_result = db.table("agent_runs").insert({
        "agent_name": "ibge_sectors_collector", "status": "running"
    }).execute()
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            # 1. Baixar malha de setores censitários (GeoJSON)
            logger.info("[ibge_sectors] Baixando malha de setores censitários...")
            resp = client.get(IBGE_MESH_URL, headers={"Accept": "application/geo+json"})

            if resp.status_code != 200:
                logger.error(f"[ibge_sectors] HTTP {resp.status_code}: {resp.text[:200]}")
                _finish_run(db, run_id, "failed", stats, f"HTTP {resp.status_code}")
                return stats

            geojson = resp.json()
            features = geojson.get("features", [])
            logger.info(f"[ibge_sectors] {len(features)} feature(s) recebida(s)")

            # A API de malhas do IBGE (v3/v4) NÃO expõe setores censitários: ela
            # devolve só o contorno do município (1 feature, codarea=3529005).
            # Gravar isso criava 1 linha placeholder enganosa em census_sectors.
            # Setores 2022 (polígono + renda) só existem como download do geoftp:
            #   malhas: https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/
            #           malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/
            #   renda:  Agregados por Setores Censitários 2022 (CSV, por UF)
            # A ingestão desses arquivos exige geopandas e roda no ambiente local.
            if len(features) <= 1:
                msg = (
                    f"API de malhas retornou {len(features)} feature (contorno do "
                    "município, não setores). Setores 2022 exigem ingestão do "
                    "shapefile do geoftp + Agregados por Setores. Nada gravado."
                )
                logger.error(f"[ibge_sectors] {msg}")
                _finish_run(db, run_id, "failed", stats, msg)
                return stats

            # 2. Tentar buscar dados de renda (pode falhar — não é crítico)
            renda_map: dict[str, float] = {}
            try:
                renda_resp = client.get(IBGE_SIDRA_RENDA_URL)
                if renda_resp.status_code == 200:
                    renda_map = _parse_renda_data(renda_resp.json())
                    logger.info(f"[ibge_sectors] Dados de renda: {len(renda_map)} setores")
            except Exception:
                logger.warning("[ibge_sectors] Falha ao buscar dados de renda — continuando sem eles")

            # 3. Processar e fazer upsert de cada setor
            batch: list[dict] = []
            for feature in features:
                try:
                    sector = _process_feature(feature, renda_map)
                    if sector:
                        batch.append(sector)
                        stats["sectors_fetched"] += 1
                except Exception:
                    logger.debug("[ibge_sectors] Erro processando setor", exc_info=True)
                    stats["failed"] += 1

                # Upsert em batches de 50
                if len(batch) >= 50:
                    _upsert_batch(db, batch, stats)
                    batch = []

            if batch:
                _upsert_batch(db, batch, stats)

        logger.info(f"[ibge_sectors] Done: {stats}")
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[ibge_sectors] Falha geral")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _process_feature(feature: dict, renda_map: dict[str, float]) -> Optional[dict]:
    """Processa uma feature GeoJSON do IBGE para formato do Supabase."""
    props = feature.get("properties", {})
    geom = feature.get("geometry")

    if not geom:
        return None

    sector_code = str(
        props.get("codarea") or
        props.get("CD_SETOR") or
        props.get("id") or
        ""
    )
    if not sector_code:
        return None

    # Converter geometry para WKT para inserção no PostGIS
    geom_wkt = _geojson_to_wkt(geom)
    if not geom_wkt:
        return None

    renda = renda_map.get(sector_code)

    return {
        "sector_code":       sector_code,
        "municipality_code": MARILIA_CODE,
        "geom":              f"SRID=4326;{geom_wkt}",
        "renda_per_capita":  renda,
        "source_year":       2022,
    }


def _geojson_to_wkt(geom: dict) -> Optional[str]:
    """Converte geometry GeoJSON para WKT simples para PostGIS."""
    geom_type = geom.get("type", "")
    coords = geom.get("coordinates", [])

    try:
        if geom_type == "Polygon":
            rings = []
            for ring in coords:
                pts = ", ".join(f"{x} {y}" for x, y in ring)
                rings.append(f"({pts})")
            return f"MULTIPOLYGON(({rings[0]}))" if len(rings) == 1 else f"MULTIPOLYGON(({', '.join(rings)}))"

        elif geom_type == "MultiPolygon":
            polygons = []
            for polygon in coords:
                rings = []
                for ring in polygon:
                    pts = ", ".join(f"{x} {y}" for x, y in ring)
                    rings.append(f"({pts})")
                polygons.append(f"({', '.join(rings)})")
            return f"MULTIPOLYGON({', '.join(polygons)})"

    except Exception:
        logger.debug("[ibge_sectors] Erro convertendo geometry", exc_info=True)

    return None


def _parse_renda_data(data: list) -> dict[str, float]:
    """Parseia resposta SIDRA de renda por setor censitário."""
    renda_map: dict[str, float] = {}
    try:
        for item in data:
            for result in item.get("resultados", []):
                for serie in result.get("series", []):
                    loc = serie.get("localidade", {})
                    sector_code = loc.get("id", "")
                    values = serie.get("serie", {})
                    for year, val in values.items():
                        if val and val not in ("-", "..."):
                            try:
                                renda_map[sector_code] = float(str(val).replace(",", "."))
                            except ValueError:
                                pass
    except Exception:
        logger.debug("[ibge_sectors] Erro parseiando dados de renda", exc_info=True)
    return renda_map


def _upsert_batch(db: Any, batch: list[dict], stats: dict) -> None:
    try:
        db.table("census_sectors").upsert(
            batch, on_conflict="sector_code"
        ).execute()
        stats["upserted"] += len(batch)
    except Exception:
        logger.exception(f"[ibge_sectors] Falha no upsert de {len(batch)} setores")
        stats["failed"] += len(batch)


def _finish_run(db: Any, run_id: Any, status: str, stats: dict, error: str = "") -> None:
    if not run_id:
        return
    try:
        db.table("agent_runs").update({
            "status": status,
            "items_processed": stats.get("sectors_fetched", 0),
            "items_created": stats.get("upserted", 0),
            "items_failed": stats.get("failed", 0),
            "metadata": {"error": error} if error else stats,
        }).eq("id", run_id).execute()
    except Exception:
        pass

"""IBGE Census data integration — demographic overlay for neighborhoods."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

# IBGE API endpoints
IBGE_CITY_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/3529005"  # Marília
IBGE_INDICATORS_URL = "https://servicodados.ibge.gov.br/api/v3/agregados"


def fetch_marilia_demographics() -> dict[str, Any]:
    """Fetch demographic data for Marília from IBGE API."""
    data: dict[str, Any] = {}

    try:
        # Basic city info
        resp = httpx.get(IBGE_CITY_URL, timeout=15)
        if resp.status_code == 200:
            city = resp.json()
            data["city_name"] = city.get("nome", "Marília")
            data["micro_region"] = city.get("microrregiao", {}).get("nome")
            data["meso_region"] = city.get("microrregiao", {}).get("mesorregiao", {}).get("nome")

        # Population estimate (table 6579)
        pop_url = f"{IBGE_INDICATORS_URL}/6579/periodos/-1/variaveis/9324?localidades=N6[3529005]"
        resp = httpx.get(pop_url, timeout=15)
        if resp.status_code == 200:
            result = resp.json()
            if result and result[0].get("resultados"):
                series = result[0]["resultados"][0].get("series", [])
                if series:
                    values = series[0].get("serie", {})
                    # Get latest value
                    for year in sorted(values.keys(), reverse=True):
                        if values[year] and values[year] != "-":
                            data["population"] = int(values[year])
                            data["population_year"] = int(year)
                            break

        # GDP per capita (table 5938)
        gdp_url = f"{IBGE_INDICATORS_URL}/5938/periodos/-1/variaveis/37?localidades=N6[3529005]"
        resp = httpx.get(gdp_url, timeout=15)
        if resp.status_code == 200:
            result = resp.json()
            if result and result[0].get("resultados"):
                series = result[0]["resultados"][0].get("series", [])
                if series:
                    values = series[0].get("serie", {})
                    for year in sorted(values.keys(), reverse=True):
                        if values[year] and values[year] != "-":
                            data["gdp_per_capita"] = float(values[year])
                            data["gdp_year"] = int(year)
                            break

    except Exception:
        logger.exception("[ibge] Failed to fetch demographics")

    return data


def run_ibge_update() -> dict[str, int]:
    """Fetch IBGE data and store as market indices."""
    db = get_client()
    stats = {"metrics": 0}

    data = fetch_marilia_demographics()
    logger.info(f"[ibge] Fetched: {data}")

    metrics = []
    if data.get("population"):
        metrics.append({
            "source": "ibge",
            "region": "marilia",
            "period": str(data.get("population_year", "2022")),
            "metric_name": "populacao",
            "metric_value": data["population"],
            "metadata": {"context": "Estimativa populacional IBGE"},
        })

    if data.get("gdp_per_capita"):
        metrics.append({
            "source": "ibge",
            "region": "marilia",
            "period": str(data.get("gdp_year", "2021")),
            "metric_name": "pib_per_capita",
            "metric_value": data["gdp_per_capita"],
            "metadata": {"context": "PIB per capita IBGE", "unit": "R$"},
        })

    for m in metrics:
        try:
            db.table("market_indices").upsert(
                m, on_conflict="source,region,period,metric_name"
            ).execute()
            stats["metrics"] += 1
        except Exception:
            logger.exception(f"[ibge] Failed to save: {m['metric_name']}")

    logger.info(f"[ibge] Done: {stats['metrics']} metrics saved")
    return stats

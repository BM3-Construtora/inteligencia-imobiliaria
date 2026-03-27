"""IBGE Census data integration — demographic overlay for neighborhoods."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

MARILIA_CODE = "3529005"
IBGE_CITY_URL = f"https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{MARILIA_CODE}"
IBGE_AGREGADOS_URL = "https://servicodados.ibge.gov.br/api/v3/agregados"


def _fetch_ibge_table(table: str, variable: str) -> dict[str, Any] | None:
    """Fetch a single variable from an IBGE aggregate table."""
    url = f"{IBGE_AGREGADOS_URL}/{table}/periodos/-1/variaveis/{variable}?localidades=N6[{MARILIA_CODE}]"
    try:
        resp = httpx.get(url, timeout=20)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        logger.debug(f"[ibge] Failed to fetch table {table} var {variable}")
    return None


def _extract_latest_value(data: list) -> tuple[Any, str | None]:
    """Extract the latest non-null value and its period from IBGE response."""
    if not data or not data[0].get("resultados"):
        return None, None
    series = data[0]["resultados"][0].get("series", [])
    if not series:
        return None, None
    values = series[0].get("serie", {})
    for year in sorted(values.keys(), reverse=True):
        v = values[year]
        if v and v != "-" and v != "...":
            return v, year
    return None, None


def fetch_marilia_demographics() -> dict[str, Any]:
    """Fetch comprehensive demographic data for Marília."""
    data: dict[str, Any] = {}

    try:
        # Basic city info
        resp = httpx.get(IBGE_CITY_URL, timeout=15)
        if resp.status_code == 200:
            city = resp.json()
            data["city_name"] = city.get("nome", "Marília")

        # Population estimate (table 6579, var 9324)
        result = _fetch_ibge_table("6579", "9324")
        val, year = _extract_latest_value(result)
        if val:
            data["population"] = int(val)
            data["population_year"] = int(year)

        # GDP per capita (table 5938, var 37)
        result = _fetch_ibge_table("5938", "37")
        val, year = _extract_latest_value(result)
        if val:
            data["gdp_per_capita"] = float(val)
            data["gdp_year"] = int(year)

        # Households (table 4714, var 614 = domicílios particulares permanentes)
        result = _fetch_ibge_table("4714", "614")
        val, year = _extract_latest_value(result)
        if val:
            data["total_households"] = int(val)
            data["households_year"] = int(year)

        # Average household income (table 5691, var 5691 = rendimento nominal mensal domiciliar per capita)
        result = _fetch_ibge_table("5691", "5691")
        val, year = _extract_latest_value(result)
        if val:
            data["avg_household_income_per_capita"] = float(val)
            data["income_year"] = int(year)

        # Urbanization rate (table 1301, var 616)
        result = _fetch_ibge_table("1301", "616")
        val, year = _extract_latest_value(result)
        if val:
            data["urban_population"] = int(val)

    except Exception:
        logger.exception("[ibge] Failed to fetch demographics")

    return data


def estimate_mcmv_demand(demographics: dict[str, Any]) -> dict[str, Any]:
    """Estimate MCMV demand based on demographics.

    Uses population growth and income distribution to estimate
    how many housing units are needed per MCMV faixa.
    """
    pop = demographics.get("population", 247000)
    households = demographics.get("total_households", 88000)
    income_pc = demographics.get("avg_household_income_per_capita", 1800)

    # Estimate average household size
    avg_household_size = pop / households if households > 0 else 3.2

    # Annual population growth (2.57% observed)
    annual_growth_rate = 0.0257
    new_residents_year = int(pop * annual_growth_rate)
    new_households_year = int(new_residents_year / avg_household_size)

    # Estimate income distribution for MCMV faixas
    # Based on IBGE income per capita → household income (×3 members avg)
    avg_household_income = income_pc * avg_household_size

    # MCMV Faixa distribution estimates for interior SP
    faixa1_pct = 0.35 if avg_household_income < 3200 else 0.25
    faixa2_pct = 0.25
    faixa3_pct = 0.20
    medio_padrao_pct = 0.15
    alto_padrao_pct = 0.05

    # Housing deficit proxy: 21% vacancy but qualitative deficit exists
    qualitative_deficit_pct = 0.15  # estimated based on IBGE data
    deficit_units = int(households * qualitative_deficit_pct)

    return {
        "new_households_year": new_households_year,
        "housing_deficit_estimate": deficit_units,
        "avg_household_size": round(avg_household_size, 1),
        "avg_household_income": round(avg_household_income, 0),
        "demand_faixa1_units_year": int(new_households_year * faixa1_pct),
        "demand_faixa2_units_year": int(new_households_year * faixa2_pct),
        "demand_faixa3_units_year": int(new_households_year * faixa3_pct),
        "demand_medio_padrao_year": int(new_households_year * medio_padrao_pct),
        "demand_alto_padrao_year": int(new_households_year * alto_padrao_pct),
    }


def run_ibge_update() -> dict[str, int]:
    """Fetch IBGE data and store as market indices."""
    db = get_client()
    stats = {"metrics": 0}

    demographics = fetch_marilia_demographics()
    logger.info(f"[ibge] Fetched demographics: {demographics}")

    demand = estimate_mcmv_demand(demographics)
    logger.info(f"[ibge] Demand estimates: {demand}")

    # Save all metrics
    all_metrics = []

    if demographics.get("population"):
        all_metrics.append(("populacao", demographics["population"], str(demographics.get("population_year", "2025")), "Estimativa populacional IBGE"))
    if demographics.get("gdp_per_capita"):
        all_metrics.append(("pib_per_capita", demographics["gdp_per_capita"], str(demographics.get("gdp_year", "2021")), "PIB per capita IBGE (R$)"))
    if demographics.get("total_households"):
        all_metrics.append(("total_domicilios", demographics["total_households"], str(demographics.get("households_year", "2022")), "Domicílios particulares permanentes"))
    if demographics.get("avg_household_income_per_capita"):
        all_metrics.append(("renda_domiciliar_per_capita", demographics["avg_household_income_per_capita"], str(demographics.get("income_year", "2022")), "Rendimento nominal mensal domiciliar per capita (R$)"))

    # Demand estimates
    all_metrics.append(("demanda_mcmv_faixa1_anual", demand["demand_faixa1_units_year"], "2026", "Estimativa unidades/ano Faixa 1"))
    all_metrics.append(("demanda_mcmv_faixa2_anual", demand["demand_faixa2_units_year"], "2026", "Estimativa unidades/ano Faixa 2"))
    all_metrics.append(("demanda_mcmv_faixa3_anual", demand["demand_faixa3_units_year"], "2026", "Estimativa unidades/ano Faixa 3"))
    all_metrics.append(("deficit_habitacional_estimado", demand["housing_deficit_estimate"], "2026", "Déficit habitacional estimado"))
    all_metrics.append(("novos_domicilios_ano", demand["new_households_year"], "2026", "Novos domicílios necessários/ano"))
    all_metrics.append(("renda_media_domiciliar", demand["avg_household_income"], "2026", "Renda média domiciliar estimada (R$)"))

    for name, value, period, context in all_metrics:
        try:
            db.table("market_indices").upsert(
                {
                    "source": "ibge",
                    "region": "marilia",
                    "period": period,
                    "metric_name": name,
                    "metric_value": value,
                    "metadata": {"context": context},
                },
                on_conflict="source,region,period,metric_name",
            ).execute()
            stats["metrics"] += 1
        except Exception:
            logger.exception(f"[ibge] Failed to save: {name}")

    logger.info(f"[ibge] Done: {stats['metrics']} metrics saved")
    return stats

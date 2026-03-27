"""Collector for SINAPI construction cost indices from IBGE API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

# IBGE SINAPI API — Table 2296: National construction cost index by state
# Variables: 1198 = Custo médio m² (R$), 1196 = Variação mensal (%)
SINAPI_TABLE = "2296"
SINAPI_URL = f"https://servicodados.ibge.gov.br/api/v3/agregados/{SINAPI_TABLE}/periodos/-6/variaveis/1198|1196"
SP_CODE = "35"  # São Paulo state code


def run_sinapi_collector() -> dict[str, int]:
    """Fetch SINAPI construction cost data from IBGE and store in market_indices."""
    db = get_client()
    stats = {"metrics": 0}

    try:
        # Fetch SINAPI for São Paulo
        url = f"{SINAPI_URL}?localidades=N3[{SP_CODE}]"
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        metrics = []
        for variable in data:
            var_id = variable.get("id")
            var_name = variable.get("variavel", "")

            for result in variable.get("resultados", []):
                for serie in result.get("series", []):
                    locality = serie.get("localidade", {}).get("nome", "SP")
                    values = serie.get("serie", {})

                    for period, value in values.items():
                        if not value or value == "...":
                            continue

                        # Period format: "202601" → "2026-01"
                        formatted_period = f"{period[:4]}-{period[4:]}" if len(period) == 6 else period

                        metric_name = "sinapi_custo_m2" if var_id == "1198" else "sinapi_variacao_mensal_pct"
                        unit = "R$/m²" if var_id == "1198" else "%"

                        metrics.append({
                            "source": "sinapi",
                            "region": "sp",
                            "period": formatted_period,
                            "metric_name": metric_name,
                            "metric_value": float(value),
                            "metadata": {
                                "unit": unit,
                                "context": f"SINAPI {var_name} - {locality}",
                                "ibge_variable": var_id,
                            },
                        })

        # Save metrics
        for m in metrics:
            try:
                db.table("market_indices").upsert(
                    m, on_conflict="source,region,period,metric_name"
                ).execute()
                stats["metrics"] += 1
            except Exception:
                logger.exception(f"[sinapi] Failed to save: {m['metric_name']} {m['period']}")

        logger.info(f"[sinapi] Done: {stats['metrics']} metrics saved")

    except Exception:
        logger.exception("[sinapi] Failed to fetch SINAPI data")

    return stats


def get_latest_sinapi_cost() -> float:
    """Get the latest SINAPI cost/m² for SP. Falls back to default if unavailable."""
    db = get_client()
    try:
        result = (
            db.table("market_indices")
            .select("metric_value")
            .eq("source", "sinapi")
            .eq("metric_name", "sinapi_custo_m2")
            .eq("region", "sp")
            .order("period", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return float(result.data[0]["metric_value"])
    except Exception:
        pass
    return 1920.0  # Fallback: national average Jan 2026

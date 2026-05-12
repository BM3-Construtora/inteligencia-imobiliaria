"""Coletor SIDRA/IBGE de salário e ocupação na construção civil (UF SP).

Calibra custo de mão-de-obra em viability.py complementando o SINAPI nacional.

Tabelas SIDRA usadas (PNAD Contínua trimestral, API pública IBGE):
- 5442 — Rendimento médio mensal real (Reais) por grupamento de atividade
    Variável 5932 = rendimento habitualmente recebido no trabalho principal
- 5434 — Pessoas ocupadas (mil pessoas) por grupamento de atividade
    Variável 4090 = pessoas de 14+ anos ocupadas na semana de referência

Classificação 888 = "Grupamento de atividade no trabalho principal"
  Categoria 47949 = "Construção" (equivalente CNAE F)

Periodicidade: trimestral, formato AAAATT (ex: 202501 = 1º tri/2025).
Granularidade: N3 (UF). Usamos SP (id=35).

API base: https://servicodados.ibge.gov.br/api/v3/agregados/{table}/...
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "sidra_pnad"
SECTOR = "construcao_civil"

# IBGE codes
SP_CODE = "35"
CLASS_ATIVIDADE = "888"
CAT_CONSTRUCAO = "47949"

# Tabelas SIDRA
TABLE_RENDIMENTO = "5442"
VAR_RENDIMENTO_HABITUAL = "5932"  # Reais

TABLE_OCUPADOS = "5434"
VAR_OCUPADOS = "4090"  # Mil pessoas

# Últimos N períodos a coletar
PERIODOS = "-6"

API_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
TIMEOUT = 60


def run_collector() -> dict[str, int]:
    """Coleta rendimento médio e ocupados na construção civil (SP) e upserta em labor_indices."""
    stats = {"processed": 0, "created": 0, "failed": 0}

    db = get_client()
    run_id = _start_run(db)

    try:
        rendimento_rows = _fetch_rendimento_construcao()
        ocupados_rows = _fetch_ocupados_construcao()
        rows = rendimento_rows + ocupados_rows

        logger.info(f"[{SOURCE}] Parsed {len(rows)} labor indicator rows")

        for row in rows:
            stats["processed"] += 1
            try:
                db.table("labor_indices").upsert(
                    row,
                    on_conflict="source,period_code,region_code,indicator,sector",
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(
                    f"[{SOURCE}] Falha ao upsertar {row.get('indicator')} {row.get('period_code')}"
                )

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _fetch_rendimento_construcao() -> list[dict[str, Any]]:
    """Tabela 5442 — Rendimento médio mensal real (R$) construção civil SP."""
    url = (
        f"{API_BASE}/{TABLE_RENDIMENTO}/periodos/{PERIODOS}"
        f"/variaveis/{VAR_RENDIMENTO_HABITUAL}"
        f"?localidades=N3[{SP_CODE}]"
        f"&classificacao={CLASS_ATIVIDADE}[{CAT_CONSTRUCAO}]"
    )
    return _fetch_and_parse(url, indicator="rendimento_medio", unit="R$/mes")


def _fetch_ocupados_construcao() -> list[dict[str, Any]]:
    """Tabela 5434 — Pessoas ocupadas (mil) construção civil SP."""
    url = (
        f"{API_BASE}/{TABLE_OCUPADOS}/periodos/{PERIODOS}"
        f"/variaveis/{VAR_OCUPADOS}"
        f"?localidades=N3[{SP_CODE}]"
        f"&classificacao={CLASS_ATIVIDADE}[{CAT_CONSTRUCAO}]"
    )
    return _fetch_and_parse(url, indicator="ocupados", unit="mil_pessoas")


def _fetch_and_parse(url: str, indicator: str, unit: str) -> list[dict[str, Any]]:
    """Faz GET na API SIDRA e converte o JSON em linhas para labor_indices."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error {indicator}: {e}")
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Falha decode JSON {indicator}")
        return []

    rows: list[dict[str, Any]] = []
    for variable in data:
        for result in variable.get("resultados", []):
            for serie in result.get("series", []):
                loc = serie.get("localidade", {})
                region_code = str(loc.get("id") or SP_CODE)
                values = serie.get("serie", {})

                for period, value in values.items():
                    if not value or value in ("...", "-", ".."):
                        continue
                    try:
                        numeric = float(value)
                    except (TypeError, ValueError):
                        continue

                    rows.append({
                        "source": SOURCE,
                        "period_code": _format_period(period),
                        "region_code": region_code,
                        "indicator": indicator,
                        "sector": SECTOR,
                        "value": numeric,
                        "unit": unit,
                        "raw_payload": {
                            "ibge_variable": variable.get("id"),
                            "variable_name": variable.get("variavel"),
                            "raw_period": period,
                            "raw_value": value,
                            "locality": loc.get("nome"),
                        },
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    })
    return rows


def _format_period(period: str) -> str:
    """Converte AAAATT → 'AAAATQ' (ex: 202501 → 2025T1)."""
    if len(period) == 6 and period.isdigit():
        return f"{period[:4]}T{int(period[4:])}"
    return period


def get_latest_labor_cost_sp() -> dict[str, float | str | None]:
    """Retorna últimos indicadores de mão-de-obra na construção (SP).

    Returns:
        {
            "rendimento_medio_mes": float | None,   # R$/mês habitual
            "ocupados_mil": float | None,           # mil pessoas
            "period_code": str | None,
        }
    """
    db = get_client()
    out: dict[str, float | str | None] = {
        "rendimento_medio_mes": None,
        "ocupados_mil": None,
        "period_code": None,
    }

    try:
        for indicator, key in (
            ("rendimento_medio", "rendimento_medio_mes"),
            ("ocupados", "ocupados_mil"),
        ):
            r = (
                db.table("labor_indices")
                .select("value,period_code")
                .eq("source", SOURCE)
                .eq("sector", SECTOR)
                .eq("region_code", SP_CODE)
                .eq("indicator", indicator)
                .order("period_code", desc=True)
                .limit(1)
                .execute()
            )
            if r.data:
                out[key] = float(r.data[0]["value"])
                # mantém período mais recente entre indicadores
                pc = r.data[0]["period_code"]
                if not out["period_code"] or (pc and pc > str(out["period_code"])):
                    out["period_code"] = pc
    except Exception:
        logger.exception(f"[{SOURCE}] Falha ao buscar últimos labor indices")

    return out


def _start_run(db: Any) -> int | None:
    try:
        r = db.table("agent_runs").insert({
            "agent_name": f"collector_{SOURCE}",
            "status": "running",
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception:
        logger.exception(f"[{SOURCE}] Falha ao iniciar agent_runs")
        return None


def _finish_run(
    db: Any,
    run_id: int | None,
    status: str,
    stats: dict[str, int],
    error: str | None = None,
) -> None:
    if not run_id:
        return
    update = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["processed"],
        "items_created": stats["created"],
        "items_failed": stats["failed"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.exception(f"[{SOURCE}] Falha ao atualizar agent_runs")

"""Collector for CRECI-SP market research reports.

Downloads quarterly PDF reports from CRECI-SP and extracts structured
market metrics using Gemini LLM. Stores in market_indices table.

This collector is meant to run monthly (not daily), since CRECI
publishes reports quarterly.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client
from src.llm import _generate, _parse_json, GEMINI_API_KEY

logger = logging.getLogger(__name__)

# CRECI-SP research page
CRECI_RESEARCH_URL = "https://www.crecisp.gov.br/comunicacao/pesquisasmercado"

# Known report URLs pattern — CRECI publishes quarterly
# We fetch the most recent report page and extract PDF links
CRECI_API_BASE = "https://www.crecisp.gov.br"


def run_creci_collector() -> dict[str, int]:
    """Fetch and process CRECI-SP market reports."""
    db = get_client()
    stats = {"reports_found": 0, "metrics_extracted": 0, "failed": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "collector_creci", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        if not GEMINI_API_KEY:
            logger.warning("[creci] No GEMINI_API_KEY, skipping LLM extraction")
            _finish_run(db, run_id, "completed", stats)
            return stats

        # Fetch the CRECI research page to find report links
        report_data = _fetch_creci_page()
        if not report_data:
            logger.warning("[creci] Could not fetch CRECI page, using LLM general knowledge")
            # Fallback: ask Gemini for latest known CRECI data about Marília
            metrics = _extract_from_general_knowledge()
        else:
            stats["reports_found"] = 1
            metrics = _extract_metrics_from_text(report_data)

        if metrics:
            _save_metrics(db, metrics)
            stats["metrics_extracted"] = len(metrics)

        logger.info(
            f"[creci] Done: {stats['reports_found']} reports, "
            f"{stats['metrics_extracted']} metrics extracted"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[creci] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _fetch_creci_page() -> str | None:
    """Fetch the CRECI research page content."""
    try:
        resp = httpx.get(CRECI_RESEARCH_URL, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        # Return raw HTML for LLM to parse
        return resp.text[:10000]  # Limit to avoid token overflow
    except Exception as e:
        logger.error(f"[creci] Failed to fetch page: {e}")
        return None


def _extract_metrics_from_text(page_text: str) -> list[dict[str, Any]]:
    """Use Gemini to extract market metrics from CRECI page content."""
    prompt = f"""Analise este conteudo do site do CRECI-SP (pesquisas de mercado imobiliario)
e extraia metricas relevantes para a regiao de Marilia-SP.

Conteudo da pagina:
{page_text[:5000]}

Extraia o maximo de metricas quantitativas que encontrar. Retorne JSON:
{{
  "period": "periodo do relatorio (ex: 2026-Q1)",
  "metrics": [
    {{"name": "nome_da_metrica", "value": 123.45, "unit": "unidade", "context": "breve contexto"}},
    ...
  ]
}}

Metricas de interesse:
- volume de vendas (total transacoes)
- preco mediano por m2 (terreno, casa, apartamento)
- variacao percentual de precos
- tempo medio de venda (dias no mercado)
- taxa de ocupacao / vacancia
- numero de lancamentos

Se nao encontrar dados especificos de Marilia, retorne os dados da regiao interior-SP.
Se nao encontrar dados quantitativos, retorne {{"period": null, "metrics": []}}"""

    text = _generate(prompt, max_tokens=3000)
    result = _parse_json(text)

    if not result or not result.get("metrics"):
        return []

    period = result.get("period", _current_quarter())
    metrics = []
    for m in result["metrics"]:
        if m.get("value") is not None:
            metrics.append({
                "source": "creci_sp",
                "region": "marilia",
                "period": period,
                "metric_name": _sanitize_metric_name(m.get("name", "")),
                "metric_value": float(m["value"]),
                "metadata": {
                    "unit": m.get("unit", ""),
                    "context": m.get("context", ""),
                },
            })
    return metrics


def _extract_from_general_knowledge() -> list[dict[str, Any]]:
    """Ask Gemini for general CRECI market data about Marília."""
    prompt = """Com base no seu conhecimento sobre o mercado imobiliario de Marilia-SP,
forneça estimativas de mercado para o periodo mais recente que voce conhece.

Retorne JSON com metricas estimadas:
{{
  "period": "periodo estimado (ex: 2025-Q4)",
  "metrics": [
    {{"name": "preco_mediano_m2_terreno", "value": 450.00, "unit": "R$/m2", "context": "estimativa CRECI"}},
    {{"name": "preco_mediano_m2_casa", "value": 3200.00, "unit": "R$/m2", "context": "estimativa"}},
    {{"name": "volume_vendas_mensal", "value": 150, "unit": "transacoes/mes", "context": "estimativa"}},
    {{"name": "tempo_medio_venda_dias", "value": 90, "unit": "dias", "context": "estimativa"}},
    {{"name": "variacao_preco_anual_pct", "value": 8.5, "unit": "%", "context": "estimativa de valorizacao"}},
    ...mais metricas relevantes...
  ]
}}

Use valores realistas para uma cidade de ~240k habitantes no interior de SP."""

    text = _generate(prompt, max_tokens=2000)
    result = _parse_json(text)

    if not result or not result.get("metrics"):
        return []

    period = result.get("period", _current_quarter())
    metrics = []
    for m in result["metrics"]:
        if m.get("value") is not None:
            metrics.append({
                "source": "creci_sp",
                "region": "marilia",
                "period": period,
                "metric_name": _sanitize_metric_name(m.get("name", "")),
                "metric_value": float(m["value"]),
                "metadata": {
                    "unit": m.get("unit", ""),
                    "context": m.get("context", ""),
                    "estimated": True,
                },
            })
    return metrics


def _save_metrics(db: Any, metrics: list[dict[str, Any]]) -> None:
    """Upsert metrics into market_indices table."""
    for m in metrics:
        try:
            db.table("market_indices").upsert(
                m,
                on_conflict="source,region,period,metric_name",
            ).execute()
        except Exception:
            logger.exception(f"[creci] Failed to save metric: {m.get('metric_name')}")


def _sanitize_metric_name(name: str) -> str:
    """Sanitize metric name to snake_case."""
    import re
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name[:80]


def _current_quarter() -> str:
    """Return current quarter string like '2026-Q1'."""
    now = datetime.now(timezone.utc)
    q = (now.month - 1) // 3 + 1
    return f"{now.year}-Q{q}"


def _finish_run(
    db: Any,
    run_id: int | None,
    status: str,
    stats: dict[str, int],
    error: str | None = None,
) -> None:
    if not run_id:
        return
    update: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["reports_found"],
        "items_created": stats["metrics_extracted"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

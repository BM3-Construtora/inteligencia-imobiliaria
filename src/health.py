"""Health-check dos coletores — lê agent_runs e alerta quando algo quebra.

Motivação: `agent_runs` era escrito por todos os coletores mas lido por ninguém.
Um scraper que retorna 0 itens marcava status `completed` e o pipeline ficava
verde mesmo com a fonte quebrada (mudança de layout, bloqueio Cloudflare). Este
módulo fecha esse buraco: roda como último passo do pipeline, inspeciona as runs
das últimas 24h e dispara um alerta no Telegram quando encontra falha, run presa
ou coletor que voltou vazio.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org/bot{token}"

# Janela de análise e limite para considerar uma run "presa" em running.
LOOKBACK_HOURS = 24
STUCK_HOURS = 6


def _send_telegram(text: str) -> bool:
    """Envia um alerta de texto. Retorna True se enviou."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[health] TELEGRAM_BOT_TOKEN/CHAT_ID ausentes — alerta não enviado")
        return False
    url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("[health] Falha ao enviar alerta Telegram")
        return False


def _is_collector(agent_name: str) -> bool:
    return agent_name.startswith("collector_")


def _latest_run_per_agent(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduz as runs para a mais recente de cada agent_name (rows já vêm desc)."""
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.get("agent_name")
        if name and name not in latest:
            latest[name] = row
    return latest


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_agent_health(lookback_hours: int = LOOKBACK_HOURS) -> dict[str, Any]:
    """Inspeciona agent_runs recentes e retorna problemas encontrados.

    Categorias de problema:
    - failed:   status == 'failed'
    - stuck:    status == 'running' há mais de STUCK_HOURS
    - empty:    coletor com status 'completed' e 0 itens processados (falha silenciosa)
    """
    db = get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    result = (
        db.table("agent_runs")
        .select("agent_name, status, started_at, finished_at, items_processed, error_message")
        .gte("started_at", cutoff.isoformat())
        .order("started_at", desc=True)
        .execute()
    )
    rows = result.data or []
    latest = _latest_run_per_agent(rows)

    now = datetime.now(timezone.utc)
    failed: list[dict[str, Any]] = []
    stuck: list[dict[str, Any]] = []
    empty: list[dict[str, Any]] = []

    for name, run in latest.items():
        status = run.get("status")
        processed = run.get("items_processed") or 0

        if status == "failed":
            failed.append(run)
        elif status == "running":
            started = _parse_ts(run.get("started_at"))
            if started and (now - started) > timedelta(hours=STUCK_HOURS):
                stuck.append(run)
        elif status == "completed" and _is_collector(name) and processed == 0:
            empty.append(run)

    problems = failed + stuck + empty
    return {
        "checked": len(latest),
        "failed": failed,
        "stuck": stuck,
        "empty": empty,
        "problems": len(problems),
    }


def _format_alert(report: dict[str, Any]) -> str:
    lines = ["🚨 *Health-check dos coletores*", ""]

    def block(title: str, runs: list[dict[str, Any]], detail_key: Optional[str] = None) -> None:
        if not runs:
            return
        lines.append(f"*{title}* ({len(runs)}):")
        for run in runs:
            name = run.get("agent_name", "?")
            if detail_key == "error":
                err = (run.get("error_message") or "")[:120]
                lines.append(f"• `{name}` — {err}" if err else f"• `{name}`")
            elif detail_key == "started":
                lines.append(f"• `{name}` — desde {run.get('started_at', '?')}")
            else:
                lines.append(f"• `{name}`")
        lines.append("")

    block("Falharam", report["failed"], "error")
    block("Presas (running)", report["stuck"], "started")
    block("Voltaram vazias", report["empty"])
    lines.append(f"_{report['checked']} agentes verificados nas últimas {LOOKBACK_HOURS}h._")
    return "\n".join(lines).strip()


def run_health_check(alert: bool = True) -> dict[str, Any]:
    """Roda o health-check. Se `alert`, envia Telegram quando há problema.

    Sempre retorna o report. Não levanta exceção nem força saída não-zero: o
    objetivo é observabilidade, não derrubar o pipeline.
    """
    report = check_agent_health()

    if report["problems"] == 0:
        logger.info(f"[health] OK — {report['checked']} agentes, nenhum problema")
        return report

    logger.warning(
        f"[health] {report['problems']} problema(s): "
        f"{len(report['failed'])} falha, {len(report['stuck'])} presa, "
        f"{len(report['empty'])} vazia"
    )
    if alert:
        sent = _send_telegram(_format_alert(report))
        report["alert_sent"] = sent
    return report

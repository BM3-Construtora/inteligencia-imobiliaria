"""Reporter — drift report semanal (Track D).

Envia via Telegram o markdown gerado por `weekly_drift_report()` —
compara Hunter/AVM/Viability vs realidade e sugere ajustes de threshold.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client
from src.feedback_loop import weekly_drift_report

logger = logging.getLogger(__name__)


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > max_len:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def _send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.error("[reporter_drift] Telegram não configurado")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _split_message(text):
        resp = httpx.post(
            url,
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()


def _finish_run(
    db: Any,
    run_id: Optional[int],
    status: str,
    stats: dict[str, int],
    error: Optional[str] = None,
) -> None:
    if not run_id:
        return
    update: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats.get("generated", 0),
        "items_created": stats.get("sent", 0),
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception as exc:
        logger.debug(f"[reporter_drift] _finish_run falhou: {exc}")


def run_weekly_drift_report() -> dict[str, int]:
    """Gera o drift report e envia via Telegram."""
    db = get_client()
    stats = {"generated": 0, "sent": 0}

    run_id: Optional[int] = None
    try:
        run_result = (
            db.table("agent_runs")
            .insert({"agent_name": "reporter_drift", "status": "running"})
            .execute()
        )
        run_id = run_result.data[0]["id"] if run_result.data else None
    except Exception as exc:
        logger.debug(f"[reporter_drift] agent_runs insert falhou: {exc}")

    try:
        text = weekly_drift_report()
        stats["generated"] = 1
        if text:
            _send_telegram(text)
            stats["sent"] = 1
            logger.info("[reporter_drift] Drift report enviado")
        _finish_run(db, run_id, "completed", stats)
    except Exception as exc:
        logger.exception("[reporter_drift] Falhou")
        _finish_run(db, run_id, "failed", stats, str(exc))
        raise

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_weekly_drift_report())

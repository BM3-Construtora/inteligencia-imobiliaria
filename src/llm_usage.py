"""Telemetria de custo de LLM — extrai tokens da resposta Gemini e persiste.

Non-blocking: falhas de gravação são silenciosas (logadas, nunca levantadas),
igual ao src.audit. O objetivo é medir o gasto real para priorizar otimização
com dados, em vez de estimar às cegas.

Preços em USD por 1M de tokens (input, output). thinking/reasoning tokens são
cobrados na taxa de output no Gemini 2.5. Confira em ai.google.dev/pricing e
ajuste aqui se mudarem — este dict é a única fonte da estimativa de custo.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# (input_per_1M, output_per_1M) em USD. Match por prefixo tolera sufixos de
# versão, ex: "gemini-2.5-flash-002" cai em "gemini-2.5-flash".
PRICES: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash":      (0.30, 2.50),
    "gemini-2.5-pro":        (1.25, 10.00),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash":      (0.10, 0.40),
    "gemini-1.5-flash":      (0.075, 0.30),
    "text-embedding-004":    (0.0, 0.0),  # grátis no AI Studio
}
_DEFAULT_PRICE = (0.30, 2.50)  # assume flash quando o modelo é desconhecido


def _price_for(model: str) -> tuple[float, float]:
    """Preço (in, out) por 1M tokens. Match por prefixo mais longo primeiro."""
    if not model:
        return _DEFAULT_PRICE
    for prefix in sorted(PRICES, key=len, reverse=True):
        if model.startswith(prefix):
            return PRICES[prefix]
    return _DEFAULT_PRICE


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    output_tokens: int,
    thinking_tokens: int = 0,
) -> float:
    """Custo estimado em USD. Thinking tokens contam como output."""
    in_rate, out_rate = _price_for(model)
    billable_out = output_tokens + thinking_tokens
    return (prompt_tokens * in_rate + billable_out * out_rate) / 1_000_000


def extract_usage(response: Any) -> dict[str, int]:
    """Lê usage_metadata de uma resposta Gemini de forma defensiva.

    Nomes de campo do google-genai: prompt_token_count, candidates_token_count,
    thoughts_token_count, total_token_count. getattr protege contra variações
    de versão do SDK e respostas sem metadata.
    """
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return {"prompt_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "total_tokens": 0}

    def _get(*names: str) -> int:
        for n in names:
            val = getattr(meta, n, None)
            if isinstance(val, int):
                return val
        return 0

    prompt = _get("prompt_token_count")
    output = _get("candidates_token_count")
    thinking = _get("thoughts_token_count", "thinking_token_count")
    total = _get("total_token_count") or (prompt + output + thinking)
    return {
        "prompt_tokens": prompt,
        "output_tokens": output,
        "thinking_tokens": thinking,
        "total_tokens": total,
    }


def record_llm_usage(
    model: str,
    task: str,
    response: Any,
    llm_mode: Optional[str] = None,
    run_id: Optional[int] = None,
) -> None:
    """Registra o uso de uma chamada LLM. Non-blocking, nunca quebra o pipeline."""
    usage = extract_usage(response)
    if usage["total_tokens"] == 0:
        return  # nada a registrar (chamada falhou ou sem metadata)

    thread = threading.Thread(
        target=_write_usage,
        args=(model, task, usage, llm_mode, run_id),
        daemon=True,
    )
    thread.start()


def _write_usage(
    model: str,
    task: str,
    usage: dict[str, int],
    llm_mode: Optional[str],
    run_id: Optional[int],
) -> None:
    try:
        from src.db import get_client

        cost = estimate_cost_usd(
            model,
            usage["prompt_tokens"],
            usage["output_tokens"],
            usage["thinking_tokens"],
        )

        get_client().table("llm_usage").insert({
            "model":           model,
            "task":            task,
            "llm_mode":        llm_mode,
            "prompt_tokens":   usage["prompt_tokens"],
            "output_tokens":   usage["output_tokens"],
            "thinking_tokens": usage["thinking_tokens"],
            "total_tokens":    usage["total_tokens"],
            "est_cost_usd":    round(cost, 6),
            "run_id":          run_id,
        }).execute()
    except Exception:
        logger.debug("[llm_usage] Falha ao registrar uso", exc_info=True)


def report_usage(days: int = 30) -> dict[str, Any]:
    """Agrega e imprime o custo de LLM dos últimos `days` dias (por model+task)."""
    from src.db import get_client

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = (
            get_client()
            .table("llm_usage")
            .select("model,task,total_tokens,est_cost_usd")
            .gte("ts", since)
            .limit(100000)
            .execute()
            .data
            or []
        )
    except Exception:
        logger.warning("[llm_usage] Falha ao consultar llm_usage", exc_info=True)
        rows = []

    agg: dict[tuple[str, str], dict[str, float]] = {}
    for r in rows:
        key = (r.get("model") or "?", r.get("task") or "?")
        bucket = agg.setdefault(key, {"calls": 0, "tokens": 0, "cost": 0.0})
        bucket["calls"] += 1
        bucket["tokens"] += r.get("total_tokens") or 0
        bucket["cost"] += float(r.get("est_cost_usd") or 0)

    total_cost = sum(b["cost"] for b in agg.values())
    total_calls = sum(b["calls"] for b in agg.values())

    print(f"\n=== Custo LLM — últimos {days} dias ===")
    if not agg:
        print("(sem registros — a telemetria começa a popular após o próximo pipeline)")
    else:
        print(f"{'model':<24}{'task':<24}{'calls':>7}{'tokens':>12}{'USD':>10}")
        for (model, task), b in sorted(agg.items(), key=lambda kv: kv[1]["cost"], reverse=True):
            print(f"{model:<24}{task:<24}{int(b['calls']):>7}{int(b['tokens']):>12}{b['cost']:>10.4f}")
        print("-" * 77)
        print(f"{'TOTAL':<48}{total_calls:>7}{'':>12}{total_cost:>10.4f}")
        print(f"Projeção mensal (~30d): US$ {total_cost / days * 30:.2f}")

    return {"days": days, "total_cost_usd": round(total_cost, 4), "total_calls": total_calls}

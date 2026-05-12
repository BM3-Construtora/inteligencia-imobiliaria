"""Coleta processos de inventário em Marília-SP via DataJud CNJ.

API pública: https://api-publica.datajud.cnj.jus.br/
Endpoint usado: api_publica_tjsp/_search (Elasticsearch-like).

Auth: header "Authorization: APIKey <chave>" — o CNJ publica chave pública
fixa. Se requisição falhar, retorna 0 e segue.

Rate limit: batch pequeno (size=50). signal_type='heritage'.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "inventario_tjsp"
SIGNAL_TYPE = "heritage"
CITY = "Marília"
STATE = "SP"

DATAJUD_URL = (
    "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"
)

# Chave pública oficial divulgada pelo CNJ p/ acesso ao DataJud.
# Configurável via env caso seja rotacionada.
DATAJUD_API_KEY = os.getenv(
    "DATAJUD_API_KEY",
    "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==",
)

# Códigos de "classe processual" do CNJ:
#   1372 = Inventário
#   1473 = Arrolamento Comum
#   1432 = Arrolamento Sumário
CLASSE_CODES = [1372, 1473, 1432]

# Código IBGE de Marília-SP = 3529005 (3528502 é Mairiporã — bug fix 2026-05-11)
MARILIA_IBGE = 3529005

# LIMITAÇÃO 2026-05-11: Inventários no TJ-SP correm em segredo de justiça por
# padrão (art. 189 CPC). DataJud público NÃO indexa esses processos.
# Marília tem 10k+ processos públicos mas 0 das classes 1372/1473/1432 visíveis.
# Alternativas exploráveis:
#  - Diário de Justiça Eletrônico (DJE-SP): editais de citação de herdeiros
#  - Cartórios de registro civil (notícia de óbito + posterior abertura)
#  - Cartórios de notas (escritura pública de inventário extrajudicial)
# Mantemos o collector aqui como scaffold para quando uma dessas fontes for
# integrada — hoje retorna 0 silenciosamente.

BATCH_SIZE = 50
TIMEOUT = 30


def run_collector() -> dict[str, int]:
    """Busca processos de inventário em Marília e upserta em off_market_signals."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        hits = _fetch_inventarios()
        logger.info(f"[{SOURCE}] Fetched {len(hits)} processos")

        for hit in hits:
            stats["processed"] += 1
            try:
                payload = _to_signal_row(hit)
                if not payload:
                    continue
                db.table("off_market_signals").upsert(
                    payload, on_conflict="source,source_id"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] Failed to upsert hit")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _fetch_inventarios() -> list[dict[str, Any]]:
    """Consulta DataJud por classes de inventário em Marília."""
    headers = {
        "Authorization": f"APIKey {DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    query = {
        "size": BATCH_SIZE,
        "query": {
            "bool": {
                "must": [
                    {"terms": {"classe.codigo": CLASSE_CODES}},
                    {
                        "term": {
                            "orgaoJulgador.codigoMunicipioIBGE": MARILIA_IBGE
                        }
                    },
                ]
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
    }

    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            resp = c.post(DATAJUD_URL, headers=headers, json=query)
            if resp.status_code != 200:
                logger.warning(
                    f"[{SOURCE}] HTTP {resp.status_code} — DataJud indisponível: "
                    f"{resp.text[:200]}"
                )
                return []
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error: {e}")
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Failed to parse DataJud response")
        return []

    hits = data.get("hits", {}).get("hits", []) or []
    return hits


def _to_signal_row(hit: dict[str, Any]) -> dict[str, Any] | None:
    src = hit.get("_source") or {}
    proc_num = src.get("numeroProcesso") or hit.get("_id")
    if not proc_num:
        return None

    classe = (src.get("classe") or {}).get("nome") or "Inventário"
    orgao = (src.get("orgaoJulgador") or {}).get("nome")
    event_date = src.get("dataAjuizamento")

    # Movimentações recentes — pega últimas para descrição
    movimentos = src.get("movimentos") or []
    last_mov = ""
    if movimentos:
        last = movimentos[-1]
        last_mov = (last.get("nome") or "")[:200]

    description_parts = [classe]
    if orgao:
        description_parts.append(orgao)
    if last_mov:
        description_parts.append(f"último mov.: {last_mov}")
    description = " — ".join(description_parts)

    now = datetime.now(timezone.utc).isoformat()
    return {
        "source": SOURCE,
        "source_id": str(proc_num),
        "signal_type": SIGNAL_TYPE,
        "title": f"{classe} — TJ-SP Marília",
        "description": description,
        "city": CITY,
        "state": STATE,
        "event_date": event_date,
        "url": (
            f"https://esaj.tjsp.jus.br/cposg/search.do?conversationId="
            f"&dadosConsulta.valorConsulta={proc_num}"
        ),
        "raw_payload": src,
        "last_seen_at": now,
        "is_active": True,
    }


def _start_run(db: Any) -> int | None:
    try:
        r = db.table("agent_runs").insert({
            "agent_name": f"collector_{SOURCE}",
            "status": "running",
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception:
        logger.exception(f"[{SOURCE}] Failed to start agent_runs")
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
        logger.exception(f"[{SOURCE}] Failed to update agent_runs")

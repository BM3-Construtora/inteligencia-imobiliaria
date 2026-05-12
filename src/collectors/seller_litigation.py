"""Collector — histórico de litígio do vendedor via DataJud (CNJ).

DataJud expõe API pública de consulta processual nos tribunais. Buscamos processos
onde a parte (autor ou réu) seja o CPF/CNPJ informado. Resultado é gravado em
`seller_history` indexado pelo sha256 do documento normalizado.

Política: rate limit polite (1s entre chamadas), try/except em torno de tudo,
falha externa → log warning + skip (nunca raise).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

# DataJud CNJ — endpoint público de busca processual.
# Tribunais de SP onde litígios imobiliários ficam concentrados.
DATAJUD_BASE = os.getenv(
    "DATAJUD_API_URL",
    "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search",
)
DATAJUD_API_KEY = os.getenv("DATAJUD_API_KEY", "")  # chave pública oficial do CNJ
REQUEST_DELAY_S = 1.0
REQUEST_TIMEOUT_S = 25


def _normalize_doc(doc: str) -> str:
    """Mantém só dígitos."""
    return re.sub(r"\D", "", doc or "")


def _doc_hash(doc: str) -> str:
    norm = _normalize_doc(doc)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _classify_doc(doc: str) -> str:
    """Retorna 'pf' se 11 dígitos, 'pj' se 14, else 'pj' (default)."""
    digits = _normalize_doc(doc)
    if len(digits) == 11:
        return "pf"
    if len(digits) == 14:
        return "pj"
    return "pj"


def _datajud_search(doc: str) -> Optional[dict[str, Any]]:
    """Chama DataJud buscando processos onde a parte contenha o documento.

    Returns:
        Raw JSON da resposta, ou None em qualquer falha.
    """
    digits = _normalize_doc(doc)
    if not digits:
        return None

    headers = {"Content-Type": "application/json"}
    if DATAJUD_API_KEY:
        headers["Authorization"] = f"APIKey {DATAJUD_API_KEY}"

    # Query Elasticsearch — busca em campos free-text das partes processuais.
    payload = {
        "size": 50,
        "query": {
            "bool": {
                "should": [
                    {"match_phrase": {"partes.documento": digits}},
                    {"match_phrase": {"partes.cpfCnpj": digits}},
                    {"query_string": {"query": digits}},
                ],
                "minimum_should_match": 1,
            }
        },
        "sort": [{"dataAjuizamento": {"order": "desc"}}],
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_S) as c:
            resp = c.post(DATAJUD_BASE, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    f"[litigation] DataJud HTTP {resp.status_code} for {digits[:4]}***"
                )
                return None
            return resp.json()
    except Exception:
        logger.warning("[litigation] DataJud request failed", exc_info=True)
        return None


def _parse_datajud(raw: dict[str, Any]) -> dict[str, Any]:
    """Extrai count + última data + sumário dos hits."""
    hits = (raw.get("hits") or {}).get("hits") or []
    count = len(hits)
    last_dt: Optional[str] = None
    summary: list[dict[str, Any]] = []
    for h in hits[:20]:
        src = h.get("_source") or {}
        proc = {
            "numero": src.get("numeroProcesso"),
            "classe": (src.get("classe") or {}).get("nome"),
            "tribunal": src.get("tribunal"),
            "data": src.get("dataAjuizamento"),
        }
        summary.append(proc)
        d = src.get("dataAjuizamento")
        if d and (last_dt is None or d > last_dt):
            last_dt = d
    return {
        "litigation_count": count,
        "last_litigation_at": last_dt,
        "summary": summary,
    }


def check_cnpj_cpf(doc: str) -> dict[str, Any]:
    """Consulta DataJud por processos da pessoa/empresa.

    Args:
        doc: CPF ou CNPJ (com ou sem máscara).

    Returns:
        {"litigation_count": int, "last_litigation_at": iso|None, "summary": list}
        Sempre retorna dict — em falha, count=0 e summary vazio.
    """
    raw = _datajud_search(doc)
    if not raw:
        return {"litigation_count": 0, "last_litigation_at": None, "summary": []}
    try:
        return _parse_datajud(raw)
    except Exception:
        logger.warning("[litigation] parse failed", exc_info=True)
        return {"litigation_count": 0, "last_litigation_at": None, "summary": []}


def update_seller_history(docs: list[str]) -> dict[str, int]:
    """Consulta DataJud para uma lista de docs e atualiza seller_history em batch.

    Args:
        docs: lista de CPF/CNPJ (raw, qualquer formato).

    Returns:
        {"queried": int, "updated": int, "with_litigation": int, "failed": int}
    """
    db = get_client()
    stats = {"queried": 0, "updated": 0, "with_litigation": 0, "failed": 0}

    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    for doc in docs:
        digits = _normalize_doc(doc)
        if not digits or digits in seen:
            continue
        seen.add(digits)

        stats["queried"] += 1
        result = check_cnpj_cpf(digits)
        try:
            row = {
                "doc_hash": _doc_hash(digits),
                "seller_type": _classify_doc(digits),
                "litigation_count": int(result.get("litigation_count") or 0),
                "last_litigation_at": result.get("last_litigation_at"),
                "complaints": result.get("summary") or [],
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(row)
            if row["litigation_count"] > 0:
                stats["with_litigation"] += 1
        except Exception:
            stats["failed"] += 1
            logger.warning("[litigation] row build failed", exc_info=True)

        time.sleep(REQUEST_DELAY_S)

    if rows:
        try:
            db.table("seller_history").upsert(
                rows, on_conflict="doc_hash"
            ).execute()
            stats["updated"] = len(rows)
        except Exception:
            logger.warning("[litigation] batch upsert failed", exc_info=True)
            stats["failed"] += len(rows)

    logger.info(f"[litigation] {stats}")
    return stats

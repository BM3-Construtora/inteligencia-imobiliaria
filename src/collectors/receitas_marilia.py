"""Coleta Receitas Analíticas mensais da Prefeitura de Marília-SP.

Fonte: paiportalserver (API interna do Portal de Transparência)
  POST https://transparencia.marilia.sp.gov.br/paiportalserver/modulovisao/filter

Tipos de receita coletados:
  - ITBI (Imposto de Transmissão de Bens Imóveis): proxy de volume de transações
  - Taxa de Licença para Execução de Obras: proxy de alvarás emitidos

Cada registro é um lançamento individual com data e valor. Útil como índice
de aquecimento do mercado (ITBI) e atividade de construção (obras).

Configuração (opcional):
  RECEITAS_START_YEAR  — ano inicial (default: 2021)
  RECEITAS_END_YEAR    — ano final (default: ano atual)
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "receitas_marilia"
CITY = "Marília"
STATE = "SP"

FILTER_URL = "https://transparencia.marilia.sp.gov.br/paiportalserver/modulovisao/filter"
CHAVE_MODULO = "folha_pagamento_detalhes"
NOME_VISAO = "ReceitaAnalitica"

_THIS_YEAR = datetime.now().year
RECEITAS_START_YEAR = int(os.getenv("RECEITAS_START_YEAR", "2021"))
RECEITAS_END_YEAR = int(os.getenv("RECEITAS_END_YEAR", str(_THIS_YEAR)))

# Exact strings returned by the API (case-insensitive match used)
DESCRICOES_ALVO = [
    "TAXA DE LICENCA PARA EXECUCAO DE OBRAS",
    "ITBI",
]

MESES = [
    "JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO",
    "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
    "Content-Type": "application/json",
    "Origin": "https://transparencia.marilia.sp.gov.br",
    "Referer": "https://transparencia.marilia.sp.gov.br/",
}
TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.5
PAGE_SIZE = 100


def run_collector() -> dict[str, int]:
    """Coleta receitas analíticas e upserta em receitas_marilia."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        records = _collect_all()
        logger.info(f"[{SOURCE}] Total registros encontrados: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("receitas_marilia").upsert(
                    _to_row(rec), on_conflict="source_id"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] upsert falhou: {rec.get('source_id')}")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector falhou")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


# ---------------------------------------------------------------------------
# Coleta
# ---------------------------------------------------------------------------

def _collect_all() -> list[dict[str, Any]]:
    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        for year in range(RECEITAS_START_YEAR, RECEITAS_END_YEAR + 1):
            max_month = 12 if year < _THIS_YEAR else datetime.now().month
            for mes_idx in range(max_month):
                mes_nome = MESES[mes_idx]
                for descricao in DESCRICOES_ALVO:
                    recs = _collect_month(client, year, mes_idx + 1, mes_nome, descricao)
                    for r in recs:
                        sid = r["source_id"]
                        if sid not in seen_ids:
                            seen_ids.add(sid)
                            all_records.append(r)
                    time.sleep(SLEEP_BETWEEN_REQUESTS)

            logger.info(f"[{SOURCE}] Ano {year}: {sum(1 for r in all_records if r['exercicio'] == year)} registros")

    return all_records


def _collect_month(
    client: httpx.Client,
    year: int,
    mes_num: int,
    mes_nome: str,
    descricao: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1

    while True:
        payload = {
            "ChaveModulo": CHAVE_MODULO,
            "NomeVisao": NOME_VISAO,
            "Filtros": [{"Campo": "DescricaoReceita", "Valor": descricao, "TipoValor": 8}],
            "Periodicidade": "MENSAL",
            "Periodo": mes_nome,
            "Exercicio": year,
            "Pagina": page,
            "QuantidadeRegistros": str(PAGE_SIZE),
            "Ordenacao": [{"ColunaOrdem": "DataMovto", "TipoOrdem": "ascend", "Ordem": 1}],
            "FiltroRedirecionaVisao": {"Campo": None, "Valor": None, "TipoValor": None},
        }
        try:
            resp = client.post(FILTER_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception(
                f"[{SOURCE}] Erro ao buscar {descricao} {mes_nome}/{year} pág {page}"
            )
            break

        valores = data.get("Valores") or []
        total_pages = data.get("QuantidadePaginas") or 1

        for item in valores:
            rec = _parse_item(item, year, mes_num, descricao)
            records.append(rec)

        if page >= total_pages or not valores:
            break
        page += 1
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    return records


def _parse_item(item: dict[str, Any], year: int, mes_num: int, descricao_alvo: str) -> dict[str, Any]:
    source_id = str(item.get("Id") or item.get("ID") or "")
    if not source_id:
        import hashlib
        source_id = hashlib.sha1(str(item).encode()).hexdigest()[:16]

    return {
        "source_id": source_id,
        "api_id": _to_int(item.get("ID")),
        "exercicio": year,
        "mes": mes_num,
        "descricao_receita": (item.get("DescricaoReceita") or "").strip(),
        "natureza_receita": (item.get("NaturezaReceita") or "").strip() or None,
        "unidade_gestora": (item.get("UnidadeGestora") or "").strip() or None,
        "vinculo": (item.get("Vinculo") or "").strip() or None,
        "descricao_vinculo": (item.get("DescricaoVinculo") or "").strip() or None,
        "nome_banco": (item.get("NomeBanco") or "").strip() or None,
        "operacao": (item.get("Operacao") or "").strip() or None,
        "data_movto": _parse_date_movto(item.get("DataMovto")),
        "valor": _parse_valor(item.get("Valor")),
        "raw_payload": item,
    }


def _parse_date_movto(raw: Any) -> str | None:
    if not raw:
        return None
    s = str(raw)[:10]
    # API returns "dd/mm/yyyy HH:MM" or "yyyy-mm-dd"
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_valor(raw: Any) -> float | None:
    if not raw:
        return None
    s = str(raw).strip()
    try:
        # Brazilian format: "3.526,05" → 3526.05
        cleaned = s.replace(".", "").replace(",", ".")
        return float(cleaned)
    except ValueError:
        return None


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": rec["source_id"],
        "api_id": rec.get("api_id"),
        "exercicio": rec["exercicio"],
        "mes": rec["mes"],
        "descricao_receita": rec["descricao_receita"],
        "natureza_receita": rec.get("natureza_receita"),
        "unidade_gestora": rec.get("unidade_gestora"),
        "vinculo": rec.get("vinculo"),
        "descricao_vinculo": rec.get("descricao_vinculo"),
        "nome_banco": rec.get("nome_banco"),
        "operacao": rec.get("operacao"),
        "data_movto": rec.get("data_movto"),
        "valor": rec.get("valor"),
        "raw_payload": rec.get("raw_payload"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
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


# ---------------------------------------------------------------------------
# Helpers para uso externo (AVM / viability)
# ---------------------------------------------------------------------------

def itbi_mensal(year: int, mes: int, db: Any = None) -> dict[str, Any]:
    """Retorna total e count de ITBI para um mês/ano.

    Útil como índice de calor do mercado:
        heat = itbi_mensal(2026, 3)["total_valor"]
    """
    if db is None:
        db = get_client()
    try:
        r = (
            db.table("receitas_marilia")
            .select("valor")
            .ilike("descricao_receita", "%ITBI%")
            .eq("exercicio", year)
            .eq("mes", mes)
            .execute()
        )
        rows = r.data or []
        valores = [row["valor"] for row in rows if row.get("valor")]
        return {
            "count": len(valores),
            "total_valor": sum(valores),
            "year": year,
            "mes": mes,
        }
    except Exception:
        logger.exception(f"[{SOURCE}] itbi_mensal falhou")
        return {"count": 0, "total_valor": 0.0, "year": year, "mes": mes}


def alvaras_mensal(year: int, mes: int, db: Any = None) -> dict[str, Any]:
    """Retorna total e count de taxas de licença de obras para um mês/ano."""
    if db is None:
        db = get_client()
    try:
        r = (
            db.table("receitas_marilia")
            .select("valor")
            .ilike("descricao_receita", "%LICENCA%OBRAS%")
            .eq("exercicio", year)
            .eq("mes", mes)
            .execute()
        )
        rows = r.data or []
        valores = [row["valor"] for row in rows if row.get("valor")]
        return {
            "count": len(valores),
            "total_valor": sum(valores),
            "year": year,
            "mes": mes,
        }
    except Exception:
        logger.exception(f"[{SOURCE}] alvaras_mensal falhou")
        return {"count": 0, "total_valor": 0.0, "year": year, "mes": mes}

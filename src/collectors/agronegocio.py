"""Coletor de índice do agronegócio (soja/milho) para Marília-SP.

Fonte primária: CEPEA ESALQ-USP (scraping HTML)
  - Soja:  https://www.cepea.esalq.usp.br/br/indicador/soja.aspx
  - Milho: https://www.cepea.esalq.usp.br/br/indicador/milho.aspx

Fallback: tabela `safra_calendar` no banco (calendário histórico por mês).

Tabela destino: `agronegocio_index`
  - reference_date DATE UNIQUE
  - cultura TEXT
  - preco_saca NUMERIC (nullable)
  - variacao_pct NUMERIC (nullable)
  - fase_safra TEXT
  - indice_compra NUMERIC (0-100)
  - source TEXT
  - collected_at TIMESTAMPTZ

Contexto: ~30% das compras imobiliárias em Marília correlacionadas com
pagamento de safra soja/milho (março-junho). O `indice_compra` é usado
como feature em price_model.py via `get_current_agronegocio_index()`.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE_CEPEA = "cepea_esalq"
SOURCE_FALLBACK = "safra_calendar_fallback"

CULTURAS = {
    "soja": "https://www.cepea.esalq.usp.br/br/indicador/soja.aspx",
    "milho": "https://www.cepea.esalq.usp.br/br/indicador/milho.aspx",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
TIMEOUT = 30

# Ajuste no indice_compra quando preço atual desvia da média histórica
PRECO_BONUS = 10.0
PRECO_PENALTY = 10.0


# ---------------------------------------------------------------------------
# Ponto de entrada principal
# ---------------------------------------------------------------------------

def run_agronegocio_collector() -> dict[str, int]:
    """Coleta preços CEPEA (soja e milho) e upserta em agronegocio_index.

    Returns:
        dict com chaves 'processed', 'created', 'failed'.
    """
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    today = date.today()

    try:
        safra_info = _get_safra_calendar(db, today.month)

        for cultura, url in CULTURAS.items():
            stats["processed"] += 1
            try:
                row = _collect_cultura(db, cultura, url, today, safra_info)
                db.table("agronegocio_index").upsert(
                    row,
                    on_conflict="reference_date,cultura",
                ).execute()
                stats["created"] += 1
                logger.info(
                    f"[agronegocio] {cultura} upserted "
                    f"preco={row.get('preco_saca')} indice={row['indice_compra']:.1f} "
                    f"source={row['source']}"
                )
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[agronegocio] Falha ao processar cultura={cultura}")

        logger.info(
            f"[agronegocio] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[agronegocio] Collector falhou inesperadamente")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


# ---------------------------------------------------------------------------
# Coleta por cultura
# ---------------------------------------------------------------------------

def _collect_cultura(
    db: Any,
    cultura: str,
    url: str,
    ref_date: date,
    safra_info: dict[str, Any],
) -> dict[str, Any]:
    """Tenta scraping CEPEA; em caso de falha usa fallback do safra_calendar."""
    try:
        preco, data_preco = _scrape_cepea(url, cultura)
        variacao = _calc_variacao(db, cultura, preco)
        media_hist = _get_media_historica(db, cultura)
        ajuste = _ajuste_preco(preco, media_hist)
        indice_base = float(safra_info.get("indice_compra_historico") or 50.0)
        indice_compra = max(0.0, min(100.0, indice_base + ajuste))

        return {
            "reference_date": (data_preco or ref_date).isoformat(),
            "cultura": cultura,
            "preco_saca": preco,
            "variacao_pct": variacao,
            "fase_safra": safra_info.get("fase_soja") if cultura == "soja" else safra_info.get("fase_milho"),
            "indice_compra": round(indice_compra, 2),
            "source": SOURCE_CEPEA,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.warning(f"[agronegocio] Scraping falhou para {cultura}: {exc}; usando fallback")
        indice_base = float(safra_info.get("indice_compra_historico") or 50.0)
        fase = safra_info.get("fase_soja") if cultura == "soja" else safra_info.get("fase_milho")

        return {
            "reference_date": ref_date.isoformat(),
            "cultura": cultura,
            "preco_saca": None,
            "variacao_pct": None,
            "fase_safra": fase,
            "indice_compra": round(indice_base, 2),
            "source": SOURCE_FALLBACK,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Scraping CEPEA ESALQ-USP
# ---------------------------------------------------------------------------

def _scrape_cepea(url: str, cultura: str) -> tuple[float, date | None]:
    """Faz scraping da tabela de preços CEPEA e retorna (preco_saca, data).

    Raises:
        ValueError: se não encontrar preço válido na página.
        httpx.HTTPError: em falhas de rede.
    """
    resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # CEPEA usa tabelas com id="imagenet-indicador1" ou class contendo "tbClima"
    table = (
        soup.find("table", {"id": "imagenet-indicador1"})
        or soup.find("table", class_=re.compile(r"tbClima", re.I))
        or soup.find("table", class_=re.compile(r"indicador", re.I))
    )

    if table is None:
        # última tentativa: primeira tabela com dados numéricos
        for t in soup.find_all("table"):
            if t.find("td", string=re.compile(r"\d+[,\.]\d+")):
                table = t
                break

    if table is None:
        raise ValueError(f"Tabela de preços não encontrada na página CEPEA ({cultura})")

    rows = table.find_all("tr")
    for row in rows[1:]:  # pula header
        cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if not cols:
            continue

        # Busca coluna com valor numérico no formato "1.234,56" ou "1234.56"
        preco: float | None = None
        data_preco: date | None = None

        for col in cols:
            # Tenta parse de data DD/MM/AAAA
            if data_preco is None:
                m = re.match(r"(\d{2})/(\d{2})/(\d{4})", col)
                if m:
                    try:
                        data_preco = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                    except ValueError:
                        pass

            # Tenta parse de preço (formato BR: ponto=milhar, vírgula=decimal)
            if preco is None:
                clean = col.replace(".", "").replace(",", ".")
                clean = re.sub(r"[^\d\.]", "", clean)
                if clean and re.match(r"^\d+\.?\d*$", clean):
                    candidate = float(clean)
                    # Preços de soja/milho em R$/sc ficam entre R$10 e R$3.000
                    if 10 < candidate < 3000:
                        preco = candidate

        if preco is not None:
            return preco, data_preco

    raise ValueError(f"Nenhum preço válido encontrado na tabela CEPEA ({cultura})")


# ---------------------------------------------------------------------------
# Cálculos auxiliares
# ---------------------------------------------------------------------------

def _calc_variacao(db: Any, cultura: str, preco_atual: float) -> float | None:
    """Variação percentual vs. último registro no banco para a cultura."""
    try:
        r = (
            db.table("agronegocio_index")
            .select("preco_saca")
            .eq("cultura", cultura)
            .not_.is_("preco_saca", "null")
            .order("reference_date", desc=True)
            .limit(1)
            .execute()
        )
        if r.data and r.data[0]["preco_saca"]:
            preco_anterior = float(r.data[0]["preco_saca"])
            if preco_anterior > 0:
                return round((preco_atual - preco_anterior) / preco_anterior * 100, 4)
    except Exception:
        logger.warning(f"[agronegocio] Não foi possível calcular variação para {cultura}")
    return None


def _get_media_historica(db: Any, cultura: str) -> float | None:
    """Média de preco_saca dos últimos 12 registros com preço no banco."""
    try:
        r = (
            db.table("agronegocio_index")
            .select("preco_saca")
            .eq("cultura", cultura)
            .not_.is_("preco_saca", "null")
            .order("reference_date", desc=True)
            .limit(12)
            .execute()
        )
        precos = [float(row["preco_saca"]) for row in r.data if row.get("preco_saca")]
        if precos:
            return sum(precos) / len(precos)
    except Exception:
        logger.warning(f"[agronegocio] Não foi possível calcular média histórica para {cultura}")
    return None


def _ajuste_preco(preco_atual: float | None, media_hist: float | None) -> float:
    """Retorna +PRECO_BONUS se acima da média, -PRECO_PENALTY se abaixo, 0 se inconclusivo."""
    if preco_atual is None or media_hist is None or media_hist == 0:
        return 0.0
    if preco_atual > media_hist:
        return PRECO_BONUS
    if preco_atual < media_hist:
        return -PRECO_PENALTY
    return 0.0


def _get_safra_calendar(db: Any, mes: int) -> dict[str, Any]:
    """Retorna linha do safra_calendar para o mês corrente."""
    try:
        r = (
            db.table("safra_calendar")
            .select("mes,fase_soja,fase_milho,indice_compra_historico")
            .eq("mes", mes)
            .limit(1)
            .execute()
        )
        if r.data:
            return r.data[0]
    except Exception:
        logger.warning(f"[agronegocio] Falha ao consultar safra_calendar para mes={mes}")
    return {
        "mes": mes,
        "fase_soja": None,
        "fase_milho": None,
        "indice_compra_historico": 50.0,
    }


# ---------------------------------------------------------------------------
# API pública: usado por price_model.py
# ---------------------------------------------------------------------------

def get_current_agronegocio_index(db: Any | None = None) -> float:
    """Retorna o indice_compra mais recente de agronegocio_index.

    Considera a média entre soja e milho do registro mais recente.
    Retorna 50.0 como default se nenhum dado disponível.

    Args:
        db: cliente Supabase (opcional; se None, chama get_client()).
    """
    _db = db or get_client()
    try:
        r = (
            _db.table("agronegocio_index")
            .select("cultura,indice_compra,reference_date")
            .order("reference_date", desc=True)
            .limit(4)
            .execute()
        )
        if not r.data:
            return 50.0

        # Agrupa pelo reference_date mais recente disponível para cada cultura
        latest: dict[str, float] = {}
        for row in r.data:
            cultura = row["cultura"]
            if cultura not in latest and row.get("indice_compra") is not None:
                latest[cultura] = float(row["indice_compra"])

        if not latest:
            return 50.0

        return round(sum(latest.values()) / len(latest), 2)

    except Exception:
        logger.exception("[agronegocio] Falha ao buscar indice_compra atual")
        return 50.0


# ---------------------------------------------------------------------------
# agent_runs helpers
# ---------------------------------------------------------------------------

def _start_run(db: Any) -> int | None:
    try:
        r = db.table("agent_runs").insert({
            "agent_name": "collector_agronegocio",
            "status": "running",
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception:
        logger.exception("[agronegocio] Falha ao iniciar agent_runs")
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
    update: dict[str, Any] = {
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
        logger.exception("[agronegocio] Falha ao atualizar agent_runs")

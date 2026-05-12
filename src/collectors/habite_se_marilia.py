"""Coleta Habite-se (certificados de conclusão de obra) — Marília-SP.

Status da fonte (pesquisa 2026-05):
- Diário Oficial do Município de Marília: https://www.marilia.sp.gov.br/portal/diario-oficial
  (URL canônica também espelhada em diariooficial.marilia.sp.gov.br)
- Não foi localizado endpoint público estruturado (RSS/JSON/API) listando
  exclusivamente Habite-se. A prática observada é que o município publica os
  certificados como atos da Secretaria de Planejamento Urbano dentro das edições
  diárias em PDF.
- Estratégia: parsear PDFs do DOM-MAR procurando blocos "HABITE-SE",
  "CERTIFICADO DE CONCLUSÃO" ou "VISTORIA FINAL".
- Caso seja necessário acesso retroativo estruturado, abrir LAI à Secretaria de
  Planejamento Urbano (Lei 12.527/2011).

Configuração:
- Env `HABITE_SE_FEED_URL` aponta para a edição/listagem PDF/HTML a ser parseada.
  Pode ser uma URL única (edição mais recente) ou um índice HTML cujo conteúdo
  será raspado em busca dos termos-chave.
- Sem URL setada, faz log warning e retorna stats zerados (não falha).

Cruzamento com alvará:
- O coletor tenta extrair `process_number` do snippet; quando casa com
  off_market_signals.source_id (signal_type='permit') do `alvara_prefeitura`,
  preenche `alvara_reference` permitindo calcular prazo médio (issue_date do
  habite-se vs event_date do alvará) e custo real por região.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "habite_se_marilia"
CITY = "Marília"
STATE = "SP"

HABITE_SE_FEED_URL = os.getenv("HABITE_SE_FEED_URL", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
TIMEOUT = 60

# Termos que indicam um bloco de Habite-se no Diário Oficial.
RE_HABITE = re.compile(
    r"(habite[-\s]?se|certificado de conclus[ãa]o(?: de obra| parcial| total)?|vistoria final)"
    r"[^\n]{0,400}",
    re.IGNORECASE,
)
RE_PROCESSO = re.compile(
    r"(?:processo|protocolo|proc\.?)\s*[:nº#]*\s*([\d\./-]{4,})",
    re.IGNORECASE,
)
RE_AREA_BUILT = re.compile(
    r"(?:[áa]rea\s+(?:constru[íi]da|edificada)|a\.?c\.?)\s*[:=]?\s*"
    r"(\d{1,5}(?:[\.,]\d{1,3})?)\s*m[²2]",
    re.IGNORECASE,
)
RE_AREA_TERRAIN = re.compile(
    r"(?:[áa]rea\s+(?:do\s+)?terreno|a\.?t\.?)\s*[:=]?\s*"
    r"(\d{1,6}(?:[\.,]\d{1,3})?)\s*m[²2]",
    re.IGNORECASE,
)
RE_COST = re.compile(
    r"(?:custo\s+declarado|valor\s+(?:declarado|da\s+obra|estimado))"
    r"[^\d]{0,30}r?\$?\s*([\d\.]+,\d{2})",
    re.IGNORECASE,
)
RE_DATE = re.compile(
    r"(\d{2})/(\d{2})/(\d{4})"
)
RE_NEIGHBORHOOD = re.compile(
    r"(?:bairro|jardim|jd\.?|parque|vila|conjunto)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s]{2,40})",
)
RE_ADDRESS = re.compile(
    r"(?:rua|avenida|av\.?|travessa|alameda|al\.?|estrada|praça)\s+"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w\s\.,Áéíóúâêôãõç-]{3,80}(?:\d{1,5})?",
    re.IGNORECASE,
)


def run_collector() -> dict[str, int]:
    """Coleta Habite-se publicados e upserta em habite_se_records."""
    stats = {"processed": 0, "created": 0, "failed": 0}

    if not HABITE_SE_FEED_URL:
        logger.warning(
            f"[{SOURCE}] HABITE_SE_FEED_URL não configurada — pulando coleta"
        )
        return stats

    db = get_client()
    run_id = _start_run(db)

    try:
        content, ct = _download(HABITE_SE_FEED_URL)
        if not content:
            _finish_run(db, run_id, "completed", stats)
            return stats

        records = _parse(content, ct)
        logger.info(f"[{SOURCE}] Parsed {len(records)} habite-se records")

        # Carrega alvarás existentes para cruzar por número de processo (1 query).
        alvara_index = _load_alvara_index(db)

        for rec in records:
            stats["processed"] += 1
            try:
                rec["alvara_reference"] = _match_alvara(rec, alvara_index)
                payload = _to_row(rec)
                db.table("habite_se_records").upsert(
                    payload, on_conflict="source_id"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] Failed to upsert record")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector failed")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _download(url: str) -> tuple[bytes, str]:
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            resp = c.get(url)
            if resp.status_code != 200:
                logger.warning(f"[{SOURCE}] HTTP {resp.status_code}")
                return b"", ""
            return resp.content, resp.headers.get("content-type", "")
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error: {e}")
        return b"", ""


def _parse(content: bytes, content_type: str) -> list[dict[str, Any]]:
    ct = (content_type or "").lower()
    is_pdf = "pdf" in ct or content[:4] == b"%PDF"

    if is_pdf:
        text = _pdf_to_text(content)
    else:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            return []
        text = re.sub(r"<[^>]+>", "\n", text)

    return _extract_habite_se(text)


def _pdf_to_text(content: bytes) -> str:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning(f"[{SOURCE}] pdfplumber não instalado — pulando PDF")
        return ""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        logger.exception(f"[{SOURCE}] pdfplumber failed")
        return ""


def _extract_habite_se(text: str) -> list[dict[str, Any]]:
    """Procura blocos contendo termos de Habite-se e extrai metadados próximos."""
    if not text:
        return []

    records: list[dict[str, Any]] = []
    for m in RE_HABITE.finditer(text):
        # janela maior que alvará: campos como custo costumam vir 200-400 chars depois.
        snippet = text[max(0, m.start() - 120): m.end() + 400]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        proc = _first_match(RE_PROCESSO, snippet)
        area_built = _to_float(_first_match(RE_AREA_BUILT, snippet))
        area_terrain = _to_float(_first_match(RE_AREA_TERRAIN, snippet))
        cost = _to_float(_first_match(RE_COST, snippet))
        issue_date = _extract_date(snippet)
        neighborhood = _first_match(RE_NEIGHBORHOOD, snippet)
        address = None
        m_addr = RE_ADDRESS.search(snippet)
        if m_addr:
            address = m_addr.group(0).strip()

        source_id = (
            proc or hashlib.sha1(snippet.encode("utf-8")).hexdigest()[:16]
        )

        records.append({
            "source_id": source_id,
            "process_number": proc,
            "issue_date": issue_date.isoformat() if issue_date else None,
            "address": address,
            "neighborhood": neighborhood.strip() if neighborhood else None,
            "area_built_m2": area_built,
            "area_terrain_m2": area_terrain,
            "declared_cost": cost,
            "snippet": snippet[:1000],
        })

    # Deduplicação dentro do batch
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in records:
        if r["source_id"] in seen:
            continue
        seen.add(r["source_id"])
        out.append(r)
    return out


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    # groups() retorna a primeira captura quando há; senão o match inteiro.
    return m.group(1) if m.groups() else m.group(0)


def _to_float(val: str | None) -> float | None:
    if not val:
        return None
    try:
        # 1.234,56 -> 1234.56 ; 1234.56 mantém
        cleaned = val.replace(".", "").replace(",", ".") if "," in val else val
        return float(cleaned)
    except ValueError:
        return None


def _extract_date(text: str) -> date | None:
    m = RE_DATE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _load_alvara_index(db: Any) -> dict[str, str]:
    """Retorna {process_number_normalizado: source_id_do_alvara}."""
    try:
        r = (
            db.table("off_market_signals")
            .select("source_id")
            .eq("source", "alvara_prefeitura")
            .eq("signal_type", "permit")
            .limit(5000)
            .execute()
        )
        idx: dict[str, str] = {}
        for row in r.data or []:
            sid = row.get("source_id")
            if not sid:
                continue
            idx[_normalize_proc(sid)] = sid
        return idx
    except Exception:
        logger.exception(f"[{SOURCE}] Falha ao carregar índice de alvarás")
        return {}


def _normalize_proc(value: str) -> str:
    return re.sub(r"[^\d]", "", value or "")


def _match_alvara(rec: dict[str, Any], index: dict[str, str]) -> str | None:
    proc = rec.get("process_number")
    if not proc or not index:
        return None
    key = _normalize_proc(proc)
    return index.get(key)


def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_id": rec["source_id"],
        "issue_date": rec.get("issue_date"),
        "process_number": rec.get("process_number"),
        "address": rec.get("address"),
        "neighborhood": rec.get("neighborhood"),
        "city": CITY,
        "state": STATE,
        "area_built_m2": rec.get("area_built_m2"),
        "area_terrain_m2": rec.get("area_terrain_m2"),
        "declared_cost": rec.get("declared_cost"),
        "alvara_reference": rec.get("alvara_reference"),
        "raw_payload": rec,
        "last_seen_at": now,
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

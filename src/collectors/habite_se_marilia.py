"""Coleta Habite-se (certificados de conclusão de obra) — Marília-SP.

Fonte: API de Dados Abertos do Diário Oficial Municipal de Marília.
  https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/[ANO]

Retorna JSON com todas as edições do ano, cada uma com campo `descricao`
contendo o texto completo da publicação. Sem autenticação, sem LAI.

Configuração (opcional):
  HABITE_SE_START_YEAR  — ano inicial da varredura (default: ano atual - 1)
  HABITE_SE_END_YEAR    — ano final (default: ano atual)
  HABITE_SE_FEED_URL    — se setada, usa URL direta em vez da API (legado/override)

Cruzamento com alvará:
  process_number extraído do texto é normalizado (só dígitos) e cruzado com
  off_market_signals.source_id (source=alvara_prefeitura) para calcular
  prazo real de obra via construction_timeline.py.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "habite_se_marilia"
CITY = "Marília"
STATE = "SP"

DOM_MAR_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}"
_THIS_YEAR = datetime.now().year

HABITE_SE_FEED_URL = os.getenv("HABITE_SE_FEED_URL", "").strip()
HABITE_SE_START_YEAR = int(os.getenv("HABITE_SE_START_YEAR", str(_THIS_YEAR - 1)))
HABITE_SE_END_YEAR = int(os.getenv("HABITE_SE_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 60
SLEEP_BETWEEN_YEARS = 2.0

RE_HABITE = re.compile(
    # "habite-se" sempre é de obra; "certificado de conclusão" só se NÃO for de curso/disciplina
    r"(?:"
    r"habite[-\s]?se"
    r"|certificado de conclus[ãa]o(?!\s+de\s+curso)(?!\s+de\s+(?:p[oó]s|gradua|especializa|aperfei))"
    r"|vistoria final de obra"
    r")"
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
RE_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_NEIGHBORHOOD = re.compile(
    r"(?:bairro|jardim|jd\.?|parque|vila|conjunto)\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s]{2,40})",
)
RE_ADDRESS = re.compile(
    # Exige número após o logradouro (ex: "Rua XV de Novembro, 123") pra evitar falsos positivos
    r"(?:rua|avenida|av\.|travessa|alameda|estrada|praça)\s+"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w\s\.,Áéíóúâêôãõç-]{3,60},?\s*n?[º°]?\s*\d{1,5}",
    re.IGNORECASE,
)


def run_collector() -> dict[str, int]:
    """Coleta Habite-se do DOM-MAR e upserta em habite_se_records."""
    stats = {"processed": 0, "created": 0, "failed": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        if HABITE_SE_FEED_URL:
            # Modo legado: URL única (PDF ou HTML)
            records = _collect_from_url(HABITE_SE_FEED_URL)
        else:
            # Modo API: iterar anos via dados-abertos DOM-MAR
            records = _collect_from_api()

        logger.info(f"[{SOURCE}] Total habite-se encontrados: {len(records)}")

        alvara_index = _load_alvara_index(db)

        for rec in records:
            stats["processed"] += 1
            try:
                rec["alvara_reference"] = _match_alvara(rec, alvara_index)
                db.table("habite_se_records").upsert(
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
# Coleta via API dados-abertos DOM-MAR
# ---------------------------------------------------------------------------

def _collect_from_api() -> list[dict[str, Any]]:
    years = range(HABITE_SE_START_YEAR, HABITE_SE_END_YEAR + 1)
    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in years:
            url = DOM_MAR_API.format(year=year)
            editions = _fetch_editions(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(editions)} edições")

            for ed in editions:
                text = ed.get("descricao") or ""
                if not text:
                    continue
                if not RE_HABITE.search(text):
                    continue  # skip edições sem habite-se (evita parse desnecessário)

                ed_date = _parse_edition_date(ed)
                ed_id = str(ed.get("edicao") or ed.get("id") or "")
                records = _extract_habite_se(text, fallback_date=ed_date, edition_id=ed_id)

                for r in records:
                    if r["source_id"] not in seen_ids:
                        seen_ids.add(r["source_id"])
                        all_records.append(r)

            if year != HABITE_SE_END_YEAR:
                time.sleep(SLEEP_BETWEEN_YEARS)

    return all_records


def _fetch_editions(client: httpx.Client, url: str, year: int) -> list[dict[str, Any]]:
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"[{SOURCE}] Ano {year}: HTTP {resp.status_code}")
            return []
        data = resp.json()
        # API retorna {"dados": [...]} — fallback para outros formatos comuns
        if isinstance(data, list):
            return data
        for key in ("dados", "data", "items", "edicoes", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        logger.warning(f"[{SOURCE}] Ano {year}: formato inesperado — keys={list(data.keys())[:5]}")
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Erro ao buscar edições {year}")
        return []


def _parse_edition_date(ed: dict[str, Any]) -> date | None:
    raw = ed.get("data") or ed.get("date") or ed.get("publicacao") or ""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(str(raw)[:19], fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Coleta via URL direta (legado/override)
# ---------------------------------------------------------------------------

def _collect_from_url(url: str) -> list[dict[str, Any]]:
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            resp = c.get(url)
            if resp.status_code != 200:
                logger.warning(f"[{SOURCE}] HTTP {resp.status_code} — {url}")
                return []
            content = resp.content
            ct = resp.headers.get("content-type", "")
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error: {e}")
        return []

    ct_lower = (ct or "").lower()
    if "pdf" in ct_lower or content[:4] == b"%PDF":
        text = _pdf_to_text(content)
    else:
        text = content.decode("utf-8", errors="ignore")
        text = re.sub(r"<[^>]+>", "\n", text)

    return _extract_habite_se(text)


def _pdf_to_text(content: bytes) -> str:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning(f"[{SOURCE}] pdfplumber não instalado")
        return ""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        logger.exception(f"[{SOURCE}] pdfplumber falhou")
        return ""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _extract_habite_se(
    text: str,
    fallback_date: date | None = None,
    edition_id: str = "",
) -> list[dict[str, Any]]:
    if not text:
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in RE_HABITE.finditer(text):
        snippet = text[max(0, m.start() - 120): m.end() + 400]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        proc = _first_match(RE_PROCESSO, snippet)
        area_built = _to_float(_first_match(RE_AREA_BUILT, snippet))
        area_terrain = _to_float(_first_match(RE_AREA_TERRAIN, snippet))
        cost = _to_float(_first_match(RE_COST, snippet))
        issue_date = _extract_date(snippet) or fallback_date
        neighborhood = _first_match(RE_NEIGHBORHOOD, snippet)
        address = (RE_ADDRESS.search(snippet) or type("", (), {"group": lambda self, n: None})()).group(0)
        if address:
            address = address.strip()

        # Descarta se não houver sinal de obra (área, endereço ou processo longo)
        has_obra_signal = any([
            area_built,
            area_terrain,
            address,
            proc and len(_normalize_proc(proc)) >= 6,
        ])
        if not has_obra_signal:
            continue

        # source_id: processo se disponível, senão hash do snippet (prefixado por edição)
        if proc:
            source_id = f"{edition_id}_{_normalize_proc(proc)}" if edition_id else _normalize_proc(proc)
        else:
            source_id = hashlib.sha1(snippet.encode("utf-8")).hexdigest()[:16]

        if source_id in seen:
            continue
        seen.add(source_id)

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

    return records


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return m.group(1) if m.groups() else m.group(0)


def _to_float(val: str | None) -> float | None:
    if not val:
        return None
    try:
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


def _normalize_proc(value: str) -> str:
    return re.sub(r"[^\d]", "", value or "")


# ---------------------------------------------------------------------------
# Índice de alvarás para cruzamento
# ---------------------------------------------------------------------------

def _load_alvara_index(db: Any) -> dict[str, str]:
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
            if sid:
                idx[_normalize_proc(sid)] = sid
        return idx
    except Exception:
        logger.exception(f"[{SOURCE}] Falha ao carregar índice de alvarás")
        return {}


def _match_alvara(rec: dict[str, Any], index: dict[str, str]) -> str | None:
    proc = rec.get("process_number")
    if not proc or not index:
        return None
    return index.get(_normalize_proc(proc))


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

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

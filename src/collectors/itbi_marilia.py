"""Coletor de ITBI (Imposto sobre Transmissão de Bens Imóveis) — Marília-SP.

================================================================================
README — Pesquisa de fontes públicas
================================================================================

URLs pesquisadas (2026-05):
- https://transparencia.marilia.sp.gov.br/  (Portal PAI / SMARAPD)
- https://www.marilia.sp.gov.br/portal/transparencia
- https://www.marilia.sp.gov.br/itbi2025
- https://www3.marilia.sp.gov.br/portalcidadaotb/  (Portal Tributário)

Status: Marília-SP **NÃO publica feed estruturado de ITBI** (CSV/JSON/API) de
forma equivalente à Prefeitura de SP capital (que publica desde 2022 na URL
https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501).

A página /itbi2025 oferece apenas parcelamento; o Portal PAI da Marília expõe
receitas/despesas agregadas mas não a granularidade de cada DTI.

Caminhos viáveis:
1. **Pedido LAI** (Lei de Acesso à Informação) à Diretoria de Fiscalização de
   Rendas — tel (14) 3402-6000. Solicitar relatório periódico DTI em CSV.
2. **Scraping do Portal Tributário** se houver listagem pública por matrícula.
3. **Cartórios** — RI 1º e 2º ofício de Marília publicam editais com
   transferências (raro em formato aberto).

Enquanto fonte oficial não está disponível, este coletor opera com URL
configurável via env (igual `alvara_prefeitura`). Quando obtida via LAI, basta
hospedar o arquivo (S3, Drive público) e setar `ITBI_MARILIA_FEED_URL`.

Formato esperado: CSV (preferencial), PDF (fallback) ou HTML. O parser detecta
automaticamente pelo content-type / magic bytes.

================================================================================
Configuração
================================================================================
- ITBI_MARILIA_FEED_URL  → URL do arquivo/endpoint (sem ela, coletor faz no-op)
"""

from __future__ import annotations

import csv
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

SOURCE = "itbi_marilia"
CITY = "Marília"
STATE = "SP"

ITBI_FEED_URL = os.getenv("ITBI_MARILIA_FEED_URL", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
TIMEOUT = 60

# Regex heurísticos (PDF/HTML)
RE_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
RE_VALUE = re.compile(
    r"R\$\s*([\d\.]+,\d{2})|(\d{1,3}(?:\.\d{3})+,\d{2})"
)
RE_AREA = re.compile(r"(\d{2,5}[\.,]?\d*)\s*m²", re.IGNORECASE)
RE_REGISTRY = re.compile(
    r"(?:matr[íi]cula|registro)\s*[:nº#]*\s*([\d\./-]{3,})",
    re.IGNORECASE,
)
RE_PROPERTY_TYPE = re.compile(
    r"\b(terreno|lote|casa|sobrado|apartamento|apto|sala|loja|gal[pã]ão|"
    r"comercial|residencial|rural|ch[áa]cara|s[íi]tio|fazenda)\b",
    re.IGNORECASE,
)


# Mapeamento de colunas CSV (tolerante a variações)
CSV_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "transaction_date": ("data", "data_transacao", "data_recolhimento", "dt_pagto"),
    "address": ("endereco", "endereço", "logradouro", "imovel"),
    "neighborhood": ("bairro", "setor"),
    "property_type": ("tipo", "tipo_imovel", "natureza"),
    "area_m2": ("area", "área", "area_m2", "metragem"),
    "declared_value": ("valor_declarado", "valor_transacao", "valor_negocio", "preco"),
    "market_value": ("valor_venal", "valor_mercado", "base_calculo"),
    "buyer_doc": ("comprador", "adquirente", "cpf_comprador"),
    "seller_doc": ("vendedor", "transmitente", "cpf_vendedor"),
    "registry_number": ("matricula", "matrícula", "registro", "numero_dti"),
}


def run_collector() -> dict[str, int]:
    """Coleta transações de ITBI e upserta em itbi_transactions."""
    stats = {"processed": 0, "created": 0, "failed": 0}

    if not ITBI_FEED_URL:
        logger.warning(
            f"[{SOURCE}] ITBI_MARILIA_FEED_URL não configurada — pulando coleta. "
            f"Marília-SP ainda não publica feed estruturado; é necessário pedido LAI."
        )
        return stats

    db = get_client()
    run_id = _start_run(db)

    try:
        content, ct = _download(ITBI_FEED_URL)
        if not content:
            _finish_run(db, run_id, "completed", stats)
            return stats

        records = _parse(content, ct)
        logger.info(f"[{SOURCE}] Parsed {len(records)} ITBI transactions")

        for rec in records:
            stats["processed"] += 1
            try:
                payload = _to_row(rec)
                db.table("itbi_transactions").upsert(
                    payload, on_conflict="source_id"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] Falha ao upsert transação")

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} failed={stats['failed']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Collector falhou")
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
    url_lower = ITBI_FEED_URL.lower()

    is_pdf = "pdf" in ct or content[:4] == b"%PDF"
    is_csv = (
        "csv" in ct
        or "text/plain" in ct
        or url_lower.endswith(".csv")
        or url_lower.endswith(".tsv")
    )

    if is_pdf:
        text = _pdf_to_text(content)
        return _extract_from_text(text)

    if is_csv:
        return _extract_from_csv(content)

    # HTML fallback — tenta CSV embedded, depois text
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        return []

    if "<table" in text.lower():
        return _extract_from_text(re.sub(r"<[^>]+>", " ", text))

    return _extract_from_text(text)


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
        logger.exception(f"[{SOURCE}] pdfplumber falhou")
        return ""


def _extract_from_csv(content: bytes) -> list[dict[str, Any]]:
    """Parse CSV tolerante a delimitador ; ou , e nomes de coluna variados."""
    try:
        text = content.decode("utf-8-sig", errors="ignore")
    except Exception:
        return []

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    out: list[dict[str, Any]] = []

    for row in reader:
        norm = {_normalize_key(k): (v or "").strip() for k, v in row.items() if k}
        rec = _map_csv_row(norm)
        if not rec:
            continue
        rec["raw_payload"] = {k: v for k, v in norm.items() if v}
        rec["source_id"] = _build_source_id(rec, norm)
        out.append(rec)

    return _dedup(out)


def _normalize_key(k: str) -> str:
    k = k.strip().lower()
    k = re.sub(r"[áàâã]", "a", k)
    k = re.sub(r"[éê]", "e", k)
    k = re.sub(r"[íî]", "i", k)
    k = re.sub(r"[óôõ]", "o", k)
    k = re.sub(r"[úû]", "u", k)
    k = re.sub(r"ç", "c", k)
    k = re.sub(r"[^a-z0-9]+", "_", k).strip("_")
    return k


def _map_csv_row(row: dict[str, str]) -> dict[str, Any] | None:
    rec: dict[str, Any] = {}

    for field, aliases in CSV_FIELD_ALIASES.items():
        for alias in aliases:
            key = _normalize_key(alias)
            if key in row and row[key]:
                rec[field] = row[key]
                break

    if not rec.get("address") and not rec.get("registry_number"):
        return None

    rec["transaction_date"] = _parse_date(rec.get("transaction_date"))
    rec["area_m2"] = _parse_number(rec.get("area_m2"))
    rec["declared_value"] = _parse_number(rec.get("declared_value"))
    rec["market_value"] = _parse_number(rec.get("market_value"))
    rec["property_type"] = _normalize_property_type(rec.get("property_type"))
    rec["buyer_doc"] = _hash_doc(rec.get("buyer_doc"))
    rec["seller_doc"] = _hash_doc(rec.get("seller_doc"))

    return rec


def _extract_from_text(text: str) -> list[dict[str, Any]]:
    """Heurística: quebra texto por linhas e tenta extrair tuplas de transação."""
    if not text:
        return []

    out: list[dict[str, Any]] = []
    # Janela deslizante de ~3 linhas (PDFs costumam quebrar registros)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for i, line in enumerate(lines):
        window = " ".join(lines[i: i + 3])

        m_date = RE_DATE.search(window)
        m_value = RE_VALUE.search(window)
        if not (m_date and m_value):
            continue

        m_area = RE_AREA.search(window)
        m_reg = RE_REGISTRY.search(window)
        m_type = RE_PROPERTY_TYPE.search(window)

        snippet = re.sub(r"\s+", " ", window)[:500]

        rec: dict[str, Any] = {
            "transaction_date": _parse_date(
                f"{m_date.group(1)}/{m_date.group(2)}/{m_date.group(3)}"
            ),
            "address": snippet,
            "area_m2": _parse_number(m_area.group(1)) if m_area else None,
            "declared_value": _parse_number(
                m_value.group(1) or m_value.group(2)
            ),
            "registry_number": m_reg.group(1) if m_reg else None,
            "property_type": _normalize_property_type(
                m_type.group(1) if m_type else None
            ),
            "raw_payload": {"snippet": snippet},
        }
        rec["source_id"] = _build_source_id(rec, {"snippet": snippet})
        out.append(rec)

    return _dedup(out)


def _build_source_id(rec: dict[str, Any], raw: dict[str, Any]) -> str:
    """source_id estável: matrícula + data se houver, senão hash do conteúdo."""
    reg = rec.get("registry_number")
    txn_date = rec.get("transaction_date")
    if reg and txn_date:
        return f"{reg}-{txn_date}"

    basis = "|".join([
        str(rec.get("registry_number") or ""),
        str(rec.get("transaction_date") or ""),
        str(rec.get("address") or ""),
        str(rec.get("declared_value") or ""),
        str(raw.get("snippet") or ""),
    ])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:24]


def _parse_date(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    # tenta formatos comuns
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    s = str(value).strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    # padrão BR: 1.234,56  →  1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_property_type(value: Any) -> str | None:
    if not value:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    mapping = {
        "lote": "terreno",
        "terreno": "terreno",
        "casa": "casa",
        "sobrado": "casa",
        "apto": "apartamento",
        "apartamento": "apartamento",
        "sala": "comercial",
        "loja": "comercial",
        "galpão": "comercial",
        "galpao": "comercial",
        "comercial": "comercial",
        "rural": "rural",
        "chácara": "rural",
        "chacara": "rural",
        "sítio": "rural",
        "sitio": "rural",
        "fazenda": "rural",
        "residencial": "casa",
    }
    for key, mapped in mapping.items():
        if key in s:
            return mapped
    return "outro"


def _hash_doc(value: Any) -> str | None:
    """Anonimiza CPF/CNPJ: mantém últimos 4 dígitos + hash do restante."""
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        # provavelmente é nome — hasheia direto
        return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:16]
    if len(digits) <= 4:
        return digits
    tail = digits[-4:]
    head_hash = hashlib.sha1(digits[:-4].encode("utf-8")).hexdigest()[:8]
    return f"{head_hash}***{tail}"


def _dedup(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in records:
        sid = r.get("source_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(r)
    return out


def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_id": rec["source_id"],
        "transaction_date": rec.get("transaction_date"),
        "address": (rec.get("address") or "")[:500] or None,
        "neighborhood": rec.get("neighborhood"),
        "city": CITY,
        "state": STATE,
        "property_type": rec.get("property_type"),
        "area_m2": rec.get("area_m2"),
        "declared_value": rec.get("declared_value"),
        "market_value": rec.get("market_value"),
        "buyer_doc": rec.get("buyer_doc"),
        "seller_doc": rec.get("seller_doc"),
        "registry_number": rec.get("registry_number"),
        "raw_payload": rec.get("raw_payload"),
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
        logger.exception(f"[{SOURCE}] Falha ao iniciar agent_runs")
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
        logger.exception(f"[{SOURCE}] Falha ao atualizar agent_runs")

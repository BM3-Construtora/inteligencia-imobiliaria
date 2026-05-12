"""Coletor da Planta Genérica de Valores (PGV) — IPTU Marília-SP.

Dado de REFERÊNCIA (não é signal de off-market). Lê o anexo da Lei Complementar
Municipal que define o valor venal m² oficial por face de quadra/setor fiscal.

Uso a jusante:
  - Floor price de terra por região (calibração do AVM em `price_model.py`)
  - Detector "imóvel abaixo do valor venal" (oportunidade fiscal)

Status atual:
  - Lei base: LC 672/2013 (institui a PGV, vigência 2013)
  - Revisão recente: PLC 16/2025 aprovada em 22/09/2025 pela Câmara Municipal
  - Anexo I / Tabela 5 = valores territoriais por face de quadra
  - Anexo I / Tabelas 1-4 = valores prediais por tipo/padrão construtivo

URLs candidatas (configurar via env `IPTU_PLANTA_URL`):
  - https://www.marilia.sp.gov.br/prefeitura/wp-content/uploads/2013/03/
    Lei_Complementar_672-PGV_modifica_CTM_2013.pdf
  - https://www.marilia.sp.gov.br/prefeitura/wp-content/uploads/2013/07/
    NOVA.Montagem-CTM.pdf  (contém Tabela 5 consolidada)
  - PDF do PLC 16/2025 — ainda não localizado em URL estável no portal da
    Câmara (camaramarilia.sp.gov.br). Buscar pelo número da Lei sancionada
    quando publicada no Diário Oficial Municipal.

BLOCKER conhecido:
  - Planta Genérica é PDF pesado, layout tabular complexo, hifenizado e com
    cabeçalhos repetidos. `pdfplumber.extract_tables()` cobre o caso "tabela
    com bordas", mas a Tabela 5 de Marília é layout "lista contínua por
    bairro" — fallback regex obrigatório. Scaffolding atual cobre ambos.

Idempotente via UNIQUE (ref_year, sector_code, face_code).
"""

from __future__ import annotations

import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "iptu_planta_marilia"
CITY = "Marília"
STATE = "SP"

# Configuração via env — coletor roda 1x/ano (CRON anual), mas pode rodar
# manualmente várias vezes sem duplicar (upsert).
IPTU_PLANTA_URL = os.getenv("IPTU_PLANTA_URL", "").strip()
IPTU_PLANTA_REF_YEAR = int(
    os.getenv("IPTU_PLANTA_REF_YEAR", str(datetime.now().year))
)
# Lei de origem — informativo, ajusta conforme o ano (ex: "LC 672/2013",
# "LC XYZ/2025" após sanção do PLC 16/2025).
IPTU_PLANTA_SOURCE_LAW = os.getenv(
    "IPTU_PLANTA_SOURCE_LAW", "Lei Complementar 672/2013"
).strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
TIMEOUT = 120

# Regex de linha tabular típica da Tabela 5 — formato observado:
#   "<setor>-<face>  <logradouro>  <de>  <até>  <R$/m²>"
# Ex: "012-034  RUA SAO LUIZ  100  299  850,00"
# Tolerante a múltiplos espaços, vírgula decimal e separador de milhar.
RE_TABLE_ROW = re.compile(
    r"^\s*"
    r"(?P<sector>\d{1,3})\s*[-./]\s*(?P<face>\d{1,4}[A-Z]?)\s+"
    r"(?P<street>[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ .'\-/]{3,60}?)\s+"
    r"(?P<from>\d{1,5}|[A-Z][A-Z .'\-/]{2,40}?)\s+"
    r"(?P<to>\d{1,5}|[A-Z][A-Z .'\-/]{2,40}?)\s+"
    r"(?P<value>\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*$",
    re.MULTILINE,
)

# Fallback minimalista: setor-face + valor R$/m² na mesma linha.
RE_TABLE_ROW_MIN = re.compile(
    r"^\s*"
    r"(?P<sector>\d{1,3})\s*[-./]\s*(?P<face>\d{1,4}[A-Z]?)\s+"
    r"(?P<rest>.+?)\s+"
    r"(?P<value>\d{1,3}(?:\.\d{3})*(?:,\d{2}))\s*$",
    re.MULTILINE,
)


def run_collector() -> dict[str, int]:
    """Baixa PDF da PGV, parseia tabela e upserta em iptu_planta_valores."""
    stats = {"processed": 0, "created": 0, "failed": 0}

    if not IPTU_PLANTA_URL:
        logger.warning(
            f"[{SOURCE}] IPTU_PLANTA_URL não configurada — pulando coleta. "
            "Setar URL do PDF anexo da Lei Complementar (PGV) Marília."
        )
        return stats

    db = get_client()
    run_id = _start_run(db)

    try:
        content, ct = _download(IPTU_PLANTA_URL)
        if not content:
            logger.warning(f"[{SOURCE}] Download vazio")
            _finish_run(db, run_id, "completed", stats)
            return stats

        records = _parse(content, ct)
        logger.info(
            f"[{SOURCE}] Parsed {len(records)} linhas da PGV "
            f"(ref_year={IPTU_PLANTA_REF_YEAR})"
        )

        if not records:
            logger.warning(
                f"[{SOURCE}] Nenhum registro parseado — revisar layout do PDF "
                "ou ajustar RE_TABLE_ROW."
            )

        for rec in records:
            stats["processed"] += 1
            try:
                payload = _to_row(rec)
                db.table("iptu_planta_valores").upsert(
                    payload, on_conflict="ref_year,sector_code,face_code"
                ).execute()
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] Falha no upsert de registro")

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
# Download
# ---------------------------------------------------------------------------
def _download(url: str) -> tuple[bytes, str]:
    try:
        with httpx.Client(
            headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
        ) as c:
            resp = c.get(url)
            if resp.status_code != 200:
                logger.warning(f"[{SOURCE}] HTTP {resp.status_code} em {url}")
                return b"", ""
            return resp.content, resp.headers.get("content-type", "")
    except httpx.HTTPError as e:
        logger.warning(f"[{SOURCE}] HTTP error: {e}")
        return b"", ""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _parse(content: bytes, content_type: str) -> list[dict[str, Any]]:
    ct = (content_type or "").lower()
    is_pdf = "pdf" in ct or content[:4] == b"%PDF"
    if not is_pdf:
        logger.warning(
            f"[{SOURCE}] Conteúdo não é PDF (content-type={ct!r}) — abortando"
        )
        return []

    # 1) Tentar extract_tables (caso PDF tenha grid real)
    rows = _pdf_extract_tables(content)
    if rows:
        logger.info(f"[{SOURCE}] extract_tables retornou {len(rows)} linhas")
        return rows

    # 2) Fallback regex sobre texto bruto
    text = _pdf_to_text(content)
    if not text:
        return []
    return _parse_text(text)


def _pdf_extract_tables(content: bytes) -> list[dict[str, Any]]:
    """Tenta extrair tabela estruturada (PDFs com bordas/grid)."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning(f"[{SOURCE}] pdfplumber não instalado")
        return []

    out: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    out.extend(_rows_from_table(table))
    except Exception:
        logger.exception(f"[{SOURCE}] extract_tables falhou")
        return []
    return out


def _rows_from_table(table: list[list[str | None]]) -> list[dict[str, Any]]:
    """Heurística: encontrar colunas setor/face/logradouro/valor em uma tabela.

    Layout esperado (variável):
      [setor, face, logradouro, de, até, valor]
    """
    out: list[dict[str, Any]] = []
    if not table or len(table) < 2:
        return out

    for row in table:
        if not row:
            continue
        cells = [(c or "").strip() for c in row]
        # Última célula numérica = valor R$/m²?
        value = _parse_brl(cells[-1]) if cells else None
        if value is None or value <= 0:
            continue
        # Setor + face em alguma das primeiras células
        sector, face = _find_sector_face(cells[:3])
        if not sector:
            continue
        street = cells[2] if len(cells) > 2 else None
        sfrom = cells[3] if len(cells) > 3 else None
        sto = cells[4] if len(cells) > 4 else None
        out.append({
            "sector_code": sector,
            "face_code": face,
            "street_name": _clean_str(street),
            "street_from": _clean_str(sfrom),
            "street_to": _clean_str(sto),
            "land_value_per_m2": value,
            "raw": cells,
        })
    return out


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
        logger.exception(f"[{SOURCE}] pdfplumber falhou no extract_text")
        return ""


def _parse_text(text: str) -> list[dict[str, Any]]:
    """Fallback regex sobre texto plano da PGV."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for m in RE_TABLE_ROW.finditer(text):
        sector = m.group("sector").lstrip("0") or "0"
        face = m.group("face")
        key = (sector, face)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "sector_code": sector,
            "face_code": face,
            "street_name": _clean_str(m.group("street")),
            "street_from": _clean_str(m.group("from")),
            "street_to": _clean_str(m.group("to")),
            "land_value_per_m2": _parse_brl(m.group("value")),
            "raw": m.group(0).strip(),
        })

    if out:
        return out

    # Tentativa mais permissiva
    for m in RE_TABLE_ROW_MIN.finditer(text):
        sector = m.group("sector").lstrip("0") or "0"
        face = m.group("face")
        key = (sector, face)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "sector_code": sector,
            "face_code": face,
            "street_name": _clean_str(m.group("rest")),
            "street_from": None,
            "street_to": None,
            "land_value_per_m2": _parse_brl(m.group("value")),
            "raw": m.group(0).strip(),
        })
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_brl(s: str | None) -> float | None:
    """'1.234,56' -> 1234.56 ; '850,00' -> 850.0"""
    if not s:
        return None
    s = s.strip().replace("R$", "").replace(" ", "")
    if not re.match(r"^\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?$", s):
        # Tenta interpretar formatos simples ("850" ou "850.50")
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _find_sector_face(cells: list[str]) -> tuple[str | None, str | None]:
    """Procura padrão setor + face nas primeiras células da linha."""
    for i, c in enumerate(cells):
        # Caso "012-034" em uma célula só
        m = re.match(r"^\s*(\d{1,3})\s*[-./]\s*(\d{1,4}[A-Z]?)\s*$", c)
        if m:
            return m.group(1).lstrip("0") or "0", m.group(2)
        # Caso setor e face em células separadas
        if re.match(r"^\d{1,3}$", c) and i + 1 < len(cells):
            nxt = cells[i + 1]
            if re.match(r"^\d{1,4}[A-Z]?$", nxt):
                return c.lstrip("0") or "0", nxt
    return None, None


def _clean_str(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    """Mapeia registro parseado para coluna da tabela iptu_planta_valores."""
    return {
        "ref_year": IPTU_PLANTA_REF_YEAR,
        "sector_code": rec["sector_code"],
        "face_code": rec.get("face_code"),
        "neighborhood": rec.get("neighborhood"),
        "street_name": rec.get("street_name"),
        "street_from": rec.get("street_from"),
        "street_to": rec.get("street_to"),
        "land_value_per_m2": rec["land_value_per_m2"],
        "build_value_per_m2_by_type": rec.get("build_value_per_m2_by_type"),
        "source_law": IPTU_PLANTA_SOURCE_LAW,
        "raw_payload": {"raw": rec.get("raw")},
    }


# ---------------------------------------------------------------------------
# agent_runs tracking
# ---------------------------------------------------------------------------
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
        logger.exception(f"[{SOURCE}] Falha ao atualizar agent_runs")

"""Monitor do Plano Diretor — keywords de zoneamento no DOM-MAR (Marília-SP).

Plano Diretor 2026 está em revisão AGORA. Jardim Bela Vista e Jardim América
identificados para upzoning pela Planurb. Este coletor monitora o DOM-MAR
para capturar qualquer mudança antes de qualquer portal imobiliário.

Também monitora: PPA 2026-2029, leis de uso e ocupação, ZEIS, outorga onerosa.

Configuração (opcional):
  PLANO_DIRETOR_START_YEAR  — ano inicial (default: ano atual - 1)
  PLANO_DIRETOR_END_YEAR    — ano final (default: ano atual)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.db import get_client
from src.marilia_neighborhoods import validate_neighborhood

logger = logging.getLogger(__name__)

SOURCE = "plano_diretor_monitor"
DOM_MAR_API = "https://www.marilia.sp.gov.br/portal/dados-abertos/diario-oficial/{year}"
_THIS_YEAR = datetime.now().year

START_YEAR = int(os.getenv("PLANO_DIRETOR_START_YEAR", str(_THIS_YEAR - 1)))
END_YEAR = int(os.getenv("PLANO_DIRETOR_END_YEAR", str(_THIS_YEAR)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}
TIMEOUT = 60
SLEEP_BETWEEN_YEARS = 2.0

# Keywords de alto valor urbanístico
UPZONING_KEYWORDS = re.compile(
    r"(?:"
    r"plano\s+diretor"
    r"|rezon[ae]amento"
    r"|altera[çc][ãa]o\s+de\s+uso"
    r"|uso\s+e\s+ocupa[çc][ãa]o\s+do\s+solo"
    r"|lei\s+(?:complementar\s+)?\d+.*zon[ae]"
    r"|outorga\s+onerosa"
    r"|ZEIS"                                        # Zona Especial de Interesse Social
    r"|ZR[123]\b"                                   # Zonas residenciais
    r"|ZC[123]\b"                                   # Zonas comerciais
    r"|ZDE\b"                                       # Zona de Desenvolvimento Econômico
    r"|coeficiente\s+de\s+aproveitamento"
    r"|gabarito\s+de\s+altura"
    r"|taxa\s+de\s+ocupa[çc][ãa]o"
    r"|audiência\s+pública.*(?:plano\s+diretor|zoneamento)"
    r"|ppa\s+20(?:26|27|28|29)"                    # PPA 2026-2029
    r")",
    re.IGNORECASE,
)

# Bairros em upzoning (identificados pela Planurb)
UPZONING_BAIRROS = {
    "jardim bela vista", "jd bela vista", "bela vista",
    "jardim america", "jardim américa", "jd america",
}

RE_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_LEI = re.compile(
    r"lei\s+(?:complementar\s+)?(?:municipal\s+)?(?:n[º°]?\s*)?([\d\.]+(?:/\d{4})?)",
    re.IGNORECASE,
)
RE_NEIGHBORHOOD = re.compile(
    r"(?:bairro|jardim|jd\.?|parque|vila|conjunto)\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s]{2,40})",
)


def run_plano_diretor_monitor() -> dict[str, int]:
    """Monitora DOM-MAR por publicações de zoneamento/Plano Diretor."""
    stats = {"processed": 0, "created": 0, "failed": 0, "upzoning_alerts": 0}
    db = get_client()
    run_id = _start_run(db)

    try:
        records = _collect_from_api()
        logger.info(f"[{SOURCE}] Total sinais de zoneamento encontrados: {len(records)}")

        for rec in records:
            stats["processed"] += 1
            try:
                db.table("plano_diretor_signals").upsert(
                    _to_row(rec), on_conflict="source_id"
                ).execute()
                stats["created"] += 1
                if rec.get("upzoning_bairro"):
                    stats["upzoning_alerts"] += 1
                    logger.warning(
                        f"[{SOURCE}] 🏗️ UPZONING ALERT: {rec['upzoning_bairro']} em {rec.get('publication_date')}"
                    )
            except Exception:
                stats["failed"] += 1
                logger.exception(f"[{SOURCE}] upsert falhou: {rec.get('source_id')}")

        if stats["upzoning_alerts"] > 0:
            _send_telegram_alert(stats["upzoning_alerts"], records)

        logger.info(
            f"[{SOURCE}] Done: processed={stats['processed']} "
            f"created={stats['created']} upzoning_alerts={stats['upzoning_alerts']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception(f"[{SOURCE}] Monitor falhou")
        _finish_run(db, run_id, "failed", stats, str(e))

    return stats


def _collect_from_api() -> list[dict[str, Any]]:
    years = range(START_YEAR, END_YEAR + 1)
    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for year in years:
            url = DOM_MAR_API.format(year=year)
            editions = _fetch_editions(client, url, year)
            logger.info(f"[{SOURCE}] Ano {year}: {len(editions)} edições")

            for ed in editions:
                text = ed.get("descricao") or ""
                if not text or not UPZONING_KEYWORDS.search(text):
                    continue

                ed_date = _parse_edition_date(ed)
                ed_id = str(ed.get("edicao") or ed.get("id") or "")
                records = _extract_signals(text, fallback_date=ed_date, edition_id=ed_id)

                for r in records:
                    if r["source_id"] not in seen_ids:
                        seen_ids.add(r["source_id"])
                        all_records.append(r)

            if year != END_YEAR:
                time.sleep(SLEEP_BETWEEN_YEARS)

    return all_records


def _fetch_editions(client: httpx.Client, url: str, year: int) -> list[dict[str, Any]]:
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"[{SOURCE}] Ano {year}: HTTP {resp.status_code}")
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        for key in ("dados", "data", "items", "edicoes", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return []
    except Exception:
        logger.exception(f"[{SOURCE}] Erro ao buscar edições {year}")
        return []


def _parse_edition_date(ed: dict[str, Any]) -> date | None:
    raw = ed.get("data") or ed.get("date") or ed.get("publicacao") or ""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(raw)[:19], fmt).date()
        except ValueError:
            continue
    return None


def _extract_signals(
    text: str,
    fallback_date: date | None = None,
    edition_id: str = "",
) -> list[dict[str, Any]]:
    if not text:
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in UPZONING_KEYWORDS.finditer(text):
        snippet = text[max(0, m.start() - 100): m.end() + 600]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        keyword_matched = m.group(0).strip()
        pub_date = _extract_date(snippet) or fallback_date
        lei_number = _first_match(RE_LEI, snippet)
        neighborhood_raw = _first_match(RE_NEIGHBORHOOD, snippet)
        neighborhood = validate_neighborhood(neighborhood_raw) if neighborhood_raw else None

        # Detectar se menciona bairro em upzoning
        upzoning_bairro = None
        snippet_lower = snippet.lower()
        for bairro in UPZONING_BAIRROS:
            if bairro in snippet_lower:
                upzoning_bairro = bairro
                break

        # Classificar tipo de sinal
        tipo = _classify_signal_type(snippet)

        key_parts = [edition_id, keyword_matched[:50], str(pub_date or ""), lei_number or ""]
        source_id = hashlib.sha1(":".join(key_parts).encode()).hexdigest()[:20]

        if source_id in seen:
            continue
        seen.add(source_id)

        records.append({
            "source_id": source_id,
            "publication_date": pub_date.isoformat() if pub_date else None,
            "tipo_sinal": tipo,
            "keyword": keyword_matched[:100],
            "lei_number": lei_number,
            "neighborhood": neighborhood.strip() if neighborhood else None,
            "upzoning_bairro": upzoning_bairro,
            "snippet": snippet[:1000],
        })

    return records


def _classify_signal_type(text: str) -> str:
    t = text.lower()
    if re.search(r"plano\s+diretor", t):
        return "plano_diretor"
    if re.search(r"ppa|plano\s+plurianual", t):
        return "ppa"
    if re.search(r"zeis", t):
        return "zeis"
    if re.search(r"outorga\s+onerosa", t):
        return "outorga_onerosa"
    if re.search(r"audiência\s+pública", t):
        return "audiencia_publica"
    if re.search(r"rezon[ae]amento|altera[çc][ãa]o\s+de\s+zon", t):
        return "rezonamento"
    return "uso_ocupacao_solo"


def _send_telegram_alert(count: int, records: list[dict[str, Any]]) -> None:
    upzoning = [r for r in records if r.get("upzoning_bairro")]
    if not upzoning:
        return
    try:
        import os
        import httpx as _httpx
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        lines = [f"🏗️ <b>Alerta Plano Diretor 2026</b> — {count} sinal(is) novo(s)"]
        for r in upzoning[:5]:
            lines.append(
                f"\n📍 <b>{r['upzoning_bairro'].title()}</b>"
                f"\nData: {r.get('publication_date', '?')}"
                f"\nTipo: {r.get('tipo_sinal', '?')}"
                f"\nLei: {r.get('lei_number', '-')}"
            )
        _httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "\n".join(lines), "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        logger.exception(f"[{SOURCE}] Telegram alert falhou")


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return m.group(1) if m.groups() else m.group(0)


def _extract_date(text: str) -> date | None:
    m = RE_DATE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _to_row(rec: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_id": rec["source_id"],
        "publication_date": rec.get("publication_date"),
        "tipo_sinal": rec.get("tipo_sinal"),
        "keyword": rec.get("keyword"),
        "lei_number": rec.get("lei_number"),
        "neighborhood": rec.get("neighborhood"),
        "upzoning_bairro": rec.get("upzoning_bairro"),
        "raw_snippet": rec.get("snippet", "")[:2000],
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

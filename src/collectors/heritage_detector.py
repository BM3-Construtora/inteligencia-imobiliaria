"""Detector de herança imobiliária — Marília-SP.

Herança = venda forçada com desconto estimado de 15-25%. Identificamos sinais via:
  1. Obituários publicados em jornais locais (Jornal Cidade de Marília / Diário de Marília)
  2. Processos de inventário no TJSP via DataJud (CNJ)
  3. Cruzamento com listings novos publicados até 90 dias após o óbito

Política de privacidade:
  - Nunca armazena CPF em claro; apenas SHA-256 do CPF limpo se disponível.
  - Nomes dos falecidos são armazenados exclusivamente para matching/dedup.
  - Graceful degradation: qualquer falha externa → log warning + continua.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SOURCE = "heritage_detector"
DESCONTO_ESTIMADO_DEFAULT = 20.0  # % conservador para Marília

DATAJUD_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"
DATAJUD_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQTZud3Y4ZG15Zw=="

OBITUARIO_SOURCES = [
    {
        "name": "jornal_cidade_marilia",
        "url": "https://jornaldacidade.net/falecimentos",
        "fallback_urls": [
            "https://jornaldacidade.net/categoria/falecimentos",
            "https://jornaldacidade.net/obituario",
        ],
    },
    {
        "name": "diario_marilia",
        "url": "https://www.diariodemarilia.com.br/falecimentos",
        "fallback_urls": [],
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

TIMEOUT = 30
REQUEST_DELAY_S = 1.5
LISTING_MATCH_DAYS = 90

# Padrões de extração de obituário
RE_NOME = re.compile(
    r"(?:faleceu|falecimento\s+de|[oó]bito\s+de|senhor[a]?\s+|sr\.?\s*|sra\.?\s*)"
    r"([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙÇ][a-záéíóúâêîôûãõàèìòùç]+(?:\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙÇ][a-záéíóúâêîôûãõàèìòùç]+){1,5})",
    re.IGNORECASE,
)
RE_DATA_OBITO = re.compile(
    r"(?:faleceu|óbito|falecimento)[^\d]{0,40}(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})",
    re.IGNORECASE,
)
RE_ENDERECO = re.compile(
    r"(?:residente|resid[eê]ncia|morava|domiciliado)\s+(?:na|no|em)?\s*"
    r"((?:rua|av(?:enida)?|travessa|alameda|pra[çc]a|estrada)\s+[^,\n]{5,80})",
    re.IGNORECASE,
)
RE_DATE_GENERIC = re.compile(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cpf_hash(cpf_raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", cpf_raw or "")
    if len(digits) != 11:
        return None
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()


def _source_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _parse_date_tuple(day: str, month: str, year: str) -> Optional[date]:
    try:
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# 1. Coleta de obituários
# ---------------------------------------------------------------------------


def _extract_obituarios_from_html(html: str, source_name: str) -> list[dict[str, Any]]:
    """Extrai obituários do HTML bruto. Retorna lista (possivelmente vazia)."""
    results: list[dict[str, Any]] = []

    # Divide em blocos por entry/article se possível, senão trabalha no texto todo
    # Estratégia simples: extrai parágrafos relevantes
    blocks = re.split(r"<(?:article|div|li|p|section)[^>]*>", html)
    if len(blocks) <= 2:
        blocks = [html]

    for block in blocks:
        # Remove tags HTML
        text = re.sub(r"<[^>]+>", " ", block)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s{2,}", " ", text).strip()

        if len(text) < 20:
            continue

        # Filtra blocos irrelevantes
        keywords = ["faleceu", "falecimento", "óbito", "obituário", "falecida", "falecido", "saudades"]
        if not any(k in text.lower() for k in keywords):
            continue

        nome: Optional[str] = None
        data_falecimento: Optional[date] = None
        endereco: Optional[str] = None

        # Extrai nome
        m_nome = RE_NOME.search(text)
        if m_nome:
            nome = m_nome.group(1).strip()

        # Extrai data óbito
        m_data = RE_DATA_OBITO.search(text)
        if m_data:
            data_falecimento = _parse_date_tuple(m_data.group(1), m_data.group(2), m_data.group(3))
        if not data_falecimento:
            m_data2 = RE_DATE_GENERIC.search(text)
            if m_data2:
                data_falecimento = _parse_date_tuple(m_data2.group(1), m_data2.group(2), m_data2.group(3))

        # Extrai endereço
        m_end = RE_ENDERECO.search(text)
        if m_end:
            endereco = m_end.group(1).strip()

        if not nome:
            continue

        results.append({
            "nome_falecido": nome,
            "signal_date": data_falecimento or _today(),
            "endereco": endereco,
            "source": source_name,
            "signal_type": "obituario",
            "raw_text": text[:500],
        })

    return results


def _fetch_url(url: str) -> Optional[str]:
    """GET simples com timeout. Retorna HTML ou None."""
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                return resp.text
            logger.warning(f"[heritage] HTTP {resp.status_code} para {url}")
            return None
    except Exception:
        logger.warning(f"[heritage] Falha ao buscar {url}", exc_info=True)
        return None


def _collect_obituarios() -> list[dict[str, Any]]:
    """Scraping das fontes de obituários. Graceful degradation total."""
    all_results: list[dict[str, Any]] = []

    for src in OBITUARIO_SOURCES:
        try:
            html = _fetch_url(src["url"])

            # Tenta fallbacks se necessário
            if not html:
                for fallback in src.get("fallback_urls", []):
                    html = _fetch_url(fallback)
                    if html:
                        break

            if not html:
                logger.warning(f"[heritage] Nenhum HTML obtido para {src['name']}")
                continue

            items = _extract_obituarios_from_html(html, src["name"])
            logger.info(f"[heritage] {src['name']}: {len(items)} obituários extraídos")
            all_results.extend(items)

        except Exception:
            logger.warning(f"[heritage] Erro ao coletar {src['name']}", exc_info=True)

        time.sleep(REQUEST_DELAY_S)

    return all_results


# ---------------------------------------------------------------------------
# 2. Inventários TJSP via DataJud
# ---------------------------------------------------------------------------


def _collect_inventarios_tjsp() -> list[dict[str, Any]]:
    """Busca processos de inventário em Marília via DataJud. Retorna lista ou []."""
    payload = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"municipio_nome": "Marília"}},
                    {"match": {"assunto_nome": "Inventário"}},
                ]
            }
        },
        "size": 50,
        "sort": [{"dataAjuizamento": {"order": "desc"}}],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"ApiKey {DATAJUD_API_KEY}",
    }

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(DATAJUD_URL, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(f"[heritage] DataJud HTTP {resp.status_code}")
                return []
            data = resp.json()
    except Exception:
        logger.warning("[heritage] Falha ao chamar DataJud", exc_info=True)
        return []

    results: list[dict[str, Any]] = []
    hits = (data.get("hits") or {}).get("hits") or []

    for hit in hits:
        try:
            src = hit.get("_source") or {}
            numero = src.get("numeroProcesso", "")
            data_ajuiz_raw = src.get("dataAjuizamento")

            signal_date: Optional[date] = None
            if data_ajuiz_raw:
                try:
                    signal_date = datetime.fromisoformat(
                        data_ajuiz_raw[:10]
                    ).date()
                except (ValueError, TypeError):
                    pass

            # Polo passivo — falecido costuma aparecer como réu/inventariado
            partes = src.get("partes") or []
            nome_falecido: Optional[str] = None
            for parte in partes:
                polo = (parte.get("polo") or "").upper()
                if polo in ("PASSIVO", "RÉU", "REU", "INVENTARIADO"):
                    nome_falecido = parte.get("nome")
                    break
            if not nome_falecido and partes:
                # Fallback: pega a primeira parte disponível
                nome_falecido = partes[0].get("nome")

            results.append({
                "processo_tjsp": numero,
                "signal_date": signal_date or _today(),
                "nome_falecido": nome_falecido,
                "signal_type": "inventario_tjsp",
                "source": "datajud_tjsp",
                "raw_payload": {
                    "numeroProcesso": numero,
                    "dataAjuizamento": data_ajuiz_raw,
                    "classe": (src.get("classe") or {}).get("nome"),
                    "tribunal": src.get("tribunal"),
                    "partes": partes[:5],
                },
            })
        except Exception:
            logger.warning("[heritage] Falha ao parsear hit DataJud", exc_info=True)

    logger.info(f"[heritage] DataJud inventários: {len(results)} processos")
    return results


# ---------------------------------------------------------------------------
# 3. Cruzamento com listings
# ---------------------------------------------------------------------------


def _normalize_address(addr: str) -> str:
    """Normaliza endereço para comparação."""
    addr = addr.lower()
    addr = re.sub(r"[^\w\s]", " ", addr)
    addr = re.sub(r"\b(rua|av|avenida|travessa|alameda|pra[cç]a|r\b)\b", "", addr)
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


def _fuzzy_match(a: str, b: str, threshold: int = 80) -> bool:
    """Match fuzzy entre dois endereços. Usa rapidfuzz se disponível."""
    if not a or not b:
        return False
    try:
        from rapidfuzz import fuzz
        score = fuzz.token_set_ratio(_normalize_address(a), _normalize_address(b))
        return score >= threshold
    except ImportError:
        # Fallback simples: verifica palavras em comum
        words_a = set(_normalize_address(a).split())
        words_b = set(_normalize_address(b).split())
        if not words_a or not words_b:
            return False
        intersection = words_a & words_b
        union = words_a | words_b
        ratio = len(intersection) / len(union) * 100
        return ratio >= (threshold * 0.7)  # threshold relaxado sem rapidfuzz


def _match_with_listings(
    db: Any,
    obituarios: list[dict[str, Any]],
    inventarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cruza sinais de herança com listings publicados nos 90 dias após o óbito."""
    matched: list[dict[str, Any]] = []

    # Combina todas as fontes com data e endereço
    signals_with_date: list[dict[str, Any]] = []
    for item in obituarios + inventarios:
        sig_date = item.get("signal_date")
        if not sig_date:
            continue
        signals_with_date.append(item)

    if not signals_with_date:
        return []

    # Busca listings recentes (janela máxima: mais antigo - hoje)
    dates = [s["signal_date"] for s in signals_with_date if isinstance(s["signal_date"], date)]
    if not dates:
        return []

    oldest = min(dates)
    newest_limit = _today()

    try:
        resp = (
            db.table("listings")
            .select("id, address, neighborhood, first_seen_at, price")
            .gte("first_seen_at", oldest.isoformat())
            .lte("first_seen_at", newest_limit.isoformat())
            .execute()
        )
        listings = resp.data or []
    except Exception:
        logger.warning("[heritage] Falha ao buscar listings", exc_info=True)
        listings = []

    logger.info(f"[heritage] {len(listings)} listings na janela para cruzamento")

    for signal in signals_with_date:
        sig_date = signal["signal_date"]
        if not isinstance(sig_date, date):
            continue
        date_limit = sig_date + timedelta(days=LISTING_MATCH_DAYS)
        sig_endereco = signal.get("endereco") or ""

        best_listing_id: Optional[int] = None
        for listing in listings:
            # Verifica janela temporal
            try:
                first_seen = datetime.fromisoformat(
                    (listing.get("first_seen_at") or "")[:10]
                ).date()
            except (ValueError, TypeError):
                continue

            if not (sig_date <= first_seen <= date_limit):
                continue

            # Match de endereço
            listing_addr = listing.get("address") or ""
            if sig_endereco and listing_addr:
                if _fuzzy_match(sig_endereco, listing_addr):
                    best_listing_id = listing["id"]
                    break

        signal["listing_id"] = best_listing_id
        matched.append(signal)

    return matched


# ---------------------------------------------------------------------------
# 4. Cálculo de confiança e construção dos sinais
# ---------------------------------------------------------------------------


def _build_signals(
    obituarios: list[dict[str, Any]],
    inventarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Monta sinais finais com confidence, cruzando obituários com inventários."""
    signals: list[dict[str, Any]] = []

    # Índice de inventários por nome normalizado
    inv_by_nome: dict[str, dict[str, Any]] = {}
    for inv in inventarios:
        nome = (inv.get("nome_falecido") or "").lower().strip()
        if nome:
            inv_by_nome[nome] = inv

    def _nome_key(nome: Optional[str]) -> str:
        return (nome or "").lower().strip()

    # Processa obituários
    for obit in obituarios:
        nome_key = _nome_key(obit.get("nome_falecido"))
        inv = inv_by_nome.get(nome_key)

        listing_id = obit.get("listing_id")
        has_listing = listing_id is not None
        has_inventario = inv is not None

        if has_listing and has_inventario:
            confidence = 0.9
            signal_type = "listing_post_obit"
            processo_tjsp = inv.get("processo_tjsp")
        elif has_inventario:
            confidence = 0.6
            signal_type = "inventario_tjsp"
            processo_tjsp = inv.get("processo_tjsp")
        else:
            confidence = 0.3
            signal_type = "obituario"
            processo_tjsp = None

        raw_payload = {
            "obituario": {
                "source": obit.get("source"),
                "raw_text": obit.get("raw_text"),
            }
        }
        if inv:
            raw_payload["inventario"] = inv.get("raw_payload") or {}

        signals.append({
            "nome_falecido": obit.get("nome_falecido"),
            "signal_date": obit.get("signal_date"),
            "signal_type": signal_type,
            "endereco": obit.get("endereco"),
            "neighborhood": None,
            "processo_tjsp": processo_tjsp,
            "listing_id": listing_id,
            "desconto_estimado": DESCONTO_ESTIMADO_DEFAULT,
            "confidence": confidence,
            "source": obit.get("source", SOURCE),
            "cpf_hash": None,
            "raw_payload": raw_payload,
        })

    # Inventários sem obituário correspondente
    obit_nomes = {_nome_key(o.get("nome_falecido")) for o in obituarios}
    for inv in inventarios:
        nome_key = _nome_key(inv.get("nome_falecido"))
        if nome_key in obit_nomes:
            continue  # já processado acima

        listing_id = inv.get("listing_id")
        has_listing = listing_id is not None
        confidence = 0.6 if has_listing else 0.3

        signals.append({
            "nome_falecido": inv.get("nome_falecido"),
            "signal_date": inv.get("signal_date"),
            "signal_type": "inventario_tjsp",
            "endereco": None,
            "neighborhood": None,
            "processo_tjsp": inv.get("processo_tjsp"),
            "listing_id": listing_id,
            "desconto_estimado": DESCONTO_ESTIMADO_DEFAULT,
            "confidence": confidence,
            "source": "datajud_tjsp",
            "cpf_hash": None,
            "raw_payload": inv.get("raw_payload") or {},
        })

    return signals


# ---------------------------------------------------------------------------
# 5. Persistência
# ---------------------------------------------------------------------------


def _upsert_signals(db: Any, signals: list[dict[str, Any]]) -> tuple[int, int]:
    """Upsert em heritage_signals. Retorna (created, failed)."""
    if not signals:
        return 0, 0

    rows: list[dict[str, Any]] = []
    for sig in signals:
        sig_date = sig.get("signal_date")
        if isinstance(sig_date, date):
            sig_date_str = sig_date.isoformat()
        else:
            sig_date_str = str(sig_date) if sig_date else None

        # Gera source_id determinístico
        raw_key = f"{sig.get('signal_type')}|{sig.get('nome_falecido')}|{sig.get('processo_tjsp')}|{sig_date_str}"
        source_id = _source_id(SOURCE, raw_key)

        raw_payload = sig.get("raw_payload") or {}

        rows.append({
            "source_id": source_id,
            "signal_date": sig_date_str,
            "signal_type": sig.get("signal_type"),
            "nome_falecido": sig.get("nome_falecido"),
            "cpf_hash": sig.get("cpf_hash"),
            "endereco": sig.get("endereco"),
            "neighborhood": sig.get("neighborhood"),
            "processo_tjsp": sig.get("processo_tjsp"),
            "listing_id": sig.get("listing_id"),
            "desconto_estimado": sig.get("desconto_estimado", DESCONTO_ESTIMADO_DEFAULT),
            "confidence": sig.get("confidence", 0.3),
            "source": sig.get("source", SOURCE),
            "raw_payload": raw_payload,
        })

    created = 0
    failed = 0
    # Upsert em lotes de 50
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i: i + batch_size]
        try:
            db.table("heritage_signals").upsert(
                batch, on_conflict="source_id"
            ).execute()
            created += len(batch)
        except Exception:
            logger.warning(f"[heritage] Falha no upsert lote {i}", exc_info=True)
            failed += len(batch)

    return created, failed


def _register_agent_run(db: Any, stats: dict[str, int]) -> None:
    try:
        db.table("agent_runs").insert({
            "agent": SOURCE,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
        }).execute()
    except Exception:
        logger.warning("[heritage] Falha ao registrar agent_run", exc_info=True)


# ---------------------------------------------------------------------------
# 6. Entry point público
# ---------------------------------------------------------------------------


def run_heritage_detector() -> dict[str, int]:
    """Executa o pipeline completo de detecção de herança.

    Returns:
        {
            "obituarios_found": int,
            "inventarios_found": int,
            "listings_matched": int,
            "signals_created": int,
            "failed": int,
        }
    """
    db = get_client()
    stats: dict[str, int] = {
        "obituarios_found": 0,
        "inventarios_found": 0,
        "listings_matched": 0,
        "signals_created": 0,
        "failed": 0,
    }

    # 1. Coleta
    obituarios = _collect_obituarios()
    inventarios = _collect_inventarios_tjsp()

    stats["obituarios_found"] = len(obituarios)
    stats["inventarios_found"] = len(inventarios)

    # 2. Cruzamento com listings
    all_signals_raw = obituarios + inventarios
    matched = _match_with_listings(db, obituarios, inventarios)

    # Propaga listing_id de volta para as listas originais via índice por nome
    matched_by_nome: dict[str, dict[str, Any]] = {}
    for item in matched:
        nome = (item.get("nome_falecido") or "").lower().strip()
        if nome and item.get("listing_id") is not None:
            matched_by_nome[nome] = item

    # Atualiza listing_id nos obituários
    for obit in obituarios:
        nome = (obit.get("nome_falecido") or "").lower().strip()
        if nome in matched_by_nome:
            obit["listing_id"] = matched_by_nome[nome].get("listing_id")

    # Atualiza listing_id nos inventários
    for inv in inventarios:
        nome = (inv.get("nome_falecido") or "").lower().strip()
        if nome in matched_by_nome:
            inv["listing_id"] = matched_by_nome[nome].get("listing_id")

    stats["listings_matched"] = sum(
        1 for item in (obituarios + inventarios) if item.get("listing_id") is not None
    )

    # 3. Build sinais
    signals = _build_signals(obituarios, inventarios)

    # 4. Persistência
    created, failed = _upsert_signals(db, signals)
    stats["signals_created"] = created
    stats["failed"] = failed

    # 5. Registra execução
    _register_agent_run(db, stats)

    logger.info(f"[heritage] run concluído: {stats}")
    return stats

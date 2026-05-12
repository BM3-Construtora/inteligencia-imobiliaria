"""Consulta a cartórios de registro de imóveis via ARISP/ONR (sob demanda).

================================================================================
REALIDADE DA API — leia antes de tentar usar
================================================================================

ARISP (arisp.com.br) e ONR (registradores.onr.org.br / oficioeletronico.com.br)
são os portais oficiais de registro eletrônico de imóveis em SP/BR. NÃO existe
API pública gratuita — toda consulta é PAGA e exige cadastro prévio.

  * Visualização de matrícula (ARISP)........... ~R$ 10 + R$ 1,80 taxa admin
  * Certidão digital de matrícula (SP).......... ~R$ 72
  * Certidão vintenária (SP).................... ~R$ 95
  * Pesquisa de bens por CPF/CNPJ............... custas estaduais variáveis

Requisitos para acesso programático:
  1. Cadastro prévio no portal Registradores (PF ou PJ).
  2. Saldo pré-pago carregado por boleto/cartão.
  3. Certificado digital ICP-Brasil (PKCS#12) para certas operações.
  4. Login + senha do portal (autenticação por formulário, não OAuth).

Não existe endpoint REST documentado. As opções viáveis são:
  (a) Automação headless do portal (Playwright/Selenium) — frágil, viola ToS.
  (b) Provider terceiro pago (ex.: Infosimples) que abstrai a integração.
  (c) Integração SAEC direta — só para cartórios/órgãos credenciados.

WORKFLOW RECOMENDADO PARA O MARILIABOT
--------------------------------------
Este módulo NÃO faz coleta em batch. É chamado pelo hunter quando um lead
atinge score >= threshold (ex.: top 10 do dia). Antes de gastar R$, verifica
cache em `registry_lookups` (TTL 90 dias). Custo operacional alvo: < R$ 150/mês.

Use:
    from src.collectors.arisp import lookup_by_address, get_cached_lookup

    cached = get_cached_lookup(address)
    if cached:
        data = cached
    else:
        data = lookup_by_address(address, city="Marília")

TODOs (precisam de credenciais reais para implementar)
-----------------------------------------------------
  * TODO: implementar fluxo de login real (form-based) após obter conta PJ.
  * TODO: parsing do PDF/HTML retornado pelo portal — formato varia por cartório.
  * TODO: decidir provider (Infosimples vs. automação própria) — depende de
    volume e tolerância a custo por consulta.
  * TODO: confirmar se Marília-SP usa SAEC-ONR ou portal regional do ARISP
    (cartórios do interior têm cobertura parcial).
================================================================================
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from src.db import get_client

logger = logging.getLogger(__name__)

SOURCE = "arisp"

# Endpoints oficiais (não-API — portais web)
ARISP_PORTAL = "https://www.arisp.com.br/"
ONR_PORTAL = "https://registradores.onr.org.br/"
ONR_CERTIDAO_URL = (
    "https://registradores.onr.org.br/CertidaoDigital/frmPedidosCertidao.aspx"
)

# Credenciais — todas opcionais; ausência = retorna None sem crashar
ARISP_USERNAME = os.getenv("ARISP_USERNAME", "").strip()
ARISP_PASSWORD = os.getenv("ARISP_PASSWORD", "").strip()
ARISP_API_KEY = os.getenv("ARISP_API_KEY", "").strip()  # caso use provider
ARISP_CERT_PATH = os.getenv("ARISP_CERT_PATH", "").strip()  # .pfx ICP-Brasil
ARISP_CERT_PASS = os.getenv("ARISP_CERT_PASS", "").strip()

# Cache TTL: matrícula não muda toda hora, 90d é seguro e economiza R$
CACHE_TTL_DAYS = 90

# Custo médio por consulta (atualizar conforme tabela vigente)
DEFAULT_COST_BRL = 11.80  # visualização ARISP padrão

# Rate limit conservador — portal cartorial não tolera bursts
RATE_LIMIT_SLEEP_S = 3.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}
TIMEOUT = 60


# ---------------------------------------------------------------------------
# API pública do módulo
# ---------------------------------------------------------------------------


def lookup_by_address(
    address: str,
    city: str = "Marília",
    listing_id: int | None = None,
) -> dict[str, Any] | None:
    """Consulta matrícula a partir de endereço. Retorna dict ou None.

    Fluxo:
      1. Verifica cache (`registry_lookups` últimos 90d).
      2. Se ausente, registra lookup com status='pending'.
      3. Chama portal ARISP/ONR — requer credenciais.
      4. Atualiza status para 'fetched'/'failed'/'pay_required'.
    """
    if not address or not address.strip():
        logger.warning(f"[{SOURCE}] lookup_by_address: endereço vazio")
        return None

    cached = get_cached_lookup(address)
    if cached:
        logger.info(f"[{SOURCE}] cache hit para '{address[:60]}'")
        return cached

    if not _has_credentials():
        logger.warning(
            f"[{SOURCE}] credenciais ARISP/ONR ausentes — "
            "defina ARISP_USERNAME/ARISP_PASSWORD ou ARISP_API_KEY. "
            "Pulando consulta paga."
        )
        return None

    db = get_client()
    lookup_id = _register_pending(
        db,
        listing_id=listing_id,
        address=address,
        matricula_number=None,
        registry_office=_guess_office_for_city(city),
    )

    try:
        time.sleep(RATE_LIMIT_SLEEP_S)
        result = _fetch_by_address(address, city)
        return _persist_result(db, lookup_id, result)
    except _PayRequiredError as e:
        logger.warning(f"[{SOURCE}] saldo insuficiente: {e}")
        _mark_status(db, lookup_id, "pay_required", error=str(e))
        return None
    except Exception as e:
        logger.exception(f"[{SOURCE}] lookup_by_address falhou")
        _mark_status(db, lookup_id, "failed", error=str(e))
        return None


def lookup_by_matricula(
    matricula: str,
    office: str,
    listing_id: int | None = None,
) -> dict[str, Any] | None:
    """Consulta matrícula específica em um cartório. Retorna dict ou None.

    `office` é o identificador do cartório (ex.: "1º Oficial de Marília-SP").
    """
    if not matricula or not office:
        logger.warning(f"[{SOURCE}] lookup_by_matricula: matrícula/cartório vazios")
        return None

    cached = _get_cached_by_matricula(matricula, office)
    if cached:
        logger.info(f"[{SOURCE}] cache hit para matrícula {matricula} @ {office}")
        return cached

    if not _has_credentials():
        logger.warning(f"[{SOURCE}] credenciais ausentes — pulando matrícula {matricula}")
        return None

    db = get_client()
    lookup_id = _register_pending(
        db,
        listing_id=listing_id,
        address=None,
        matricula_number=matricula,
        registry_office=office,
    )

    try:
        time.sleep(RATE_LIMIT_SLEEP_S)
        result = _fetch_by_matricula(matricula, office)
        return _persist_result(db, lookup_id, result)
    except _PayRequiredError as e:
        _mark_status(db, lookup_id, "pay_required", error=str(e))
        return None
    except Exception as e:
        logger.exception(f"[{SOURCE}] lookup_by_matricula falhou")
        _mark_status(db, lookup_id, "failed", error=str(e))
        return None


def get_cached_lookup(address: str) -> dict[str, Any] | None:
    """Retorna lookup recente (< CACHE_TTL_DAYS) para evitar gastar R$ duplicado."""
    if not address:
        return None

    cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)).isoformat()
    try:
        db = get_client()
        r = (
            db.table("registry_lookups")
            .select("*")
            .eq("address", address)
            .eq("status", "fetched")
            .gte("fetched_at", cutoff)
            .order("fetched_at", desc=True)
            .limit(1)
            .execute()
        )
        if r.data:
            return r.data[0]
    except Exception:
        logger.exception(f"[{SOURCE}] cache lookup falhou")
    return None


# ---------------------------------------------------------------------------
# Internals — fetch (stubs até ter credenciais reais)
# ---------------------------------------------------------------------------


class _PayRequiredError(Exception):
    """Saldo insuficiente no portal Registradores."""


def _fetch_by_address(address: str, city: str) -> dict[str, Any]:
    """TODO: implementar fluxo real com Playwright/provider.

    Esqueleto sugerido:
      1. POST de login em ONR_PORTAL com ARISP_USERNAME/PASSWORD.
      2. Navegar para busca por endereço (depende do cartório).
      3. Submeter formulário, capturar PDF/HTML da matrícula.
      4. Extrair: proprietário, área, último ITBI, ônus.
      5. Debitar saldo (controle no portal, não local).
    """
    logger.warning(
        f"[{SOURCE}] _fetch_by_address: STUB — fluxo não implementado. "
        f"Necessário: conta PJ ARISP/ONR + credenciais + parser de matrícula. "
        f"Address={address!r} city={city!r}"
    )
    # Placeholder para forçar o caller a tratar como 'failed'
    raise NotImplementedError(
        "ARISP lookup_by_address requer credenciais reais e implementação "
        "do fluxo de login + parsing — ver TODOs no header do módulo."
    )


def _fetch_by_matricula(matricula: str, office: str) -> dict[str, Any]:
    """TODO: implementar consulta direta por número de matrícula.

    Mais barato que busca por endereço pois pula a etapa de localização.
    """
    logger.warning(
        f"[{SOURCE}] _fetch_by_matricula: STUB — fluxo não implementado. "
        f"matricula={matricula!r} office={office!r}"
    )
    raise NotImplementedError(
        "ARISP lookup_by_matricula requer credenciais reais e implementação "
        "do fluxo de consulta — ver TODOs no header do módulo."
    )


# Quando houver credenciais, expor um httpx.Client autenticado reutilizável.
# Mantemos a função pronta para uso futuro.
def _build_client() -> httpx.Client:
    """Cliente httpx autenticado para portal ARISP/ONR.

    Suporte planejado:
      * cookies de sessão após login form-based
      * certificado client (PKCS#12) quando ARISP_CERT_PATH definido
    """
    cert = None
    if ARISP_CERT_PATH:
        # TODO: httpx aceita tuple (cert, key); .pfx precisa ser convertido.
        logger.debug(f"[{SOURCE}] cert ICP-Brasil configurado em {ARISP_CERT_PATH}")
    return httpx.Client(
        headers=HEADERS,
        timeout=TIMEOUT,
        follow_redirects=True,
        cert=cert,
    )


# ---------------------------------------------------------------------------
# Internals — persistência
# ---------------------------------------------------------------------------


def _has_credentials() -> bool:
    return bool(
        (ARISP_USERNAME and ARISP_PASSWORD)
        or ARISP_API_KEY
        or (ARISP_CERT_PATH and ARISP_CERT_PASS)
    )


def _guess_office_for_city(city: str) -> str | None:
    """Heurística mínima até termos mapa cartório <-> bairro/zona."""
    if not city:
        return None
    # TODO: Marília tem 1º e 2º Oficial de Registro de Imóveis; mapear por zona.
    if city.strip().lower() == "marília":
        return "1º Oficial de Registro de Imóveis de Marília-SP"
    return None


def _register_pending(
    db: Any,
    listing_id: int | None,
    address: str | None,
    matricula_number: str | None,
    registry_office: str | None,
) -> int | None:
    try:
        r = db.table("registry_lookups").insert({
            "listing_id": listing_id,
            "address": address,
            "matricula_number": matricula_number,
            "registry_office": registry_office,
            "status": "pending",
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception:
        logger.exception(f"[{SOURCE}] _register_pending falhou")
        return None


def _persist_result(
    db: Any,
    lookup_id: int | None,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    if not lookup_id:
        return result

    update = {
        "status": "fetched",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "property_type": result.get("property_type"),
        "area_m2": result.get("area_m2"),
        "owner_name": result.get("owner_name"),
        "owner_doc": result.get("owner_doc"),
        "last_transaction_date": result.get("last_transaction_date"),
        "last_transaction_value": result.get("last_transaction_value"),
        "encumbrances": result.get("encumbrances"),
        "raw_response": result.get("raw_response"),
        "cost_brl": result.get("cost_brl", DEFAULT_COST_BRL),
        "matricula_number": result.get("matricula_number"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        db.table("registry_lookups").update(update).eq("id", lookup_id).execute()
    except Exception:
        logger.exception(f"[{SOURCE}] _persist_result falhou")
    return {**result, "lookup_id": lookup_id}


def _mark_status(
    db: Any,
    lookup_id: int | None,
    status: str,
    error: str | None = None,
) -> None:
    if not lookup_id:
        return
    update: dict[str, Any] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("registry_lookups").update(update).eq("id", lookup_id).execute()
    except Exception:
        logger.exception(f"[{SOURCE}] _mark_status falhou")


def _get_cached_by_matricula(matricula: str, office: str) -> dict[str, Any] | None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)).isoformat()
    try:
        db = get_client()
        r = (
            db.table("registry_lookups")
            .select("*")
            .eq("matricula_number", matricula)
            .eq("registry_office", office)
            .eq("status", "fetched")
            .gte("fetched_at", cutoff)
            .order("fetched_at", desc=True)
            .limit(1)
            .execute()
        )
        if r.data:
            return r.data[0]
    except Exception:
        logger.exception(f"[{SOURCE}] _get_cached_by_matricula falhou")
    return None

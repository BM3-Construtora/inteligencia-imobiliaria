"""Coletor Mercado Livre — STUB.

STATUS 2026-05-11: Bloqueado por antibot agressivo.

ML detectou padrão de bot e redireciona requests não-autenticados de scraper
para `mercadolivre.com.br/gz/account-verification` (suspicious-traffic-frontend).
Cloudscraper, mesmo com warm-up + UA Chrome, cai no redirect.

Caminhos pra destravar:
  1. Playwright stealth (rebrowser-patches) — IP residencial + JS real.
     Custo: 1-2 dias de implementação + sessão headful em runner com xvfb.
  2. API oficial OAuth — registrar app em developers.mercadolibre.com,
     usar client_credentials. Limite de rate, mas confiável.
     Custo: setup OAuth + cadastro app.
  3. Aceitar gap no MVP — Telhanorte + Leroy já cobrem 2 cotações por SKU.

Decisão MVP: pular. Coletor retorna [] e loga warning. Quando destravar,
trocar `search_products` por implementação real.
"""

from __future__ import annotations

import logging

from src.materials.models import CommonListing

logger = logging.getLogger(__name__)

SUPPLIER_SLUG = "mercadolivre"


def search_products(query: str, **kwargs) -> list[CommonListing]:
    logger.warning(
        f"[mercadolivre] STUB — coletor bloqueado por antibot. "
        f"Query '{query}' ignorada. Ver docstring."
    )
    return []

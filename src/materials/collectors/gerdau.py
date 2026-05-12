"""Coletor Gerdau — STUB.

Gerdau é o maior produtor de aço do Brasil. Não tem e-commerce B2C público
com API consultável. Caminhos possíveis:

1. **Gerdau Mais** (app/portal B2B): portal.gerdaumais.com.br
   Requer login CNPJ. Após OAuth, dá acesso a preço/disponibilidade via API REST.
   Mais confiável — cotação real para construtoras.

2. **Distribuidores autorizados locais** (recomendado a curto prazo):
   Fone/WhatsApp com distribuidores em Marília:
   - Aço Leve / Aço Fácil: distribuidores regionais
   Usar src.materials.manual_quote para persistir cotações manuais.

3. **HTML scraping de distribuidores** com e-commerce próprio:
   Ex: rede de materiais como Metálica ou distribuidores menores com VTEX/Magento.

UNBLOCK: Quando o CNPJ da BM3 tiver acesso ao Gerdau Mais, implementar
OAuth + endpoint /api/v1/products/prices com autenticação Bearer.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SUPPLIER_SLUG = "gerdau"


def search_products(query: str, *, max_results: int = 50) -> list:
    """STUB — Gerdau não tem API pública. Ver docstring do módulo."""
    logger.warning(
        "[gerdau] Coletor não implementado. "
        "Use manual_quote para cotações manuais ou implemente OAuth Gerdau Mais."
    )
    return []

"""Off-market signal collectors.

Cada módulo expõe `run_collector()` retornando
{"processed": int, "created": int, "failed": int}.

Sinais coletados:
- leilao_caixa       — leilões de imóveis Caixa filtrados por Marília-SP
- iptu_devedor       — lista de dívida ativa do município
- alvara_prefeitura  — alvarás de construção via Diário Oficial Municipal
- inventario_tjsp    — processos de inventário (DataJud CNJ)
"""

from __future__ import annotations

from src.collectors.off_market import (
    alvara_prefeitura,
    inventario_tjsp,
    iptu_devedor,
    leilao_caixa,
)

__all__ = [
    "leilao_caixa",
    "iptu_devedor",
    "alvara_prefeitura",
    "inventario_tjsp",
]

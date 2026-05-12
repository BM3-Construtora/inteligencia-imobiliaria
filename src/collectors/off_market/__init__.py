"""Off-market signal collectors.

Cada módulo expõe `run_collector()` retornando
{"processed": int, "created": int, "failed": int}.

Sinais coletados:
- leilao_caixa        — leilões de imóveis Caixa filtrados por Marília-SP
- leilao_generico     — feed configurável (LEILOES_FEED_URL) HTML/RSS de leiloeiros
- iptu_devedor        — lista de dívida ativa do município
- alvara_prefeitura   — alvarás de construção via Diário Oficial Municipal
- inventario_tjsp     — processos de inventário (DataJud CNJ)
- habite_se_marilia   — certificados de conclusão de obra (tabela própria
                        habite_se_records; re-exportado aqui para conveniência
                        do runner).
"""

from __future__ import annotations

from src.collectors import habite_se_marilia
from src.collectors.off_market import (
    alvara_prefeitura,
    inventario_tjsp,
    iptu_devedor,
    leilao_caixa,
    leilao_generico,
)

__all__ = [
    "leilao_caixa",
    "leilao_generico",
    "iptu_devedor",
    "alvara_prefeitura",
    "inventario_tjsp",
    "habite_se_marilia",
]

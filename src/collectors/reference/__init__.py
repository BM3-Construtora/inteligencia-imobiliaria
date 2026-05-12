"""Coletores de DADOS DE REFERÊNCIA (não-signal).

Diferem de `off_market/`: aqui ficam tabelas usadas para calibrar AVM,
floor prices e regras de oportunidade. Cadência típica é anual.

Módulos:
- iptu_planta_marilia  — Planta Genérica de Valores IPTU Marília-SP (R$/m²)
"""

from __future__ import annotations

from src.collectors import iptu_planta_marilia

__all__ = ["iptu_planta_marilia"]

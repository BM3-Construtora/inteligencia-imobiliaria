"""Collector for Toca Imóveis (Supabase REST API)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import TOCA_SUPABASE_URL, TOCA_ANON_KEY, MAX_PAGES_PER_SPIDER
from src.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


def _is_marilia(city: str | None) -> bool:
    if not city:
        return False
    c = city.lower().replace('í', 'i').strip()
    return c in {'marilia', 'mar?lia', 'marília'.lower().replace('í', 'i')}


TOCA_SELECT_FIELDS = (
    "id,titulo,tipo_imovel,cidade,bairro_nome,endereco,nome_edificio,"
    "valor,valor_aluguel,dormitorios,banheiros,suites,a_construida,"
    "a_terreno,garagem,descricao,foto_thumb,imovel_fotos,lati,longi,"
    "flag_mostra_site_ven,flag_mostra_site_loc,destaque,destaque_locacao,"
    "destaque_venda,exclusividade_locacao,exclusividade_vendas,aluga_rapido,"
    "caracteristicas,zona_nome,pontos_referencia"
)


class TocaCollector(BaseCollector):
    """Collects properties from Toca Imóveis Supabase REST API."""

    source = "toca"

    async def fetch_all(self) -> list[dict[str, Any]]:
        if not TOCA_ANON_KEY or not TOCA_SUPABASE_URL:
            raise RuntimeError(
                "TOCA_ANON_KEY/TOCA_SUPABASE_URL não configuradas — "
                "defina os secrets/env vars para coletar da Toca."
            )
        all_items: list[dict[str, Any]] = []
        filtered_other_city = 0
        headers = {
            "apikey": TOCA_ANON_KEY,
            "Authorization": f"Bearer {TOCA_ANON_KEY}",
            "Prefer": "count=exact",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            offset = 0
            page = 0
            total = None

            while page < MAX_PAGES_PER_SPIDER:
                logger.info(
                    f"[toca] Fetching offset {offset} "
                    f"(page {page + 1}, total: {total or '?'})"
                )

                resp = await client.get(
                    f"{TOCA_SUPABASE_URL}/rest/v1/properties_public",
                    headers=headers,
                    params={
                        "select": TOCA_SELECT_FIELDS,
                        "has_valid_photos": "eq.true",
                        "flag_mostra_site_ven": "eq.1",
                        "valor": "gt.0",
                        "cidade": "ilike.*maril*",
                        "order": "updated_at.desc",
                        "offset": offset,
                        "limit": PAGE_SIZE,
                    },
                )
                resp.raise_for_status()

                # Parse total from content-range header
                if total is None:
                    content_range = resp.headers.get("content-range", "")
                    if "/" in content_range:
                        total = int(content_range.split("/")[1])

                items = resp.json()
                if not items:
                    break

                # Client-side safety net: drop any row whose city isn't Marília
                kept = []
                for row in items:
                    if not _is_marilia(row.get('cidade')):
                        filtered_other_city += 1
                        continue
                    kept.append(row)
                all_items.extend(kept)
                logger.info(
                    f"[toca] Page {page + 1}: {len(items)} items "
                    f"(total so far: {len(all_items)})"
                )

                offset += PAGE_SIZE
                page += 1

                if total and offset >= total:
                    break

        logger.info(
            f"[toca] Total fetched: {len(all_items)} items "
            f"(filtered_other_city={filtered_other_city})"
        )
        self.stats['filtered_other_city'] = filtered_other_city
        return all_items

    def extract_source_id(self, item: dict[str, Any]) -> str:
        return str(item["id"])

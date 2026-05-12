"""SKU discovery via LLM.

Pega `material_listing` órfãos (sku_id NULL) com fornecedor ativo, agrupa por
chave aproximada (nome + marca), pede ao Gemini que normalize em SKU canônico
(category, brand, model, unit, weight_kg), e cria `material_sku` com seed=false.

Idempotência:
  - Não cria duplicado quando EAN bate em SKU existente
  - Match por canonical_name normalizado também evita duplicar

Cost control:
  - Batch de 20 listings por chamada LLM
  - Limite de 100 listings/run por padrão (`MATERIALS_DISCOVERY_LIMIT`)

Uso:
    python -m src.materials.discovery
    python -m src.materials.discovery --limit 50 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections import defaultdict
from typing import Any

from src.db import get_client
from src.llm import _generate, _parse_json

logger = logging.getLogger(__name__)

CATEGORIES = [
    "cimento", "agregado", "aco", "bloco", "argamassa",
    "hidraulica", "eletrica", "cobertura", "revestimento",
    "tinta", "madeira", "ferramenta", "epi", "outro",
]
UNITS = [
    "saco_50kg", "saco_25kg", "saco_20kg", "saco_15kg", "saco_5kg",
    "barra_12m", "barra_6m", "barra_3m", "m2", "m3", "metro_linear",
    "balde_18l", "balde_20l", "lata_3_6l", "rolo_100m", "rolo_50m",
    "un", "milheiro", "caixa", "outro",
]

DISCOVERY_LIMIT = int(os.getenv("MATERIALS_DISCOVERY_LIMIT", "100"))
BATCH_SIZE = 20


PROMPT_TEMPLATE = """Você normaliza nomes de produtos de loja de material de construção em SKUs canônicos.

Para cada item da lista, retorne JSON com:
- "i": índice (inteiro, mesmo do input)
- "category": uma das [{categories}]
- "brand": marca normalizada em Title Case, ou null
- "model": variante/tipo (ex: "CP II F 32", "CA-50 8mm", "Esmaltado 60x60"), ou null
- "unit": uma das [{units}]
- "weight_kg": peso unitário em kg, ou null
- "canonical_name": nome canônico curto e padronizado (ex: "Cimento CP II F 32 50kg Votoran")

Regras:
- Ignore item irrelevante (ex: "removedor de cimento" não é cimento — category="outro")
- Se nome ambíguo demais, category="outro"
- canonical_name deve ser deterministico para o mesmo produto em lojas diferentes
- Retorne SEMPRE JSON válido como {{"items": [...]}}, sem markdown

Entrada:
{items}
"""


def run_discovery(limit: int = DISCOVERY_LIMIT, dry_run: bool = False) -> dict[str, int]:
    """Roda discovery em batch. Retorna stats."""
    stats: dict[str, int] = defaultdict(int)
    db = get_client()

    orphans = _load_orphans(db, limit)
    stats["orphans_fetched"] = len(orphans)
    if not orphans:
        logger.info("[discovery] sem listings órfãos pra processar")
        return dict(stats)

    grouped = _group_by_signature(orphans)
    stats["unique_groups"] = len(grouped)
    logger.info(
        f"[discovery] {len(orphans)} listings órfãos → {len(grouped)} grupos únicos"
    )

    # representative = primeiro listing de cada grupo
    representatives = [members[0] for members in grouped.values() if members]
    canonical_name_to_sku_id: dict[str, int] = {}

    for batch_start in range(0, len(representatives), BATCH_SIZE):
        batch = representatives[batch_start:batch_start + BATCH_SIZE]
        normalized = _normalize_batch(batch)
        if not normalized:
            stats["llm_failures"] += 1
            continue

        for idx, norm in enumerate(normalized):
            if idx >= len(batch):
                continue
            rep = batch[idx]
            if norm.get("category") == "outro":
                stats["skipped_outro"] += 1
                continue

            canonical_name = (norm.get("canonical_name") or "").strip()
            if not canonical_name:
                stats["skipped_no_name"] += 1
                continue

            if dry_run:
                stats["would_create"] += 1
                continue

            try:
                sku_id = _upsert_canonical_sku(db, canonical_name, norm, rep, canonical_name_to_sku_id)
                if sku_id is None:
                    stats["skipped_existing"] += 1
                    continue
            except Exception:
                logger.exception(f"[discovery] upsert SKU falhou para '{canonical_name}'")
                stats["upsert_failures"] += 1
                continue

            # Backfill: liga todos os listings desse grupo ao SKU canônico
            group_key = _signature(rep)
            group = grouped.get(group_key, [])
            try:
                _link_listings_to_sku(db, group, sku_id)
                stats["sku_created"] += 1
                stats["listings_linked"] += len(group)
            except Exception:
                logger.exception(f"[discovery] link listings → sku {sku_id} falhou")
                stats["link_failures"] += 1

    logger.info(f"[discovery] Done: {dict(stats)}")
    return dict(stats)


# ---------------------------------------------------------------------------
def _load_orphans(db, limit: int) -> list[dict[str, Any]]:
    resp = (
        db.table("material_listing")
        .select("id,supplier_id,supplier_name,supplier_ean,supplier_sku")
        .is_("sku_id", "null")
        .eq("is_active", True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def _signature(listing: dict[str, Any]) -> str:
    """Chave de agrupamento estável. Nome canonizado + EAN se houver."""
    ean = (listing.get("supplier_ean") or "").strip()
    if ean:
        return f"ean:{re.sub(r'[^0-9]', '', ean)}"
    name = _norm_text(listing.get("supplier_name"))
    return f"name:{name}"


def _group_by_signature(orphans: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Mantém um representante por grupo. Demais ficam no value pro backfill."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in orphans:
        out[_signature(o)].append(o)
    return out


def _normalize_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    items_payload = [
        {"i": idx, "name": item.get("supplier_name", ""), "ean": item.get("supplier_ean")}
        for idx, item in enumerate(batch)
    ]
    prompt = PROMPT_TEMPLATE.format(
        categories=", ".join(CATEGORIES),
        units=", ".join(UNITS),
        items=json.dumps(items_payload, ensure_ascii=False),
    )

    response = _generate(prompt, max_tokens=4000)
    if not response:
        return None

    parsed = _parse_json(response)
    if not parsed:
        return None
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return None

    # Reordena pelo índice retornado, com fallback pra posicional
    result: list[dict[str, Any]] = [{} for _ in batch]
    for entry in items:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("i")
        if isinstance(idx, int) and 0 <= idx < len(batch):
            result[idx] = entry
    return result


def _upsert_canonical_sku(
    db,
    canonical_name: str,
    norm: dict[str, Any],
    rep: dict[str, Any],
    cache: dict[str, int],
) -> int | None:
    """Cria SKU canônico ou retorna None se já existe (match por EAN ou canonical_name)."""
    ean = _clean_ean(rep.get("supplier_ean"))
    if ean:
        existing = (
            db.table("material_sku").select("id").eq("ean", ean).limit(1).execute()
        )
        if existing.data:
            cache[canonical_name] = existing.data[0]["id"]
            return None

    if canonical_name in cache:
        return cache[canonical_name]

    existing_name = (
        db.table("material_sku")
        .select("id")
        .eq("canonical_name", canonical_name)
        .limit(1)
        .execute()
    )
    if existing_name.data:
        sku_id = existing_name.data[0]["id"]
        cache[canonical_name] = sku_id
        return None  # já existe → não conta como novo

    payload = {
        "canonical_name": canonical_name,
        "category": norm.get("category") or "outro",
        "brand": norm.get("brand"),
        "model": norm.get("model"),
        "unit": norm.get("unit") or "outro",
        "weight_kg": norm.get("weight_kg"),
        "ean": ean,
        "seed": False,
    }
    resp = db.table("material_sku").insert(payload).execute()
    if not resp.data:
        return None
    sku_id = resp.data[0]["id"]
    cache[canonical_name] = sku_id
    return sku_id


def _link_listings_to_sku(db, group: list[dict[str, Any]], sku_id: int) -> None:
    ids = [row["id"] for row in group if row.get("id") is not None]
    if not ids:
        return
    (
        db.table("material_listing")
        .update({"sku_id": sku_id})
        .in_("id", ids)
        .execute()
    )


def _norm_text(text: Any) -> str:
    if not text:
        return ""
    t = str(text).lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _clean_ean(value: Any) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\D", "", str(value))
    return cleaned or None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=DISCOVERY_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_discovery(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

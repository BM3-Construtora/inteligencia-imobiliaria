"""Orquestrador do pipeline de materiais.

Fluxo:
    1. Carrega seeds (10 SKUs MVP) e upserta material_sku
    2. Para cada (supplier, sku, query), chama coletor
    3. Para cada listing retornado, faz match → sku_id
    4. Upsert material_listing (UNIQUE supplier_id, supplier_sku)
    5. Insert material_price_history

Uso:
    python -m src.materials.runner
    python -m src.materials.runner --supplier leroy_merlin
    python -m src.materials.runner --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.db import get_client
from src.materials.collectors import leroy, telhanorte
from src.materials.matcher import SkuCandidate, match
from src.materials.models import CommonListing, from_leroy, from_vtex

logger = logging.getLogger(__name__)

SEEDS_PATH = Path(__file__).parent / "seeds" / "sku_seeds.json"


# (supplier_slug → função que recebe query e retorna list[CommonListing])
def _leroy_search(query: str) -> list[CommonListing]:
    return [from_leroy(i) for i in leroy.search_products(query, max_results=50)]


def _telhanorte_search(query: str) -> list[CommonListing]:
    return [from_vtex(i, "telhanorte") for i in telhanorte.search_products(query, max_results=50)]


SEARCHERS: dict[str, Callable[[str], list[CommonListing]]] = {
    "leroy_merlin": _leroy_search,
    "telhanorte": _telhanorte_search,
}

# Sleep entre queries (sec). Suppliers com antibot agressivo precisam pausar.
QUERY_SLEEP: dict[str, tuple[float, float]] = {
    "leroy_merlin": (3.0, 6.0),
}


def run(supplier_filter: str | None = None, dry_run: bool = False) -> dict[str, int]:
    """Roda pipeline. Retorna stats agregadas."""
    stats: dict[str, int] = defaultdict(int)
    db = get_client()

    seeds = json.loads(SEEDS_PATH.read_text())["skus"]
    logger.info(f"[materials] {len(seeds)} SKUs seed carregados")

    sku_id_by_seed = _upsert_seed_skus(db, seeds, dry_run=dry_run)
    candidates = _load_sku_candidates(db, sku_id_by_seed, seeds, dry_run=dry_run)
    supplier_id_by_slug = _load_active_suppliers(db)

    if supplier_filter:
        supplier_id_by_slug = {
            k: v for k, v in supplier_id_by_slug.items() if k == supplier_filter
        }
        if not supplier_id_by_slug:
            logger.warning(f"[materials] Supplier '{supplier_filter}' não encontrado ou inativo")
            return dict(stats)

    run_start_iso = datetime.now(timezone.utc).isoformat()

    for supplier_slug, supplier_id in supplier_id_by_slug.items():
        search = SEARCHERS.get(supplier_slug)
        if search is None:
            logger.info(f"[materials] Sem coletor para '{supplier_slug}', pulando")
            continue

        supplier_start_iso = datetime.now(timezone.utc).isoformat()
        queries = _collect_queries(seeds)
        seen_supplier_skus: set[str] = set()
        sleep_range = QUERY_SLEEP.get(supplier_slug)

        for q_idx, query in enumerate(queries):
            if sleep_range and q_idx > 0:
                time.sleep(random.uniform(*sleep_range))
            try:
                listings = search(query)
            except Exception:
                logger.exception(f"[materials] {supplier_slug} query='{query}' falhou")
                stats[f"{supplier_slug}_query_failures"] += 1
                continue

            stats[f"{supplier_slug}_listings_fetched"] += len(listings)

            for listing in listings:
                if not listing.supplier_sku or listing.supplier_sku in seen_supplier_skus:
                    continue
                seen_supplier_skus.add(listing.supplier_sku)

                sku_id = match(listing, candidates)
                if sku_id is None:
                    stats[f"{supplier_slug}_unmatched"] += 1
                else:
                    stats[f"{supplier_slug}_matched"] += 1

                if dry_run:
                    continue

                try:
                    listing_id = _upsert_listing(db, listing, supplier_id, sku_id)
                    inserted = _insert_price_history_if_changed(db, listing_id, listing)
                    stats[f"{supplier_slug}_persisted"] += 1
                    if inserted:
                        stats[f"{supplier_slug}_price_inserts"] += 1
                    else:
                        stats[f"{supplier_slug}_price_unchanged"] += 1
                except Exception:
                    logger.exception(
                        f"[materials] persist falhou supplier={supplier_slug} "
                        f"sku={listing.supplier_sku}"
                    )
                    stats[f"{supplier_slug}_persist_failures"] += 1

        # Deactivation: listings desse supplier não vistos desde supplier_start.
        # Só executa se a run desse supplier coletou pelo menos 1 listing,
        # senão um erro de coleta marcaria tudo como inativo.
        if not dry_run and stats[f"{supplier_slug}_persisted"] > 0:
            deactivated = _deactivate_stale_listings(db, supplier_id, supplier_start_iso)
            stats[f"{supplier_slug}_deactivated"] = deactivated

    logger.info(f"[materials] Stats: {dict(stats)}")
    return dict(stats)


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------
def _upsert_seed_skus(db, seeds: list[dict], *, dry_run: bool) -> dict[str, int]:
    """Upsert dos SKUs seed. Retorna {canonical_name: sku_id}."""
    if dry_run:
        return {}

    out: dict[str, int] = {}
    for s in seeds:
        payload = {
            "canonical_name": s["canonical_name"],
            "category": s["category"],
            "brand": s.get("brand"),
            "model": s.get("model"),
            "unit": s["unit"],
            "weight_kg": s.get("weight_kg"),
            "ean": s.get("ean"),
            "seed": True,
            "bom_stage": s.get("bom_stage"),
        }
        ean = payload["ean"]
        if ean:
            resp = (
                db.table("material_sku")
                .upsert(payload, on_conflict="ean")
                .execute()
            )
        else:
            existing = (
                db.table("material_sku")
                .select("id")
                .eq("canonical_name", payload["canonical_name"])
                .execute()
            )
            if existing.data:
                resp = (
                    db.table("material_sku")
                    .update(payload)
                    .eq("id", existing.data[0]["id"])
                    .execute()
                )
            else:
                resp = db.table("material_sku").insert(payload).execute()

        if resp.data:
            out[s["canonical_name"]] = resp.data[0]["id"]

    return out


def _load_sku_candidates(
    db,
    sku_id_by_seed: dict[str, int],
    seeds: list[dict],
    *,
    dry_run: bool = False,
) -> list[SkuCandidate]:
    """Constrói lista de candidatos para o matcher.

    Em dry-run, usa os próprios seeds em memória com id sintético (índice).
    Caso normal, usa todos os SKUs com flag seed=true no banco (inclui SKUs
    descobertos em runs anteriores).
    """
    if dry_run:
        return [
            SkuCandidate(
                id=-(idx + 1),
                canonical_name=s["canonical_name"],
                brand=s.get("brand"),
                ean=s.get("ean"),
                model=s.get("model"),
            )
            for idx, s in enumerate(seeds)
        ]

    resp = db.table("material_sku").select("id,canonical_name,brand,model,ean").eq("seed", True).execute()
    return [
        SkuCandidate(
            id=row["id"],
            canonical_name=row["canonical_name"],
            brand=row.get("brand"),
            ean=row.get("ean"),
            model=row.get("model"),
        )
        for row in (resp.data or [])
    ]


def _load_active_suppliers(db) -> dict[str, int]:
    resp = (
        db.table("material_supplier")
        .select("id,slug")
        .eq("is_active", True)
        .eq("delivers_to_marilia", True)
        .execute()
    )
    return {row["slug"]: row["id"] for row in (resp.data or [])}


def _collect_queries(seeds: list[dict]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for s in seeds:
        for q in s.get("search_queries") or [s["canonical_name"]]:
            q_norm = q.strip().lower()
            if q_norm and q_norm not in seen:
                seen.add(q_norm)
                queries.append(q)
    return queries


def _upsert_listing(db, listing: CommonListing, supplier_id: int, sku_id: int | None) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "supplier_id": supplier_id,
        "supplier_sku": listing.supplier_sku,
        "supplier_name": listing.supplier_name,
        "supplier_ean": listing.ean,
        "sku_id": sku_id,
        "url": listing.url,
        "is_active": listing.is_available,
        "last_seen_at": now_iso,
        "raw_payload": listing.raw,
    }
    resp = (
        db.table("material_listing")
        .upsert(payload, on_conflict="supplier_id,supplier_sku")
        .execute()
    )
    if not resp.data:
        raise RuntimeError("upsert material_listing sem retorno")
    return resp.data[0]["id"]


def _insert_price_history_if_changed(db, listing_id: int, listing: CommonListing) -> bool:
    """Insere snapshot só se preço/availability mudou vs último. Retorna True se inseriu."""
    effective_price = listing.region_price if listing.region_price is not None else listing.price
    if effective_price is None:
        return False

    last = (
        db.table("material_price_history")
        .select("price,is_available,region_price")
        .eq("listing_id", listing_id)
        .order("collected_at", desc=True)
        .limit(1)
        .execute()
    )
    if last.data:
        prev = last.data[0]
        same_price = _num_eq(prev.get("price"), effective_price)
        same_region = _num_eq(prev.get("region_price"), listing.region_price)
        same_avail = bool(prev.get("is_available")) == bool(listing.is_available)
        if same_price and same_region and same_avail:
            return False

    payload = {
        "listing_id": listing_id,
        "price": effective_price,
        "list_price": listing.list_price,
        "region_price": listing.region_price,
        "is_available": listing.is_available,
    }
    db.table("material_price_history").insert(payload).execute()
    return True


def _num_eq(a, b, tol: float = 0.005) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def _deactivate_stale_listings(db, supplier_id: int, cutoff_iso: str) -> int:
    """Marca is_active=false em listings ativos não vistos desde cutoff."""
    resp = (
        db.table("material_listing")
        .update({"is_active": False})
        .eq("supplier_id", supplier_id)
        .eq("is_active", True)
        .lt("last_seen_at", cutoff_iso)
        .execute()
    )
    return len(resp.data or [])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--supplier", help="Filtra um único supplier por slug")
    parser.add_argument("--dry-run", action="store_true", help="Não escreve no banco")
    args = parser.parse_args()
    run(supplier_filter=args.supplier, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

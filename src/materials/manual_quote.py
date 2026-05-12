"""CLI pra cadastrar cotação manual de fornecedor local sem site.

Uso típico:
    # Cotação rápida (concreto usinado):
    python -m src.materials.manual_quote \\
        --supplier polimix_marilia \\
        --canonical "Concreto usinado fck 25 MPa bombeado" \\
        --category outro --unit m3 \\
        --price 480 --quantity 1 \\
        --note "frete incluído 5km"

    # Cotação de areia (gera SKU canônico novo se necessário):
    python -m src.materials.manual_quote \\
        --supplier areal_local_marilia \\
        --canonical "Areia média lavada m3" \\
        --category agregado --unit m3 \\
        --price 95

O CLI cria/atualiza material_sku canônico (seed=false), garante listing
do fornecedor e grava price_history com source='manual'.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from src.db import get_client
from src.materials.normalize import compute as normalize_price

logger = logging.getLogger(__name__)


def submit(
    supplier_slug: str,
    canonical_name: str,
    category: str,
    unit: str,
    price: float,
    *,
    brand: str | None = None,
    model: str | None = None,
    weight_kg: float | None = None,
    ean: str | None = None,
    quantity: int = 1,
    shipping_cost: float | None = None,
    note: str | None = None,
) -> dict:
    """Insere cotação manual. Retorna dict com ids criados."""
    db = get_client()

    sup = (
        db.table("material_supplier")
        .select("id,name")
        .eq("slug", supplier_slug)
        .limit(1)
        .execute()
    )
    if not sup.data:
        raise SystemExit(f"Supplier '{supplier_slug}' não cadastrado")
    supplier_id = sup.data[0]["id"]

    sku_id = _ensure_sku(db, canonical_name, category, unit, brand, model, weight_kg, ean)
    listing_id = _ensure_listing(db, supplier_id, sku_id, canonical_name, ean, note)

    effective_price = price / max(quantity, 1) if quantity > 1 else price
    norm = normalize_price(
        price=effective_price,
        category=category,
        unit=unit,
        weight_kg=weight_kg,
        supplier_name=canonical_name,
    )

    payload = {
        "listing_id": listing_id,
        "price": effective_price,
        "list_price": None,
        "region_price": None,
        "is_available": True,
        "shipping_cost": shipping_cost,
        "can_deliver_marilia": True,
        "price_per_kg": norm.price_per_kg,
        "price_per_m2": norm.price_per_m2,
        "price_per_unit": norm.price_per_unit,
        "is_outlier": norm.is_outlier,
        "outlier_reason": norm.outlier_reason,
        "source": "manual",
    }
    resp = db.table("material_price_history").insert(payload).execute()

    return {
        "supplier_id": supplier_id,
        "sku_id": sku_id,
        "listing_id": listing_id,
        "price_history_id": resp.data[0]["id"] if resp.data else None,
        "price_per_kg": norm.price_per_kg,
        "is_outlier": norm.is_outlier,
    }


def _ensure_sku(
    db,
    canonical_name: str,
    category: str,
    unit: str,
    brand: str | None,
    model: str | None,
    weight_kg: float | None,
    ean: str | None,
) -> int:
    if ean:
        existing = db.table("material_sku").select("id").eq("ean", ean).limit(1).execute()
        if existing.data:
            return existing.data[0]["id"]
    existing = (
        db.table("material_sku")
        .select("id")
        .eq("canonical_name", canonical_name)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    resp = (
        db.table("material_sku")
        .insert({
            "canonical_name": canonical_name,
            "category": category,
            "brand": brand,
            "model": model,
            "unit": unit,
            "weight_kg": weight_kg,
            "ean": ean,
            "seed": False,
        })
        .execute()
    )
    return resp.data[0]["id"]


def _ensure_listing(
    db,
    supplier_id: int,
    sku_id: int,
    canonical_name: str,
    ean: str | None,
    note: str | None,
) -> int:
    supplier_sku = f"manual:{sku_id}"
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "supplier_id": supplier_id,
        "supplier_sku": supplier_sku,
        "supplier_name": canonical_name,
        "supplier_ean": ean,
        "sku_id": sku_id,
        "url": None,
        "is_active": True,
        "last_seen_at": now_iso,
        "raw_payload": {"manual_note": note} if note else {},
    }
    resp = (
        db.table("material_listing")
        .upsert(payload, on_conflict="supplier_id,supplier_sku")
        .execute()
    )
    return resp.data[0]["id"]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Cadastrar cotação manual.")
    parser.add_argument("--supplier", required=True, help="slug do fornecedor")
    parser.add_argument("--canonical", required=True, help="canonical_name do SKU")
    parser.add_argument("--category", required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--price", required=True, type=float)
    parser.add_argument("--brand")
    parser.add_argument("--model")
    parser.add_argument("--weight-kg", type=float)
    parser.add_argument("--ean")
    parser.add_argument("--quantity", type=int, default=1, help="dividir preço se for cotação por lote")
    parser.add_argument("--shipping-cost", type=float)
    parser.add_argument("--note")
    args = parser.parse_args()

    out = submit(
        supplier_slug=args.supplier,
        canonical_name=args.canonical,
        category=args.category,
        unit=args.unit,
        price=args.price,
        brand=args.brand,
        model=args.model,
        weight_kg=args.weight_kg,
        ean=args.ean,
        quantity=args.quantity,
        shipping_cost=args.shipping_cost,
        note=args.note,
    )
    print(out, file=sys.stdout)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Congela o dataset do Experimento A (TCC, Cap. 5) num arquivo versionado.

Motivação: o `listings` do Supabase evolui todo dia (novas coletas, mudança de
`is_active`), então rodar `eval_avm.py` contra o banco vivo não reproduz os
números do TCC. Este script fixa o coorte usado no trabalho — terrenos coletados
até jul/2026 que ainda estavam ativos — na forma da matriz de atributos já
extraída (com `days_listed` congelado), permitindo que `eval_avm.py` rode offline
e reproduza exatamente as tabelas para sempre.

Uso:  PYTHONPATH=. python3 scripts/freeze_avm_snapshot.py
Saída: docs/avm_snapshot.json
"""
from __future__ import annotations

import json

from src.db import get_client
from src.price_model import (
    _fetch_agronegocio_indice, _fetch_market_heat, _build_neigh_avg_price_m2,
    _fetch_obras_map, _fetch_parcelamentos_map, _extract_rows,
)

CUTOFF = "2026-08"  # coletas a partir de agosto/2026 ficam de fora (lote posterior ao TCC)
OUT = "docs/avm_snapshot.json"


def _fetch_land(db):
    out, page, off = [], 1000, 0
    while True:
        r = (db.table("listings")
             .select("id, sale_price, total_area, price_per_m2, neighborhood, "
                     "latitude, longitude, is_mcmv, features, first_seen_at, is_active")
             .eq("property_type", "land").is_("canonical_listing_id", "null")
             .not_.is_("sale_price", "null").gt("sale_price", 5000)
             .not_.is_("total_area", "null").gt("total_area", 15)
             .range(off, off + page - 1).execute())
        if not r.data:
            break
        out.extend(r.data)
        if len(r.data) < page:
            break
        off += page
    return out


def main() -> None:
    db = get_client()
    land = _fetch_land(db)
    cohort = [l for l in land
              if l.get("is_active") and (l.get("first_seen_at") or "9999") < CUTOFF]

    agro = _fetch_agronegocio_indice(db)
    for l in cohort:
        l["_agronegocio_indice"] = agro
    heat = _fetch_market_heat(db)
    obras = _fetch_obras_map(db)
    parcel = _fetch_parcelamentos_map(db)

    # Matriz estática (days_listed já congelado; centroides são determinísticos).
    # A coluna 1 (neigh_price) e o target-encoding são recomputados por split no
    # eval, então aqui guardamos também price_per_m2 e y para permitir isso.
    neigh_all = _build_neigh_avg_price_m2(cohort)
    X, y, ids, neighs = _extract_rows(cohort, neigh_all, heat, obras, parcel)

    by_id = {int(l["id"]): l for l in cohort}
    rows = []
    for xi, yi, idi, nb in zip(X, y, ids, neighs):
        ppm2 = by_id[idi].get("price_per_m2")
        rows.append({
            "id": idi, "y": float(yi), "area": float(xi[0]), "neigh": nb,
            "ppm2": (float(ppm2) if ppm2 else None), "x": [float(v) for v in xi],
        })

    snap = {
        "meta": {
            "description": "Coorte congelado do Experimento A (TCC Cap. 5)",
            "cutoff_first_seen_at": CUTOFF, "filter": "property_type=land, is_active, "
            "sale_price>5000, total_area>15, canonical_listing_id null",
            "n": len(rows), "quantiles": [0.10, 0.25, 0.50, 0.75, 0.90],
            "feature_names_note": "x[] segue FEATURE_NAMES de src.price_model; "
            "x[1] (neigh_price) e o target-encoding são recomputados por split (train-only)",
        },
        "rows": rows,
    }
    with open(OUT, "w") as f:
        json.dump(snap, f, ensure_ascii=False)
    print(f"OK -> {OUT}  (N={len(rows)})")


if __name__ == "__main__":
    main()

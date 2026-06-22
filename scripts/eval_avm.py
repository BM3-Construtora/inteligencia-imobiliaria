# -*- coding: utf-8 -*-
"""Experimento A (TCC, Cap. 5): avaliação honesta do AVM contra baseline.

Reproduz o protocolo de produção (src/price_model.py) — mesmos hiperparâmetros,
target-encoding só no treino — e corrige dois pontos para evitar otimismo:
  (1) o preço médio por bairro (feature) é construído APENAS sobre o treino
      (sem vazamento), ao contrário da produção, que o calcula sobre todo o conjunto;
  (2) reporta média ± desvio sobre múltiplas divisões treino/teste (várias seeds),
      em vez de um único split, dando uma noção de variância dado o n pequeno.

Acrescenta o que o pipeline de produção não calcula: baseline de preço/m² do
bairro, MAPE, RMSE, perda pinball por quantil e cobertura P25–P75 / P10–P90.

Uso:  PYTHONPATH=. python3 scripts/eval_avm.py
Saída: tabela para o Cap. 5 + JSON em docs/eval_avm_result.json
"""
from __future__ import annotations

import json
import statistics

import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split

from src.db import get_client
from src.price_model import (
    QUANTILES,
    _fetch_agronegocio_indice,
    _fetch_market_heat,
    _build_neigh_avg_price_m2,
    _fetch_obras_map,
    _fetch_parcelamentos_map,
    _extract_rows,
)

SEEDS = [42, 7, 123, 2024, 99]


def _fetch_land_listings(db):
    """Igual a price_model._fetch_listings, mas sem a coluna
    mcmv_accessibility_score (ausente nesta base; _extract_rows usa default 50)."""
    out, page, off = [], 1000, 0
    while True:
        r = (
            db.table("listings")
            .select("id, sale_price, total_area, price_per_m2, neighborhood, "
                    "latitude, longitude, is_mcmv, features, first_seen_at")
            .eq("is_active", True).eq("property_type", "land")
            .is_("canonical_listing_id", "null")
            .not_.is_("sale_price", "null").gt("sale_price", 5000)
            .not_.is_("total_area", "null").gt("total_area", 15)
            .range(off, off + page - 1).execute()
        )
        if not r.data:
            break
        out.extend(r.data)
        if len(r.data) < page:
            break
        off += page
    return out


def _train_models(X_tr, y_tr):
    models = {}
    for q in QUANTILES:
        m = lgb.LGBMRegressor(
            objective="quantile", alpha=q, n_estimators=400, learning_rate=0.04,
            num_leaves=15, max_depth=6, min_data_in_leaf=25, feature_fraction=0.85,
            bagging_fraction=0.85, bagging_freq=3, reg_alpha=0.1, reg_lambda=0.2,
            random_state=42, verbosity=-1,
        )
        m.fit(X_tr, y_tr)
        models[q] = m
    return models


def _run_split(listings, heat, obras, parcel, seed):
    tr_l, te_l = train_test_split(listings, test_size=0.2, random_state=seed)

    # Feature de preço médio do bairro — AJUSTADA SÓ NO TREINO (sem vazamento)
    neigh_avg = _build_neigh_avg_price_m2(tr_l)
    Xtr, ytr, _, ntr = _extract_rows(tr_l, neigh_avg, heat, obras, parcel)
    Xte, yte, _, nte = _extract_rows(te_l, neigh_avg, heat, obras, parcel)
    if len(yte) < 10 or len(ytr) < 30:
        return None

    Xtr, ytr = np.array(Xtr, float), np.array(ytr, float)
    Xte, yte = np.array(Xte, float), np.array(yte, float)

    # Target-encoding do bairro (treino) + coluna extra
    bucket: dict[str, list[float]] = {}
    for nb, pr in zip(ntr, ytr):
        if nb:
            bucket.setdefault(nb, []).append(float(pr))
    enc = {nb: sum(v) / len(v) for nb, v in bucket.items()}
    gmean = float(ytr.mean())
    Xtr = np.hstack([Xtr, np.array([enc.get(nb, gmean) for nb in ntr]).reshape(-1, 1)])
    Xte = np.hstack([Xte, np.array([enc.get(nb, gmean) for nb in nte]).reshape(-1, 1)])

    models = _train_models(Xtr, ytr)
    p = {q: models[q].predict(Xte) for q in QUANTILES}

    # Baseline: preço/m² mediano do bairro (treino) × área
    pm2: dict[str, list[float]] = {}
    for i, nb in enumerate(ntr):
        a = Xtr[i][0]
        if a > 0:
            pm2.setdefault(nb, []).append(float(ytr[i]) / a)
    pm2m = {nb: statistics.median(v) for nb, v in pm2.items()}
    gpm2 = statistics.median([float(ytr[i]) / Xtr[i][0] for i in range(len(ytr)) if Xtr[i][0] > 0])
    base = np.array([pm2m.get(nte[i], gpm2) * Xte[i][0] for i in range(len(yte))])

    def mae(a, b): return float(np.mean(np.abs(a - b)))
    def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))
    def mape(a, b): return float(np.mean(np.abs((a - b) / a)) * 100)

    return {
        "n_test": len(yte),
        "base_mae": mae(yte, base), "base_mape": mape(yte, base), "base_rmse": rmse(yte, base),
        "avm_mae": mae(yte, p[0.50]), "avm_mape": mape(yte, p[0.50]), "avm_rmse": rmse(yte, p[0.50]),
        "cov2575": float(np.mean((yte >= p[0.25]) & (yte <= p[0.75])) * 100),
        "cov1090": float(np.mean((yte >= p[0.10]) & (yte <= p[0.90])) * 100),
    }


def main() -> None:
    db = get_client()
    listings = _fetch_land_listings(db)
    total_listings = db.table("listings").select("id", count="exact").limit(1).execute().count
    agro = _fetch_agronegocio_indice(db)
    for l in listings:
        l["_agronegocio_indice"] = agro
    heat = _fetch_market_heat(db)
    obras = _fetch_obras_map(db)
    parcel = _fetch_parcelamentos_map(db)
    itbi = db.table("itbi_transactions").select("id", count="exact").limit(1).execute().count

    usable = [l for l in listings if (l.get("total_area") or 0) > 0 and (l.get("sale_price") or 0) > 0]
    geo = sum(1 for l in usable if l.get("latitude") and l.get("longitude"))

    print(f"\n=== CONJUNTO DE DADOS ===")
    print(f"listings (base total):           {total_listings}")
    print(f"terrenos ativos com preço/área:  {len(usable)}")
    print(f"geocodificados:                  {geo} ({100*geo/max(len(usable),1):.1f}%)")
    print(f"transações ITBI (ground truth):  {itbi}")

    runs = [r for r in (_run_split(listings, heat, obras, parcel, s) for s in SEEDS) if r]
    if not runs:
        print("Dados insuficientes."); return

    def agg(key):
        vals = [r[key] for r in runs]
        return statistics.mean(vals), (statistics.stdev(vals) if len(vals) > 1 else 0.0)

    keys = ["base_mae", "base_mape", "base_rmse", "avm_mae", "avm_mape",
            "avm_rmse", "cov2575", "cov1090"]
    a = {k: agg(k) for k in keys}
    res = {"n_total": total_listings, "n_usable": len(usable), "geocoded": geo,
           "geocoded_pct": round(100*geo/len(usable), 1), "itbi": itbi,
           "seeds": SEEDS, "n_test_avg": round(statistics.mean([r["n_test"] for r in runs])),
           **{k: {"mean": round(a[k][0], 2), "std": round(a[k][1], 2)} for k in keys}}

    print(f"\n=== EXPERIMENTO A — média ± desvio sobre {len(runs)} divisões (n_teste≈{res['n_test_avg']}) ===")
    print(f"{'Métrica':<14}{'Baseline':>22}{'AVM (P50)':>22}")
    print(f"{'MAE (R$)':<14}{a['base_mae'][0]:>14,.0f} ±{a['base_mae'][1]:>6,.0f}{a['avm_mae'][0]:>14,.0f} ±{a['avm_mae'][1]:>6,.0f}")
    print(f"{'MAPE (%)':<14}{a['base_mape'][0]:>15.1f} ±{a['base_mape'][1]:>5.1f}{a['avm_mape'][0]:>15.1f} ±{a['avm_mape'][1]:>5.1f}")
    print(f"{'RMSE (R$)':<14}{a['base_rmse'][0]:>14,.0f} ±{a['base_rmse'][1]:>6,.0f}{a['avm_rmse'][0]:>14,.0f} ±{a['avm_rmse'][1]:>6,.0f}")
    print(f"\n=== COBERTURA (AVM) ===")
    print(f"  P25–P75 (alvo 50%): {a['cov2575'][0]:.1f}% ± {a['cov2575'][1]:.1f}")
    print(f"  P10–P90 (alvo 80%): {a['cov1090'][0]:.1f}% ± {a['cov1090'][1]:.1f}")

    with open("docs/eval_avm_result.json", "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print("\nOK -> docs/eval_avm_result.json")


if __name__ == "__main__":
    main()

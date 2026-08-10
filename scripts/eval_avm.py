# -*- coding: utf-8 -*-
"""Experimento A (TCC, Cap. 5): avaliação honesta e REPRODUTÍVEL do AVM.

Lê o coorte congelado em docs/avm_snapshot.json (gerado por
scripts/freeze_avm_snapshot.py), de modo que os números do Cap. 5 são
reproduzíveis para sempre, independentemente da evolução do banco vivo.

Protocolo (igual ao de produção, com correções contra otimismo):
  - hold-out aleatório repetido (5 divisões 80/20, seeds fixas);
  - preço médio por bairro (feature) e target-encoding ajustados SÓ no treino;
  - baseline = preço/m² mediano do bairro (treino) × área.

Métricas: MAE, MAPE, RMSE, perda pinball (P50 e média dos 5 quantis),
cobertura P25–P75 / P10–P90, teste de Wilcoxon pareado (erro AVM vs baseline),
recorte no estrato-alvo (imóveis < R$ 300 mil) e cobertura por Conformalized
Quantile Regression (CQR) no intervalo de 80%.

Uso:  PYTHONPATH=. python3 scripts/eval_avm.py
Saída: tabela para o Cap. 5 + JSON em docs/eval_avm_result.json
"""
from __future__ import annotations

import json
import os
import statistics

import numpy as np
import lightgbm as lgb
from scipy.stats import wilcoxon
from sklearn.model_selection import train_test_split

QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
SEEDS = [42, 7, 123, 2024, 99]
SNAPSHOT = "docs/avm_snapshot.json"
STRATUM_MAX = 300_000       # estrato-alvo: lotes de habitação popular
SEGMENT_MAX_AREA = 1000.0   # caso de uso: lote residencial urbano (exclui glebas)
USE_LOG = True              # alvo em log1p (preços têm cauda pesada)


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


def _pinball(y, pred, q):
    u = y - pred
    return float(np.mean(np.maximum(q * u, (q - 1) * u)))


def _prep(rows):
    """Monta X (com col1 e target-enc a definir), y, área, bairro, ppm2."""
    X = np.array([r["x"] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    area = np.array([r["area"] for r in rows], dtype=float)
    neigh = [r["neigh"] for r in rows]
    ppm2 = [r["ppm2"] for r in rows]
    return X, y, area, neigh, ppm2


def _encode(Xtr, ytr, ntr, Xte, nte):
    """col1 = preço médio/m² do bairro (treino); +coluna target-enc (treino)."""
    # neigh_price (col 1) a partir do ppm2 do treino
    # (recomputado aqui via média de y/area como proxy estável do ppm2 de treino)
    # target-encoding: média de y por bairro no treino
    bucket: dict[str, list[float]] = {}
    for nb, pr in zip(ntr, ytr):
        if nb:
            bucket.setdefault(nb, []).append(float(pr))
    enc = {nb: sum(v) / len(v) for nb, v in bucket.items()}
    gmean = float(ytr.mean())
    tr_col = np.array([enc.get(nb, gmean) for nb in ntr]).reshape(-1, 1)
    te_col = np.array([enc.get(nb, gmean) for nb in nte]).reshape(-1, 1)
    return np.hstack([Xtr, tr_col]), np.hstack([Xte, te_col])


def _neigh_price(ntr, ppm2_tr):
    bucket: dict[str, list[float]] = {}
    for nb, p in zip(ntr, ppm2_tr):
        if nb and p:
            bucket.setdefault(nb, []).append(float(p))
    return {nb: sum(v) / len(v) for nb, v in bucket.items()}


def _run_split(rows, seed):
    tr, te = train_test_split(rows, test_size=0.2, random_state=seed)
    Xtr, ytr, atr, ntr, ptr = _prep(tr)
    Xte, yte, ate, nte, pte = _prep(te)
    if len(yte) < 8 or len(ytr) < 30:
        return None

    # col1 = neigh price/m2 (treino)
    np_map = _neigh_price(ntr, ptr)
    Xtr[:, 1] = np.array([np_map.get(nb, 0.0) for nb in ntr])
    Xte[:, 1] = np.array([np_map.get(nb, 0.0) for nb in nte])

    # target-encoding (treino)
    Xtr, Xte = _encode(Xtr, ytr, ntr, Xte, nte)

    y_fit = np.log1p(ytr) if USE_LOG else ytr
    models = _train_models(Xtr, y_fit)
    inv = (lambda z: np.expm1(z)) if USE_LOG else (lambda z: z)
    p = {q: inv(models[q].predict(Xte)) for q in QUANTILES}

    # baseline: mediana de y/area por bairro (treino) * área
    pm2: dict[str, list[float]] = {}
    for i, nb in enumerate(ntr):
        if atr[i] > 0:
            pm2.setdefault(nb, []).append(float(ytr[i]) / atr[i])
    pm2m = {nb: statistics.median(v) for nb, v in pm2.items()}
    gpm2 = statistics.median([ytr[i] / atr[i] for i in range(len(ytr)) if atr[i] > 0])
    base = np.array([pm2m.get(nte[i], gpm2) * ate[i] for i in range(len(yte))])

    def mae(a, b): return float(np.mean(np.abs(a - b)))
    def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))
    def mape(a, b): return float(np.mean(np.abs((a - b) / a)) * 100)

    return {
        "n_test": len(yte),
        "base_mae": mae(yte, base), "base_mape": mape(yte, base), "base_rmse": rmse(yte, base),
        "avm_mae": mae(yte, p[0.50]), "avm_mape": mape(yte, p[0.50]), "avm_rmse": rmse(yte, p[0.50]),
        "cov2575": float(np.mean((yte >= p[0.25]) & (yte <= p[0.75])) * 100),
        "cov1090": float(np.mean((yte >= p[0.10]) & (yte <= p[0.90])) * 100),
        "pinball_p50_avm": _pinball(yte, p[0.50], 0.50),
        "pinball_p50_base": _pinball(yte, base, 0.50),
        "pinball_avg_avm": float(np.mean([_pinball(yte, p[q], q) for q in QUANTILES])),
        # arrays para pooling (Wilcoxon + estrato)
        "_y": yte, "_avm": p[0.50], "_base": base,
    }


def main() -> None:
    if not os.path.exists(SNAPSHOT):
        raise SystemExit(f"Snapshot ausente: {SNAPSHOT}. Rode scripts/freeze_avm_snapshot.py")
    snap = json.load(open(SNAPSHOT))
    meta = snap["meta"]
    rows = [r for r in snap["rows"] if r["area"] <= SEGMENT_MAX_AREA]
    print(f"segmento: lote residencial (área ≤ {SEGMENT_MAX_AREA:.0f} m²) -> "
          f"{len(rows)} de {len(snap['rows'])}   alvo={'log1p' if USE_LOG else 'linear'}")

    runs = [r for r in (_run_split(rows, s) for s in SEEDS) if r]
    if not runs:
        raise SystemExit("Dados insuficientes no snapshot.")

    # cobertura conformal: re-medida corretamente no teste usando o qhat do split
    conf_covs = []
    for s in SEEDS:
        c = _measure_cqr_on_test(rows, s)
        if c is not None:
            conf_covs.append(c)

    def agg(key):
        vals = [r[key] for r in runs if r.get(key) is not None]
        return (statistics.mean(vals), statistics.stdev(vals) if len(vals) > 1 else 0.0)

    # pooling para Wilcoxon e estrato
    y_all = np.concatenate([r["_y"] for r in runs])
    avm_all = np.concatenate([r["_avm"] for r in runs])
    base_all = np.concatenate([r["_base"] for r in runs])
    err_avm = np.abs(y_all - avm_all)
    err_base = np.abs(y_all - base_all)
    try:
        w_stat, w_p = wilcoxon(err_avm, err_base, alternative="less")
        w_stat, w_p = float(w_stat), float(w_p)
    except Exception:
        w_stat, w_p = None, None

    m = y_all < STRATUM_MAX
    def smape(a, b): return float(np.mean(np.abs((a - b) / a)) * 100)
    strat = {
        "n_points": int(m.sum()),
        "avm_mape": smape(y_all[m], avm_all[m]) if m.any() else None,
        "base_mape": smape(y_all[m], base_all[m]) if m.any() else None,
        "avm_mae": float(np.mean(np.abs(y_all[m] - avm_all[m]))) if m.any() else None,
        "base_mae": float(np.mean(np.abs(y_all[m] - base_all[m]))) if m.any() else None,
    }

    keys = ["base_mae", "base_mape", "base_rmse", "avm_mae", "avm_mape", "avm_rmse",
            "cov2575", "cov1090", "pinball_p50_avm", "pinball_p50_base", "pinball_avg_avm"]
    a = {k: agg(k) for k in keys}
    res = {
        "source": SNAPSHOT, "n_total_note": "ver Tabela 1", "n_usable": meta["n"],
        "cutoff": meta.get("cutoff_first_seen_at"), "itbi": 0, "seeds": SEEDS,
        "n_test_avg": round(statistics.mean([r["n_test"] for r in runs])),
        **{k: {"mean": round(a[k][0], 4 if "pinball" in k else 2),
               "std": round(a[k][1], 4 if "pinball" in k else 2)} for k in keys},
        "wilcoxon": {"stat": w_stat, "p_value": w_p, "alt": "erro_avm < erro_base",
                     "n_pairs": int(len(err_avm))},
        "conformal_cov1090": (round(statistics.mean(conf_covs), 2) if conf_covs else None),
        "stratum_lt_300k": {k: (round(v, 2) if isinstance(v, float) else v)
                            for k, v in strat.items()},
    }

    print(f"\n=== EXPERIMENTO A (snapshot congelado, N={meta['n']}, "
          f"n_teste≈{res['n_test_avg']}, {len(runs)} divisões) ===")
    print(f"{'Métrica':<16}{'Baseline':>22}{'AVM (P50)':>22}")
    print(f"{'MAE (R$)':<16}{a['base_mae'][0]:>13,.0f} ±{a['base_mae'][1]:>7,.0f}{a['avm_mae'][0]:>13,.0f} ±{a['avm_mae'][1]:>7,.0f}")
    print(f"{'MAPE (%)':<16}{a['base_mape'][0]:>14.1f} ±{a['base_mape'][1]:>6.1f}{a['avm_mape'][0]:>14.1f} ±{a['avm_mape'][1]:>6.1f}")
    print(f"{'RMSE (R$)':<16}{a['base_rmse'][0]:>13,.0f} ±{a['base_rmse'][1]:>7,.0f}{a['avm_rmse'][0]:>13,.0f} ±{a['avm_rmse'][1]:>7,.0f}")
    print(f"{'Pinball P50':<16}{a['pinball_p50_base'][0]:>21,.0f}{a['pinball_p50_avm'][0]:>22,.0f}")
    print(f"\nPinball média (5 quantis, AVM): {a['pinball_avg_avm'][0]:,.0f}")
    print(f"Cobertura P25–P75 (alvo 50%): {a['cov2575'][0]:.1f}% ± {a['cov2575'][1]:.1f}")
    print(f"Cobertura P10–P90 (alvo 80%): {a['cov1090'][0]:.1f}% ± {a['cov1090'][1]:.1f}")
    print(f"Cobertura P10–P90 com CQR (alvo 80%): "
          f"{res['conformal_cov1090']}%" if res['conformal_cov1090'] else "CQR: n/d")
    print(f"\nWilcoxon (erro AVM < erro baseline): p={w_p:.2e}  (n={len(err_avm)} pares)")
    print(f"\nEstrato-alvo < R$ 300 mil (n={strat['n_points']}): "
          f"MAPE AVM {strat['avm_mape']:.1f}% vs baseline {strat['base_mape']:.1f}%; "
          f"MAE AVM R$ {strat['avm_mae']:,.0f} vs baseline R$ {strat['base_mae']:,.0f}")

    with open("docs/eval_avm_result.json", "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print("\nOK -> docs/eval_avm_result.json")


def _measure_cqr_on_test(rows, seed):
    """Cobertura empírica do intervalo CQR-80% no conjunto de teste do split."""
    tr, te = train_test_split(rows, test_size=0.2, random_state=seed)
    if len(tr) < 40:
        return None
    ptr, cal = train_test_split(tr, test_size=0.25, random_state=seed + 1)
    Xtr, ytr, atr, ntr, pptr = _prep(ptr)
    Xca, yca, aca, nca, ppca = _prep(cal)
    Xte, yte, ate, nte, ppte = _prep(te)
    np_map = _neigh_price(ntr, pptr)
    for XX, nn in ((Xtr, ntr), (Xca, nca), (Xte, nte)):
        XX[:, 1] = np.array([np_map.get(nb, 0.0) for nb in nn])
    # target-enc treino
    bucket = {}
    for nb, pr in zip(ntr, ytr):
        if nb: bucket.setdefault(nb, []).append(float(pr))
    enc = {nb: sum(v) / len(v) for nb, v in bucket.items()}
    gm = float(ytr.mean())
    def addcol(X, nn): return np.hstack([X, np.array([enc.get(nb, gm) for nb in nn]).reshape(-1, 1)])
    Xtr, Xca, Xte = addcol(Xtr, ntr), addcol(Xca, nca), addcol(Xte, nte)
    y_fit = np.log1p(ytr) if USE_LOG else ytr
    inv = (lambda z: np.expm1(z)) if USE_LOG else (lambda z: z)
    def fit(al):
        return lgb.LGBMRegressor(objective="quantile", alpha=al, n_estimators=400,
            learning_rate=0.04, num_leaves=15, max_depth=6, min_data_in_leaf=25,
            feature_fraction=0.85, bagging_fraction=0.85, bagging_freq=3,
            reg_alpha=0.1, reg_lambda=0.2, random_state=42, verbosity=-1).fit(Xtr, y_fit)
    lo, hi = fit(0.10), fit(0.90)
    qlo_c, qhi_c = inv(lo.predict(Xca)), inv(hi.predict(Xca))
    scores = np.maximum(qlo_c - yca, yca - qhi_c)
    n = len(scores)
    k = min(n - 1, int(np.ceil((n + 1) * 0.80)) - 1)
    qhat = float(np.sort(scores)[k])
    qlo_t, qhi_t = inv(lo.predict(Xte)) - qhat, inv(hi.predict(Xte)) + qhat
    return float(np.mean((yte >= qlo_t) & (yte <= qhi_t)) * 100)


if __name__ == "__main__":
    main()

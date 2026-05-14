"""Price prediction model — Track E AVM.

Trains LightGBM quantile regressors (alpha=0.10/0.25/0.50/0.75/0.90) over
active land listings to produce a P25–P75 negotiation interval per property.
SHAP values explain the P50 estimate in human-readable PT-BR.

Optional deps: lightgbm, shap
Fallback: scikit-learn RandomForest (point estimate, shap_summary='rf_fallback').

Outputs:
- Upserts `avm_predictions` (per listing_id)
- Patches `opportunities.score_breakdown` with predicted_price + price_diff_pct
- Logs `agent_runs` entry

Schema: sql/023_avm_predictions.sql
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client
from src.spatial import get_economic_centroid_distances

logger = logging.getLogger(__name__)

# --- Constants ------------------------------------------------------------

MODEL_VERSION = "lgbm_q_v3_2026-05-14"
MODEL_VERSION_FALLBACK = "rf_fallback_v3_2026-05-14"
# v3: ITBI como ground truth (elimina survivorship bias) + feature agronegócio

# Coordenadas legadas — mantidas para compatibilidade
# Usar get_economic_centroid_distances() para features mais precisas
MARILIA_LAT = -22.21
MARILIA_LON = -49.95

QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]

FEATURE_NAMES = [
    "area",
    "neigh_avg_price_m2",
    "has_coords",
    "is_mcmv",
    "infra_count",
    "prox_count",
    # Centros econômicos reais de Marília (substituem distância_centro genérica)
    "dist_commercial_km",    # Av. Sampaio Vidal + Shopping
    "dist_health_km",        # Famema + Amaral Carvalho
    "dist_education_km",     # Unimar + Unesp
    "dist_industrial_km",    # Distrito industrial
    "dist_historic_km",      # Centro histórico (decadente — peso menor)
    # Score de acessibilidade MCMV (critérios reais da Caixa)
    "mcmv_accessibility_score",
    "market_heat_score",
    "days_listed",
    "obras_bairro_count",
    "parcelamentos_bairro_count",
    "agronegocio_indice",
    "neigh_target_enc",
]

# Human labels for SHAP narrative
FEATURE_LABELS_PT = {
    "area": "área",
    "neigh_avg_price_m2": "preço médio do bairro (R$/m²)",
    "has_coords": "geolocalização",
    "is_mcmv": "compatibilidade MCMV",
    "infra_count": "infraestrutura",
    "prox_count": "proximidades",
    "dist_commercial_km":       "distância ao polo comercial (km)",
    "dist_health_km":           "distância ao polo de saúde (km)",
    "dist_education_km":        "distância ao polo educacional (km)",
    "dist_industrial_km":       "distância ao polo industrial (km)",
    "dist_historic_km":         "distância ao centro histórico (km)",
    "mcmv_accessibility_score": "score de acessibilidade MCMV",
    "market_heat_score": "demanda do bairro",
    "days_listed": "tempo de anúncio",
    "obras_bairro_count": "obras públicas concluídas no bairro",
    "parcelamentos_bairro_count": "novos loteamentos aprovados no bairro",
    "agronegocio_indice": "pressão de compra do agronegócio (safra)",
    "neigh_target_enc": "preço típico do bairro",
}


# --- Entry point ----------------------------------------------------------

def run_price_model() -> dict[str, int]:
    """Train AVM and score all active land listings."""
    db = get_client()
    stats: dict[str, Any] = {
        "trained_on": 0,
        "predicted": 0,
        "undervalued": 0,
        "failed": 0,
        "model": MODEL_VERSION,
    }

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "price_model", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        listings = _fetch_listings(db)
        if len(listings) < 20:
            logger.warning(
                f"[price_model] Only {len(listings)} listings, need >= 20"
            )
            _finish_run(db, run_id, "completed", stats)
            return stats

        # Índice agronegócio (safra) — feature global para o mês atual
        agro_indice = _fetch_agronegocio_indice(db)
        for l in listings:
            l["_agronegocio_indice"] = agro_indice
        logger.info(f"[price_model] Agronegócio indice={agro_indice:.1f}")

        # ITBI como ground truth adicional (elimina survivorship bias)
        itbi_raw = _fetch_itbi_as_training(db)
        itbi_listings = _itbi_to_listing_format(itbi_raw, agro_indice)
        if itbi_listings:
            logger.info(f"[price_model] +{len(itbi_listings)} transações ITBI como ground truth")
            stats["itbi_ground_truth"] = len(itbi_listings)

        heat_map = _fetch_market_heat(db)

        # Try LightGBM path; on import error or runtime fail, fall back to RF.
        try:
            import lightgbm  # noqa: F401
            import numpy as np  # noqa: F401
            from sklearn.model_selection import train_test_split  # noqa: F401
            stats.update(_run_lgbm(db, listings, heat_map, stats, itbi_listings=itbi_listings))
        except ImportError as e:
            logger.warning(
                f"[price_model] lightgbm/sklearn missing ({e}); using RF fallback"
            )
            stats["model"] = MODEL_VERSION_FALLBACK
            stats.update(_run_rf_fallback(db, listings, heat_map, stats))
        except Exception:
            logger.exception("[price_model] LGBM path failed, using RF fallback")
            stats["model"] = MODEL_VERSION_FALLBACK
            stats.update(_run_rf_fallback(db, listings, heat_map, stats))

        logger.info(
            f"[price_model] Done ({stats['model']}): trained={stats['trained_on']}, "
            f"predicted={stats['predicted']}, undervalued={stats['undervalued']}"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[price_model] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


# --- Data fetching --------------------------------------------------------

def _fetch_listings(db: Any) -> list[dict]:
    listings: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        result = (
            db.table("listings")
            .select(
                "id, sale_price, total_area, price_per_m2, neighborhood, "
                "latitude, longitude, is_mcmv, features, first_seen_at, "
                "mcmv_accessibility_score"
            )
            .eq("is_active", True)
            .eq("property_type", "land")
            .is_("canonical_listing_id", "null")
            .not_.is_("sale_price", "null")
            .gt("sale_price", 5000)
            .not_.is_("total_area", "null")
            .gt("total_area", 15)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        listings.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return listings


def _fetch_market_heat(db: Any) -> dict[str, float]:
    """Pull neighborhoods.market_heat_score per neighborhood. Optional."""
    try:
        result = (
            db.table("neighborhoods")
            .select("name, market_heat_score")
            .not_.is_("market_heat_score", "null")
            .execute()
        )
        return {
            r["name"]: float(r["market_heat_score"])
            for r in (result.data or [])
            if r.get("name") and r.get("market_heat_score") is not None
        }
    except Exception:
        return {}


def _fetch_obras_map(db: Any, years: int = 3) -> dict[str, float]:
    """Completed public works count per neighborhood in the last N years."""
    from datetime import datetime
    cutoff_year = datetime.now().year - years
    try:
        r = (
            db.table("obras_publicas_marilia")
            .select("neighborhood")
            .eq("situacao", "Concluído")
            .gte("year", cutoff_year)
            .not_.is_("neighborhood", "null")
            .execute()
        )
        counts: dict[str, float] = {}
        for row in r.data or []:
            n = (row.get("neighborhood") or "").strip()
            if n:
                counts[n] = counts.get(n, 0.0) + 1.0
        return counts
    except Exception:
        logger.warning("[price_model] obras map unavailable")
        return {}


def _fetch_agronegocio_indice(db: Any) -> float:
    """Retorna índice de pressão de compra do agronegócio para o mês atual (0-100)."""
    try:
        from src.collectors.agronegocio import get_current_agronegocio_index
        return get_current_agronegocio_index(db)
    except Exception:
        logger.debug("[price_model] agronegocio indice indisponível, usando 50.0")
        return 50.0


def _fetch_itbi_as_training(db: Any) -> list[dict]:
    """Busca transações ITBI para usar como ground truth no treino.

    ITBI = preço real de transação (eliminina survivorship bias das listagens).
    Exige: total_area > 0, valor_declarado > 5000, neighborhood preenchido.
    """
    try:
        from datetime import date
        cutoff = str(date(date.today().year - 3, 1, 1))
        r = (
            db.table("itbi_transactions")
            .select("neighborhood, area_m2, valor_declarado, latitude, longitude, transaction_date")
            .eq("property_type", "land")
            .gte("transaction_date", cutoff)
            .gt("area_m2", 15)
            .gt("valor_declarado", 5000)
            .not_.is_("neighborhood", "null")
            .limit(2000)
            .execute()
        )
        return r.data or []
    except Exception:
        logger.debug("[price_model] ITBI training data indisponível")
        return []


def _itbi_to_listing_format(itbi_rows: list[dict], agro_indice: float) -> list[dict]:
    """Converte registros ITBI para o formato de listing esperado por _extract_rows."""
    result = []
    for t in itbi_rows:
        area = float(t.get("area_m2") or 0)
        price = float(t.get("valor_declarado") or 0)
        if area <= 0 or price <= 0:
            continue
        result.append({
            "id": f"itbi_{t.get('transaction_date', '')}_{area}",
            "sale_price": price,
            "total_area": area,
            "price_per_m2": price / area,
            "neighborhood": t.get("neighborhood", ""),
            "latitude": t.get("latitude"),
            "longitude": t.get("longitude"),
            "is_mcmv": area <= 300,
            "features": {},
            "first_seen_at": t.get("transaction_date"),
            "mcmv_accessibility_score": 50.0,
            "_agronegocio_indice": agro_indice,
            "_is_itbi": True,
        })
    return result


def _fetch_parcelamentos_map(db: Any, years: int = 3) -> dict[str, float]:
    """Approved parcelamentos count per neighborhood in the last N years."""
    from datetime import date
    cutoff = str(date(date.today().year - years, 1, 1))
    try:
        r = (
            db.table("parcelamento_solo_marilia")
            .select("neighborhood")
            .gte("issue_date", cutoff)
            .not_.is_("neighborhood", "null")
            .execute()
        )
        counts: dict[str, float] = {}
        for row in r.data or []:
            n = (row.get("neighborhood") or "").strip()
            if n:
                counts[n] = counts.get(n, 0.0) + 1.0
        return counts
    except Exception:
        logger.warning("[price_model] parcelamentos map unavailable")
        return {}


# --- Feature engineering --------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parse_features(l: dict) -> dict:
    feat = l.get("features") or {}
    if isinstance(feat, str):
        try:
            feat = json.loads(feat)
        except (json.JSONDecodeError, TypeError):
            feat = {}
    if not isinstance(feat, dict):
        feat = {}
    return feat


def _days_listed(l: dict) -> float:
    fs = l.get("first_seen_at")
    if not fs:
        return 0.0
    try:
        first = datetime.fromisoformat(str(fs).replace("Z", "+00:00"))
        return float((datetime.now(timezone.utc) - first).days)
    except (ValueError, TypeError):
        return 0.0


def _build_neigh_avg_price_m2(listings: list[dict]) -> dict[str, float]:
    bucket: dict[str, list[float]] = {}
    for l in listings:
        n = (l.get("neighborhood") or "").strip()
        pm2 = float(l.get("price_per_m2") or 0)
        if n and pm2 > 0:
            bucket.setdefault(n, []).append(pm2)
    return {n: sum(v) / len(v) for n, v in bucket.items() if v}


def _extract_rows(
    listings: list[dict],
    neigh_avg: dict[str, float],
    heat_map: dict[str, float],
    obras_map: dict[str, float] | None = None,
    parcelamentos_map: dict[str, float] | None = None,
) -> tuple[list[list[float]], list[float], list[int], list[str]]:
    """Return (X_raw_without_target_enc, y, listing_ids, neighborhoods).

    Target-encoding for neighborhood is added later (after train/test split)
    to avoid leakage.
    """
    X: list[list[float]] = []
    y: list[float] = []
    ids: list[int] = []
    neighs: list[str] = []

    obras_map = obras_map or {}
    parcelamentos_map = parcelamentos_map or {}

    for l in listings:
        area = float(l.get("total_area") or 0)
        price = float(l.get("sale_price") or 0)
        if area <= 0 or price <= 0:
            continue

        n = (l.get("neighborhood") or "").strip()
        neigh_price = neigh_avg.get(n, 0.0)
        lat = l.get("latitude")
        lon = l.get("longitude")
        has_coords = 1 if (lat is not None and lon is not None) else 0
        is_mcmv = 1 if l.get("is_mcmv") else 0

        feat = _parse_features(l)
        infra_count = len(feat.get("infraestrutura") or [])
        prox_count = len(feat.get("proximidades") or [])

        # Centros econômicos reais (substitui distância ao centro geográfico)
        centroids = {}
        if lat and lon:
            try:
                centroids = get_economic_centroid_distances(float(lat), float(lon))
            except Exception:
                pass

        dist_commercial_km = centroids.get("commercial", 3.0)
        dist_health_km = centroids.get("health", 3.0)
        dist_education_km = centroids.get("education", 3.0)
        dist_industrial_km = centroids.get("industrial", 5.0)
        dist_historic_km = centroids.get("historic", 3.0)

        # Score MCMV do banco (calculado pelo spatial enricher)
        mcmv_score = float(l.get("mcmv_accessibility_score") or 50.0)

        heat = heat_map.get(n, 0.0)
        days = _days_listed(l)
        obras_c = obras_map.get(n, 0.0)
        parcel_c = parcelamentos_map.get(n, 0.0)
        agro = float(l.get("_agronegocio_indice") or 50.0)

        # Order MUST match FEATURE_NAMES (target-enc added later as last col)
        X.append([
            area,
            neigh_price,
            float(has_coords),
            float(is_mcmv),
            float(infra_count),
            float(prox_count),
            dist_commercial_km,
            dist_health_km,
            dist_education_km,
            dist_industrial_km,
            dist_historic_km,
            mcmv_score,
            heat,
            days,
            obras_c,
            parcel_c,
            agro,
        ])
        y.append(price)
        ids.append(int(l["id"]))
        neighs.append(n)

    return X, y, ids, neighs


# --- LightGBM path --------------------------------------------------------

def _run_lgbm(
    db: Any,
    listings: list[dict],
    heat_map: dict[str, float],
    stats: dict[str, Any],
    itbi_listings: list[dict] | None = None,
) -> dict[str, Any]:
    import numpy as np
    import lightgbm as lgb
    from sklearn.model_selection import train_test_split

    neigh_avg = _build_neigh_avg_price_m2(listings)
    obras_map = _fetch_obras_map(db)
    parcelamentos_map = _fetch_parcelamentos_map(db)

    # Dataset base: listings (peso 1.0)
    X_base, y, ids, neighs = _extract_rows(listings, neigh_avg, heat_map, obras_map, parcelamentos_map)
    weights = [1.0] * len(y)

    # Adicionar ITBI como ground truth com peso 2.0 (preço real > listagem)
    if itbi_listings:
        X_itbi, y_itbi, _, neighs_itbi = _extract_rows(
            itbi_listings, neigh_avg, heat_map, obras_map, parcelamentos_map
        )
        if X_itbi:
            X_base.extend(X_itbi)
            y.extend(y_itbi)
            neighs.extend(neighs_itbi)
            weights.extend([2.0] * len(y_itbi))
            logger.info(f"[price_model] Training set: {len(y)-len(y_itbi)} listings + {len(y_itbi)} ITBI")

    n = len(X_base)
    stats["trained_on"] = n
    if n < 20:
        return stats

    X_arr = np.array(X_base, dtype=float)
    y_arr = np.array(y, dtype=float)
    w_arr = np.array(weights, dtype=float)
    idx_all = np.arange(n)

    idx_tr, idx_te = train_test_split(idx_all, test_size=0.2, random_state=42)
    w_tr = w_arr[idx_tr]

    # --- Target-encoding (fit on TRAIN only — avoid leakage) ---
    tr_neighs = [neighs[i] for i in idx_tr]
    tr_y = y_arr[idx_tr]
    enc: dict[str, float] = {}
    bucket: dict[str, list[float]] = {}
    for nbr, price in zip(tr_neighs, tr_y):
        if nbr:
            bucket.setdefault(nbr, []).append(float(price))
    for nbr, vals in bucket.items():
        enc[nbr] = sum(vals) / len(vals)
    global_mean = float(tr_y.mean()) if len(tr_y) else 0.0

    target_enc_col = np.array([enc.get(nbr, global_mean) for nbr in neighs]).reshape(-1, 1)
    X_full = np.hstack([X_arr, target_enc_col])

    X_tr = X_full[idx_tr]
    y_tr = y_arr[idx_tr]
    X_te = X_full[idx_te]
    y_te = y_arr[idx_te]

    # --- Train one model per quantile ---
    # Calibração 2026-05-11: coverage P25-P75 estava 31.7% (target 50%).
    # Modelo apertado demais — aumentar regularização e suavizar splits.
    models: dict[float, Any] = {}
    for q in QUANTILES:
        m = lgb.LGBMRegressor(
            objective="quantile",
            alpha=q,
            n_estimators=400,
            learning_rate=0.04,
            num_leaves=15,           # 31 → 15: árvore mais rasa
            max_depth=6,             # cap depth explícito
            min_data_in_leaf=25,     # 10 → 25: mais data por leaf
            feature_fraction=0.85,
            bagging_fraction=0.85,
            bagging_freq=3,
            reg_alpha=0.1,           # L1
            reg_lambda=0.2,          # L2
            random_state=42,
            verbosity=-1,
        )
        m.fit(X_tr, y_tr, sample_weight=w_tr)
        preds_te = m.predict(X_te)
        mae = float(np.mean(np.abs(preds_te - y_te))) if len(y_te) else 0.0
        logger.info(f"[price_model] q={q:.2f} test MAE=R${mae:,.0f}")
        models[q] = m

    # Coverage P25-P75
    if len(y_te):
        p25_te = models[0.25].predict(X_te)
        p75_te = models[0.75].predict(X_te)
        inside = np.logical_and(y_te >= p25_te, y_te <= p75_te)
        coverage = float(inside.mean() * 100)
        logger.info(f"[price_model] P25-P75 coverage on test: {coverage:.1f}% (target ~50%)")
        stats["coverage_p25_p75_pct"] = round(coverage, 2)

    # --- Predict on ALL listings ---
    preds: dict[float, Any] = {q: models[q].predict(X_full) for q in QUANTILES}

    # --- SHAP for P50 ---
    shap_per_row: list[Optional[list[dict]]] = [None] * n
    shap_available = False
    try:
        import shap
        explainer = shap.TreeExplainer(models[0.50])
        sv = explainer.shap_values(X_full)
        # sv shape: (n, n_features)
        for i in range(n):
            contribs = sv[i]
            pairs = []
            for fname, fval, c in zip(FEATURE_NAMES, X_full[i], contribs):
                pairs.append({
                    "feature": fname,
                    "value": round(float(fval), 4),
                    "contribution": round(float(c), 2),
                })
            pairs.sort(key=lambda d: abs(d["contribution"]), reverse=True)
            shap_per_row[i] = pairs[:5]
        shap_available = True
    except ImportError:
        logger.warning("[price_model] shap not installed; using feature_importance fallback")
    except Exception:
        logger.exception("[price_model] SHAP failed; using feature_importance fallback")

    if not shap_available:
        # Global feature importance fallback (same for every row)
        try:
            importances = models[0.50].feature_importances_
            total = float(sum(importances)) or 1.0
            global_pairs = [
                {
                    "feature": fname,
                    "value": None,
                    "contribution": round(float(imp) / total, 4),
                }
                for fname, imp in zip(FEATURE_NAMES, importances)
            ]
            global_pairs.sort(key=lambda d: abs(d["contribution"]), reverse=True)
            global_top5 = global_pairs[:5]
        except Exception:
            global_top5 = []
        for i in range(n):
            shap_per_row[i] = global_top5

    # --- Confidence per row: based on neighborhood support in training ---
    neigh_count = {nbr: len(vals) for nbr, vals in bucket.items()}
    max_count = max(neigh_count.values()) if neigh_count else 1

    # --- Build & upsert rows ---
    pred_rows: list[dict] = []
    opp_updates: list[tuple[int, float, float]] = []  # (listing_id, p50, diff_pct)

    for i, lid in enumerate(ids):
        p10v = float(preds[0.10][i])
        p25v = float(preds[0.25][i])
        p50v = float(preds[0.50][i])
        p75v = float(preds[0.75][i])
        p90v = float(preds[0.90][i])
        actual = float(y_arr[i])
        # Guard: sort if any quantile crossing
        sorted_q = sorted([p10v, p25v, p50v, p75v, p90v])
        p10v, p25v, p50v, p75v, p90v = sorted_q

        # Area for /m²
        area = X_full[i][0]
        p10m2 = round(p10v / area, 2) if area > 0 else None
        p50m2 = round(p50v / area, 2) if area > 0 else None
        p75m2 = round(p75v / area, 2) if area > 0 else None

        mispricing = round((p50v - actual) / p50v * 100, 2) if p50v > 0 else 0.0
        is_under = actual < p25v
        if is_under:
            stats["undervalued"] += 1

        nbr = neighs[i]
        support = neigh_count.get(nbr, 0)
        confidence = round(min(1.0, 0.3 + 0.7 * (support / max_count)), 3)

        top_feats = shap_per_row[i] or []
        summary = (
            _build_shap_summary(p50v, top_feats)
            if shap_available
            else _build_shap_summary(p50v, top_feats, prefix_note="importância global")
        )

        pred_rows.append({
            "listing_id": lid,
            "p10": round(p10v, 2),
            "p25": round(p25v, 2),
            "p50": round(p50v, 2),
            "p75": round(p75v, 2),
            "p90": round(p90v, 2),
            "p10_per_m2": p10m2,
            "p50_per_m2": p50m2,
            "p75_per_m2": p75m2,
            "actual_price": round(actual, 2),
            "mispricing_pct": mispricing,
            "is_undervalued": is_under,
            "shap_top_features": top_feats,
            "shap_summary": summary,
            "model_version": MODEL_VERSION,
            "features_used": {"names": FEATURE_NAMES},
            "confidence": confidence,
        })
        opp_updates.append((lid, p50v, _diff_pct(actual, p50v)))
        stats["predicted"] += 1

    _upsert_predictions(db, pred_rows, stats)
    _patch_opportunities(db, opp_updates, stats)
    return stats


# --- RF fallback path -----------------------------------------------------

def _run_rf_fallback(
    db: Any,
    listings: list[dict],
    heat_map: dict[str, float],
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Single-point RF prediction. Populates only p50; quantiles approximated."""
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
    except ImportError:
        logger.warning("[price_model] sklearn missing — skipping")
        return stats

    neigh_avg = _build_neigh_avg_price_m2(listings)
    obras_map = _fetch_obras_map(db)
    parcelamentos_map = _fetch_parcelamentos_map(db)
    X_base, y, ids, neighs = _extract_rows(listings, neigh_avg, heat_map, obras_map, parcelamentos_map)
    n = len(X_base)
    stats["trained_on"] = n
    if n < 20:
        return stats

    X = np.array(X_base, dtype=float)
    y_arr = np.array(y, dtype=float)

    model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
    model.fit(X, y_arr)
    preds = model.predict(X)

    pred_rows: list[dict] = []
    opp_updates: list[tuple[int, float, float]] = []
    for i, lid in enumerate(ids):
        p50v = float(preds[i])
        actual = float(y_arr[i])
        mispricing = round((p50v - actual) / p50v * 100, 2) if p50v > 0 else 0.0
        # No real quantiles: best-effort wrap (±10%/±20%)
        p25v = p50v * 0.90
        p75v = p50v * 1.10
        p10v = p50v * 0.80
        p90v = p50v * 1.20
        is_under = actual < p25v
        if is_under:
            stats["undervalued"] += 1
        area = X[i][0]
        pred_rows.append({
            "listing_id": lid,
            "p10": round(p10v, 2),
            "p25": round(p25v, 2),
            "p50": round(p50v, 2),
            "p75": round(p75v, 2),
            "p90": round(p90v, 2),
            "p10_per_m2": round(p10v / area, 2) if area > 0 else None,
            "p50_per_m2": round(p50v / area, 2) if area > 0 else None,
            "p75_per_m2": round(p75v / area, 2) if area > 0 else None,
            "actual_price": round(actual, 2),
            "mispricing_pct": mispricing,
            "is_undervalued": is_under,
            "shap_top_features": [],
            "shap_summary": "rf_fallback",
            "model_version": MODEL_VERSION_FALLBACK,
            "features_used": {"names": FEATURE_NAMES[:-1]},
            "confidence": 0.5,
        })
        opp_updates.append((lid, p50v, _diff_pct(actual, p50v)))
        stats["predicted"] += 1

    _upsert_predictions(db, pred_rows, stats)
    _patch_opportunities(db, opp_updates, stats)
    return stats


# --- SHAP narrative -------------------------------------------------------

def _build_shap_summary(
    p50: float,
    top_feats: list[dict],
    prefix_note: Optional[str] = None,
) -> str:
    if not top_feats:
        return f"Preço justo R$ {p50:,.0f}."
    drivers = []
    for f in top_feats[:3]:
        name = f.get("feature", "")
        label = FEATURE_LABELS_PT.get(name, name)
        contrib = float(f.get("contribution", 0))
        if contrib == 0:
            continue
        sign = "+" if contrib > 0 else "-"
        # Render contribution as R$ delta (SHAP units = price)
        drivers.append(f"{sign}R$ {abs(contrib):,.0f} {label}")
    if not drivers:
        return f"Preço justo R$ {p50:,.0f}."
    note = f" ({prefix_note})" if prefix_note else ""
    return f"Preço justo R$ {p50:,.0f}{note}. Drivers: " + "; ".join(drivers) + "."


# --- DB writes ------------------------------------------------------------

def _upsert_predictions(db: Any, rows: list[dict], stats: dict[str, Any]) -> None:
    if not rows:
        return
    for i in range(0, len(rows), 200):
        batch = rows[i:i + 200]
        try:
            db.table("avm_predictions").upsert(batch, on_conflict="listing_id").execute()
        except Exception as e:
            logger.warning(f"[price_model] upsert batch failed ({e}); fallback per-row")
            for row in batch:
                try:
                    existing = (
                        db.table("avm_predictions")
                        .select("id")
                        .eq("listing_id", row["listing_id"])
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        db.table("avm_predictions").update(row).eq(
                            "listing_id", row["listing_id"]
                        ).execute()
                    else:
                        db.table("avm_predictions").insert(row).execute()
                except Exception:
                    stats["failed"] += 1


def _diff_pct(actual: float, predicted: float) -> float:
    if predicted <= 0:
        return 0.0
    return round((predicted - actual) / predicted * 100, 2)


def _patch_opportunities(
    db: Any,
    updates: list[tuple[int, float, float]],
    stats: dict[str, Any],
) -> None:
    """Backwards-compat: keep populating opportunities.score_breakdown."""
    for lid, p50, diff_pct in updates:
        try:
            result = (
                db.table("opportunities")
                .select("id, score_breakdown")
                .eq("listing_id", lid)
                .limit(1)
                .execute()
            )
            if not result.data:
                continue
            breakdown = result.data[0].get("score_breakdown") or {}
            breakdown["predicted_price"] = round(p50, 0)
            breakdown["price_diff_pct"] = round(diff_pct, 1)
            db.table("opportunities").update(
                {"score_breakdown": breakdown}
            ).eq("id", result.data[0]["id"]).execute()
        except Exception:
            stats["failed"] += 1


def _finish_run(
    db: Any,
    run_id: Optional[int],
    status: str,
    stats: dict[str, Any],
    error: Optional[str] = None,
) -> None:
    if not run_id:
        return
    update: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats.get("trained_on", 0),
        "items_created": stats.get("predicted", 0),
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()

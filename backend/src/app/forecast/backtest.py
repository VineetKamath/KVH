"""Rolling-origin backtest (ARCHITECTURE §7.2) through the PRODUCTION forecast code.

Protocol: training origins weekly from `train_start` to `train_end` (targets restricted to stay dates before
`test_start`); test origins as given; horizons 1..`test_horizon`; every test target fully observed.
Reports point accuracy (city x day MAE / Poisson deviance, national x day and x week WAPE) and interval
quality for both interval methods. `docs/METRICS.md` is generated from this output, never hand-typed.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from app.forecast import defaults as C
from app.forecast.conformal import (aci_calibrate, apply_band, coverage, interval_score, split_conformal,
                                    split_conformal_band)
from app.forecast.panel import Panel, day_number
from app.forecast.pickup import feature_matrix, origin_features, realised
from app.forecast.seasonal import seasonal_indices
from app.forecast.selection import poisson_deviance_terms


def _wape(y: np.ndarray, m: np.ndarray) -> float:
    return float(np.abs(y - m).sum() / y.sum()) if y.sum() > 0 else float("nan")


def run(p: Panel, train_start: date, train_end: date, test_origins: list[date], test_horizon: int,
        last_observed: date, use_lightgbm: bool = True) -> dict:
    t_start, t_end = day_number(train_start), day_number(train_end)
    test_first = min(day_number(d) for d in test_origins)
    last = day_number(last_observed)
    train_origins = list(range(t_start, t_end + 1, C.WINDOW_DAYS))
    seasons = {t: seasonal_indices(p, t) for t in train_origins + [day_number(d) for d in test_origins]}

    def stack(origins: list[int], horizon: int, window: int, max_stay: int):
        out = {"X": [], "y": [], "y7": [], "gross": [], "p50_7": [], "naive": [], "level": [], "h": [], "stay": [], "oid": []}
        for i, t in enumerate(origins):
            f = origin_features(p, t, horizon, window, seasons[t])
            y, y7 = realised(p, t, horizon)
            ok = np.tile(f.stay_day + C.WINDOW_DAYS // 2 <= max_stay, f.p50_7.shape[0])
            ok_daily = np.tile(f.stay_day <= max_stay, f.p50_7.shape[0])
            out["X"].append(feature_matrix(f)[ok])
            out["y7"].append(y7.ravel()[ok])
            out["p50_7"].append(f.p50_7.ravel()[ok])
            out["level"].append(np.repeat(f.level, horizon)[ok])
            out["y"].append((y.ravel(), ok_daily))
            out["gross"].append(f.gross.ravel())
            out["naive"].append(np.repeat(f.naive7[:, :1] / C.WINDOW_DAYS, horizon, axis=1).ravel())
            out["h"].append(np.tile(f.h, f.p50_7.shape[0]))
            out["stay"].append(np.tile(f.stay_day, f.p50_7.shape[0]))
            out["oid"].append(np.full(f.p50_7.size, i))
        return out

    # window chosen by nested validation on training origins only
    scores = {}
    for w in C.RATE_WINDOWS:
        s = stack(train_origins, C.HORIZON_DAYS, w, test_first - 1)
        lv = np.concatenate(s["level"])
        scores[w] = float(poisson_deviance_terms(np.concatenate(s["y7"])[lv == 0], np.concatenate(s["p50_7"])[lv == 0]).mean())
    window = min(scores, key=scores.get)
    tr = stack(train_origins, C.HORIZON_DAYS, window, test_first - 1)
    te_origins = [day_number(d) for d in test_origins]
    te = stack(te_origins, test_horizon, window, last)

    n_series, n_city = p.n_series, p.n_city
    city_mask = np.repeat(np.arange(n_series) < n_city, test_horizon)      # rows are series-major (S, H).ravel()
    nat_mask = np.repeat(np.arange(n_series) == n_series - 1, test_horizon)
    rows = []
    for i in range(len(te_origins)):
        y, ok = te["y"][i]
        rows.append((y, ok, te["gross"][i], te["naive"][i], te["h"][i]))

    def point_metrics(pred_index: int) -> dict:
        ys, ms, yn, mn, wk_y, wk_m = [], [], [], [], [], []
        for y, ok, gross, naive, h in rows:
            pred = gross if pred_index == 0 else naive
            c = city_mask & ok
            ys.append(y[c]); ms.append(pred[c])
            n = nat_mask & ok
            yn.append(y[n]); mn.append(pred[n])
            wk = (h[n] - 1) // C.WINDOW_DAYS
            for k in np.unique(wk):
                sel = wk == k
                if sel.sum() == C.WINDOW_DAYS:
                    wk_y.append(y[n][sel].sum()); wk_m.append(pred[n][sel].sum())
        Y, M = np.concatenate(ys), np.concatenate(ms)
        return {"city_day_mae": float(np.abs(Y - M).mean()), "city_day_poisson_deviance": float(poisson_deviance_terms(Y, M).mean()),
                "national_day_wape": _wape(np.concatenate(yn), np.concatenate(mn)),
                "national_week_wape": _wape(np.array(wk_y), np.array(wk_m)), "cells": int(Y.size)}

    result = {"window_days": window, "window_scores": scores, "pickup": point_metrics(0), "naive": point_metrics(1)}
    for k in ("pickup", "naive"):
        result[k]["national_week_accuracy"] = 1 - result[k]["national_week_wape"]
        result[k]["national_day_accuracy"] = 1 - result[k]["national_day_wape"]
    result["improvement_vs_naive"] = {
        "city_day_mae": 1 - result["pickup"]["city_day_mae"] / result["naive"]["city_day_mae"],
        "city_day_poisson_deviance": 1 - result["pickup"]["city_day_poisson_deviance"] / result["naive"]["city_day_poisson_deviance"],
    }

    # interval quality on the 7-day signal (all levels), both methods
    Xtr, y7tr, p50tr = np.vstack(tr["X"]), np.concatenate(tr["y7"]), np.concatenate(tr["p50_7"])
    Xte, y7te, p50te = np.vstack(te["X"]), np.concatenate(te["y7"]), np.concatenate(te["p50_7"])
    r_lo, r_hi = split_conformal(y7tr, p50tr)
    lo, hi = split_conformal_band(p50te, r_lo, r_hi)
    result["interval"] = {"pickup_conformal": {"coverage": coverage(y7te, lo, hi), "interval_score": interval_score(y7te, lo, hi)}}
    if use_lightgbm:
        from app.forecast.lgbm_quantile import fit_quantiles, predict_quantiles

        models = fit_quantiles(Xtr, y7tr)
        qp = predict_quantiles(models, Xte)
        a, b = C.QUANTILES
        lo2, hi2 = apply_band(qp[a], qp[b], p50te, 0.0)
        result["interval"]["lgbm_quantile"] = {"coverage": coverage(y7te, lo2, hi2), "interval_score": interval_score(y7te, lo2, hi2)}
        aci = aci_calibrate([(y7te, qp[a], qp[b], p50te)])
        result["interval"]["aci_trace"] = aci["trace"]
    return result

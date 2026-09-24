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
from app.forecast.panel import Panel, day_number, forward_counts
from app.forecast.pickup import feature_matrix, origin_features, realised
from app.forecast.seasonal import seasonal_indices
from app.forecast.selection import poisson_deviance_terms


def _wape(y: np.ndarray, m: np.ndarray) -> float:
    return float(np.abs(y - m).sum() / y.sum()) if y.sum() > 0 else float("nan")





def hindsight_oracle(p: Panel, as_of: int, horizon: int, last: int) -> np.ndarray:
    """A benchmark that cheats: for each series and stay day it predicts the realised average rate of the
    surrounding 29 days, i.e. it knows the true underlying level in hindsight. It has no on-the-books
    knowledge, so it measures how much of the error is arrival randomness that no level forecast can remove.
    A model near this benchmark has nothing left to learn from the level; one above it is using bookings
    already on the books. Never used for pricing."""
    k = C.ORACLE_HALF_WIDTH
    y = forward_counts(p, as_of - k - 1, horizon + 2 * k + 1, "booking", known_only=False)
    stay = np.arange(as_of - k, as_of + horizon + k + 1)
    obs = (stay <= last).astype(float)
    out = np.zeros((y.shape[0], horizon))
    for j in range(horizon):
        w = slice(j + 1, j + 2 * k + 2)
        out[:, j] = (y[:, w] * obs[w]).sum(axis=1) / max(obs[w].sum(), 1.0)
    return out


def _weekly(y: np.ndarray, m: np.ndarray, ok: np.ndarray, series: np.ndarray, h: np.ndarray) -> tuple[list, list]:
    """Sum complete, fully-observed 7-day blocks per series (rows are series-major (S, H).ravel())."""
    wy, wm = [], []
    wk = (h - 1) // C.WINDOW_DAYS
    for s in np.unique(series):
        for k in np.unique(wk):
            sel = (series == s) & (wk == k)
            if sel.sum() == C.WINDOW_DAYS and ok[sel].all():
                wy.append(y[sel].sum()); wm.append(m[sel].sum())
    return wy, wm


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
    for i, t in enumerate(te_origins):
        y, ok = te["y"][i]
        rows.append((y, ok, te["gross"][i], te["naive"][i], te["h"][i], hindsight_oracle(p, t, test_horizon, last).ravel()))

    series_of = np.repeat(np.arange(n_series), test_horizon)
    region_mask = (series_of >= n_city) & (series_of < n_series - 1)
    grains = {"city": city_mask, "region": region_mask, "national": nat_mask}

    def point_metrics(which: str) -> dict:
        ys, ms = [], []
        day = {g: ([], []) for g in grains}
        week = {g: ([], []) for g in grains}
        for y, ok, gross, naive, h, oracle in rows:
            pred = {"pickup": gross, "naive": naive, "hindsight_oracle": oracle, "always_zero": np.zeros_like(gross)}[which]
            c = city_mask & ok
            ys.append(y[c]); ms.append(pred[c])
            for g, mask in grains.items():
                sel = mask & ok
                day[g][0].append(y[sel]); day[g][1].append(pred[sel])
                wy, wm = _weekly(y[mask], pred[mask], ok[mask], series_of[mask], h[mask])
                week[g][0].extend(wy); week[g][1].extend(wm)
        Y, M = np.concatenate(ys), np.concatenate(ms)
        out = {"city_day_mae": float(np.abs(Y - M).mean()), "city_day_poisson_deviance": float(poisson_deviance_terms(Y, M).mean()),
               "cells": int(Y.size)}
        for g in grains:
            dy, dm = np.concatenate(day[g][0]), np.concatenate(day[g][1])
            wy, wm = np.array(week[g][0]), np.array(week[g][1])
            out[f"{g}_day_wape"] = _wape(dy, dm)
            out[f"{g}_week_wape"] = _wape(wy, wm)
            out[f"{g}_day_accuracy"] = 1 - out[f"{g}_day_wape"]
            out[f"{g}_week_accuracy"] = 1 - out[f"{g}_week_wape"]
            out[f"{g}_week_mean_bookings"] = float(wy.mean()) if wy.size else float("nan")
            # sparse-count measures (meaningful where 1 − WAPE is not): hit rate within ±1 booking, Poisson deviance
            out[f"{g}_week_within_1"] = float(np.mean(np.abs(wy - wm) <= 1)) if wy.size else float("nan")
            out[f"{g}_week_deviance"] = float(poisson_deviance_terms(wy, np.maximum(wm, C.TINY)).mean()) if wy.size else float("nan")
        return out

    result = {"window_days": window, "window_scores": scores, "pickup": point_metrics("pickup"), "naive": point_metrics("naive"),
              "hindsight_oracle": point_metrics("hindsight_oracle"), "always_zero": point_metrics("always_zero")}
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

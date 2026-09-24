"""Forecaster interface: `fit(panel, as_of)` → state, `predict(panel, state, as_of, horizon)` → result.

Champion = pickup P50 + LightGBM quantile P10/P90, calibrated with CQR + adaptive conformal inference,
chosen and re-checked on the deployment's own recent history at every fit (ARCHITECTURE §7.4, §7.7).
Everything data-dependent is estimated here; constants come only from `defaults.py`. Pure (no I/O).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.forecast import defaults as C
from app.forecast import monitor
from app.forecast.conformal import (aci_calibrate, apply_band, coverage, interval_score, split_conformal,
                                    split_conformal_band)
from app.forecast.hierarchy import kappa_from_signal_variance, relative_signal_variance
from app.forecast.panel import Panel, recent_occurred_counts, trailing_counts, type_code
from app.forecast.pickup import OriginFeatures, feature_matrix, origin_features, realised
from app.forecast.seasonal import seasonal_indices
from app.forecast.selection import decide, poisson_deviance_terms

MODEL_FAMILY = "pickup+lgbm_quantile+aci"


@dataclass
class ForecastState:
    as_of: int
    model_version: str
    window: int
    kappa: float
    tau2_rel: float
    skill_by_level: dict[int, float]
    kappa_by_level: dict[int, float]
    quantile_models: dict[float, str] | None
    point_model: str | None
    Q: float
    alpha: float
    interval_method: str
    conformal: tuple[float, float]
    selection: dict
    interval_selection: dict
    window_scores: dict
    coverage_trace: list[dict]
    monitor: dict
    params: dict = field(default_factory=dict)


@dataclass
class ForecastResult:
    features: OriginFeatures
    labels: list[tuple[str, str]]
    p10: np.ndarray        # (S, H) net 7-day
    p50: np.ndarray
    p90: np.ndarray
    gross_p50: np.ndarray  # (S, H) gross 7-day (credibility evidence)
    normal: np.ndarray     # (S, H) expected 7-day gross at this season with no unusual demand
    demand_ratio: np.ndarray
    credibility: np.ndarray
    rel_width: np.ndarray
    pace_ratio: np.ndarray
    cxl_ratio: np.ndarray  # (S,)
    method: str


def _origins(as_of: int) -> list[int]:
    return [as_of - C.WINDOW_DAYS * k for k in range(C.TRAIN_WEEKS, 0, -1)]


def _complete_mask(f: OriginFeatures, as_of: int) -> np.ndarray:
    """Rows whose centred 7-day realised target is fully observed before as_of."""
    ok_h = f.stay_day + C.WINDOW_DAYS // 2 < as_of
    return np.tile(ok_h, f.p50_7.shape[0])


def _stack(p: Panel, as_of: int, origins: list[int], window: int, seasons: dict[int, dict]) -> dict:
    X, y7, p50, naive, level, oid, sid, normal = [], [], [], [], [], [], [], []
    for i, t in enumerate(origins):
        f = origin_features(p, t, C.HORIZON_DAYS, window, seasons[t])
        _, r7 = realised(p, t, C.HORIZON_DAYS)
        m = _complete_mask(f, as_of)
        X.append(feature_matrix(f)[m])
        y7.append(r7.ravel()[m])
        p50.append(f.p50_7.ravel()[m])
        naive.append(f.naive7.ravel()[m])
        level.append(np.repeat(f.level, f.p50_7.shape[1])[m])
        sid.append(np.repeat(np.arange(f.p50_7.shape[0]), f.p50_7.shape[1])[m])
        normal.append((f.rate[:, None] * C.WINDOW_DAYS * f.season7[None, :]).ravel()[m])
        oid.append(np.full(int(m.sum()), i))
    cat = np.concatenate
    return {"X": np.vstack(X), "y7": cat(y7), "p50": cat(p50), "naive": cat(naive), "level": cat(level),
            "origin": cat(oid), "series": cat(sid), "normal": cat(normal)}


def within_series_kappa(stack: dict) -> dict[int, float]:
    """Bühlmann κ per level from the OVER-TIME variance of realised demand relative to each series' own
    expectation, beyond Poisson noise (persistent between-series differences are excluded: each series is
    centred on its own mean). κ = 1/τ²; τ² = 0 ⇒ κ = ∞ ⇒ that level's dynamic signal is noise and gets no weight."""
    out = {}
    for lvl in (0, 1, 2):
        m = (stack["level"] == lvl) & (stack["normal"] > 0)
        e, r, s = stack["normal"][m], stack["y7"][m] / stack["normal"][m], stack["series"][m]
        tot = noise = wsum = 0.0
        for k in np.unique(s):
            mk = s == k
            w = e[mk]
            mu = float(np.average(r[mk], weights=w))
            tot += float(np.sum(w * (r[mk] - mu) ** 2))
            noise += float(np.sum(w / e[mk]))
            wsum += float(w.sum())
        tau2 = max(0.0, tot / wsum - noise / wsum) if wsum > 0 else 0.0
        out[lvl] = kappa_from_signal_variance(tau2)
    return out


def _kappa(p: Panel, as_of: int) -> tuple[float, float]:
    weeks = [trailing_counts(p, as_of - C.WINDOW_DAYS * k, C.WINDOW_DAYS)[-1] for k in range(C.KAPPA_LOOKBACK_WEEKS)]
    tau2 = relative_signal_variance(np.array(weeks[::-1], dtype=float))
    return kappa_from_signal_variance(tau2), tau2


def fit(p: Panel, as_of: int, use_lightgbm: bool = True) -> ForecastState:
    origins = _origins(as_of)
    seasons = {t: seasonal_indices(p, t) for t in origins + [as_of]}
    calib = origins[-C.CALIBRATION_ORIGINS:]
    train = origins[:-C.CALIBRATION_ORIGINS]

    # 1. rate window by nested validation (city rows, pickup deviance on the training origins only)
    window_scores = {}
    for w in C.RATE_WINDOWS:
        s = _stack(p, as_of, train, w, seasons)
        city = s["level"] == 0
        window_scores[w] = float(poisson_deviance_terms(s["y7"][city], s["p50"][city]).mean())
    window = min(window_scores, key=window_scores.get)

    tr = _stack(p, as_of, train, window, seasons)
    ca = _stack(p, as_of, calib, window, seasons)
    city_ca = ca["level"] == 0

    q_models = point_model = None
    per_origin: dict[str, list] = {"naive": [], "pickup": []}
    if use_lightgbm:
        try:
            from app.forecast.lgbm_point import fit_point, predict_point
            from app.forecast.lgbm_quantile import fit_quantiles, predict_quantiles

            q_models = fit_quantiles(tr["X"], tr["y7"])
            point_model = fit_point(tr["X"], tr["y7"])
        except ImportError:
            q_models = point_model = None
    if point_model is not None:
        per_origin["lgbm_poisson"] = []
        point_pred = predict_point(point_model, ca["X"])
    for i in range(len(calib)):
        m = (ca["origin"] == i) & city_ca
        per_origin["naive"].append((ca["y7"][m], ca["naive"][m]))
        per_origin["pickup"].append((ca["y7"][m], ca["p50"][m]))
        if point_model is not None:
            per_origin["lgbm_poisson"].append((ca["y7"][m], point_pred[m]))
    selection = decide(per_origin, incumbent="pickup")

    # 2. interval: LightGBM quantile + CQR/ACI vs split-conformal around pickup (the fallback)
    r_lo, r_hi = split_conformal(tr["y7"], tr["p50"])
    conf_lo, conf_hi = split_conformal_band(ca["p50"], r_lo, r_hi)
    interval = {"pickup_conformal": {"coverage": coverage(ca["y7"], conf_lo, conf_hi),
                                     "interval_score": interval_score(ca["y7"], conf_lo, conf_hi)}}
    Q, alpha, trace, method = 0.0, 1 - C.TARGET_COVERAGE, [], "pickup_conformal"
    if q_models is not None:
        qp = predict_quantiles(q_models, ca["X"])
        batches = [(ca["y7"][ca["origin"] == i], qp[C.QUANTILES[0]][ca["origin"] == i],
                    qp[C.QUANTILES[1]][ca["origin"] == i], ca["p50"][ca["origin"] == i]) for i in range(len(calib))]
        aci = aci_calibrate(batches)
        Q, alpha, trace = aci["Q"], aci["alpha"], aci["trace"]
        lo, hi = apply_band(qp[C.QUANTILES[0]], qp[C.QUANTILES[1]], ca["p50"], Q)
        interval["pickup_lgbmq"] = {"coverage": coverage(ca["y7"], lo, hi), "interval_score": interval_score(ca["y7"], lo, hi)}
        lg = interval["pickup_lgbmq"]
        if C.COVERAGE_BAND[0] <= lg["coverage"] <= C.COVERAGE_BAND[1] and \
                lg["interval_score"] <= interval["pickup_conformal"]["interval_score"]:
            method = "pickup_lgbmq"
    if selection["decision"] == "fallback_naive":
        method = "trailing_naive"
    interval_selection = {"method": method, "scores": interval}

    # 3. credibility per hierarchy level = out-of-sample skill vs naive on the calibration origins
    #    z_L = clip(1 - SSE(champion) / SSE(naive), 0, 1); used to decide how far the demand factor may move.
    champ_pred = point_pred if selection["champion"] == "lgbm_poisson" and point_model is not None else ca["p50"]
    if selection["champion"] == "naive":
        champ_pred = ca["naive"]
    skill_by_level = {}
    for lvl in (0, 1, 2):
        m = ca["level"] == lvl
        sse_model = float(np.sum((ca["y7"][m] - champ_pred[m]) ** 2))
        sse_naive = float(np.sum((ca["y7"][m] - ca["naive"][m]) ** 2))
        skill_by_level[lvl] = float(np.clip(1 - sse_model / sse_naive, 0, 1)) if sse_naive > 0 else 0.0

    # coverage trace of the interval method actually in use (for the monitor)
    if method == "pickup_lgbmq":
        used_trace = trace
    else:
        used_trace = [{"coverage": coverage(ca["y7"][ca["origin"] == i], conf_lo[ca["origin"] == i],
                                            conf_hi[ca["origin"] == i])} for i in range(len(calib))]

    kappa, tau2 = _kappa(p, as_of)
    kappa_by_level = within_series_kappa(tr)
    current = origin_features(p, as_of, C.HORIZON_DAYS, window, seasons[as_of])
    # drift check: the lead-time mix of bookings made in the recent window vs the preceding lookback
    bk = p.typ == type_code("booking")
    recent = p.lead[bk & (p.occ >= as_of - C.CANCEL_RECENT_DAYS) & (p.occ < as_of)].astype(float)
    prior = p.lead[bk & (p.occ >= as_of - C.CANCEL_RECENT_DAYS - C.PICKUP_LOOKBACK_DAYS)
                   & (p.occ < as_of - C.CANCEL_RECENT_DAYS)].astype(float)
    feature_psi = {"booking_lead_mix": monitor.psi(prior, recent)}
    mon = monitor.evaluate(selection, used_trace, feature_psi, {})
    version = f"{MODEL_FAMILY}@{as_of}:w{window}"
    return ForecastState(as_of=as_of, model_version=version, window=window, kappa=kappa, tau2_rel=tau2,
                         skill_by_level=skill_by_level, kappa_by_level=kappa_by_level,
                         quantile_models=q_models if method == "pickup_lgbmq" else None, point_model=point_model,
                         Q=Q, alpha=alpha, interval_method=method, conformal=(r_lo, r_hi), selection=selection,
                         interval_selection=interval_selection, window_scores=window_scores, coverage_trace=trace,
                         monitor=mon, params={**current.params, "kappa": kappa, "tau2_rel": tau2,
                                 "skill_by_level": skill_by_level, "kappa_by_level": kappa_by_level})


def predict(p: Panel, state: ForecastState, as_of: int, horizon: int) -> ForecastResult:
    f = origin_features(p, as_of, horizon, state.window)
    S, H = f.p50_7.shape
    X = feature_matrix(f)
    champion = state.selection.get("champion", "pickup")
    if champion == "naive" or state.interval_method == "trailing_naive":
        p50g = f.naive7
    elif champion == "lgbm_poisson" and state.point_model is not None:
        from app.forecast.lgbm_point import predict_point

        p50g = np.maximum(predict_point(state.point_model, X).reshape(S, H), 0)
    else:
        p50g = f.p50_7
    if state.quantile_models is not None:
        from app.forecast.lgbm_quantile import predict_quantiles

        qp = predict_quantiles(state.quantile_models, X)
        lo, hi = apply_band(qp[C.QUANTILES[0]].reshape(S, H), qp[C.QUANTILES[1]].reshape(S, H), p50g, state.Q)
    else:
        lo, hi = split_conformal_band(p50g, *state.conformal)
    ret = f.retention[:, None]
    normal = f.rate[:, None] * C.WINDOW_DAYS * f.season7[None, :]
    raw_ratio = np.divide(p50g, normal, out=np.ones_like(p50g), where=normal > 0)
    rel_width = (hi - lo) / np.maximum(p50g, C.MIN_P50_FOR_WIDTH)
    expected_otb = f.rate[:, None] * C.WINDOW_DAYS * f.season7[None, :] * (1 - f.pick)
    raw_pace = (f.otb7["booking"] + 1) / (expected_otb + 1)

    # Hierarchical Bühlmann credibility: national → 1, region → national posterior, city → its region's posterior.
    # z = E / (E + κ_level): thin series move little, dense series move more; κ is estimated in fit().
    def z_of(level: int, e: np.ndarray) -> np.ndarray:
        k = state.kappa_by_level.get(level, float("inf"))
        return np.zeros_like(e) if not np.isfinite(k) else e / (e + k)

    n_city, n_reg = p.n_city, len(p.regions)
    z = np.zeros_like(p50g)
    ratio = np.ones_like(p50g)
    pace = np.ones_like(p50g)
    nat = S - 1
    z[nat] = z_of(2, normal[nat])
    ratio[nat] = 1 + z[nat] * (raw_ratio[nat] - 1)
    pace[nat] = 1 + z[nat] * (raw_pace[nat] - 1)
    for r_i in range(n_reg):
        s_i = n_city + r_i
        z[s_i] = z_of(1, normal[s_i])
        ratio[s_i] = ratio[nat] + z[s_i] * (raw_ratio[s_i] - ratio[nat])
        pace[s_i] = pace[nat] + z[s_i] * (raw_pace[s_i] - pace[nat])
    for c_i in range(n_city):
        parent = n_city + int(p.city_region[c_i])
        z[c_i] = z_of(0, normal[c_i])
        ratio[c_i] = ratio[parent] + z[c_i] * (raw_ratio[c_i] - ratio[parent])
        pace[c_i] = pace[parent] + z[c_i] * (raw_pace[c_i] - pace[parent])
    b28 = recent_occurred_counts(p, as_of, C.CANCEL_RECENT_DAYS, "booking")
    c28 = recent_occurred_counts(p, as_of, C.CANCEL_RECENT_DAYS, "cancellation")
    long_share = 1 - f.retention
    recent_share = (c28 + C.CANCEL_PRIOR_BOOKINGS * long_share) / (b28 + C.CANCEL_PRIOR_BOOKINGS)
    cxl_ratio = np.divide(recent_share, long_share, out=np.ones_like(recent_share), where=long_share > 0)
    return ForecastResult(features=f, labels=p.series_labels(), p10=lo * ret, p50=p50g * ret, p90=hi * ret,
                          gross_p50=p50g, normal=normal, demand_ratio=ratio, credibility=z, rel_width=rel_width,
                          pace_ratio=pace, cxl_ratio=cxl_ratio,
                          method=f"{champion}+{state.interval_method}")

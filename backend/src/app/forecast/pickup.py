"""Additive pickup forecaster (the P50 champion) and the per-origin feature set.

    gross(s, d) = OTB_bookings(s, d) + rate_s · season(d) · P_s(lead < h)
    P50(s, d)   = centred 7-day sum of gross

rate_s is an empirical-Bayes-shrunk trailing booking rate; P_s(lead < h) is the series' pickup curve
shrunk to the national curve; season(d) is the learned, shrunk month × day-of-week index. Pure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from app.forecast import defaults as C
from app.forecast.hierarchy import city_rates
from app.forecast.panel import EPOCH, Panel, centred_window_sum, forward_counts, trailing_counts, type_code
from app.forecast.seasonal import index_for_days, seasonal_indices


@dataclass
class OriginFeatures:
    as_of: int
    horizon: int
    level: np.ndarray        # (S,) 0 city, 1 region, 2 national
    h: np.ndarray            # (H,) 1..H
    stay_day: np.ndarray     # (H,)
    otb: dict[str, np.ndarray]     # per type (S, H) on-the-books counts
    otb7: dict[str, np.ndarray]    # per type (S, H) centred 7-day sums
    rate: np.ndarray         # (S,) shrunk bookings per stay day
    pick: np.ndarray         # (S, H) share of bookings made closer in than h days
    season: np.ndarray       # (H,) learned index (1.0 = no effect)
    season7: np.ndarray      # (H,) mean index over the centred window
    gross: np.ndarray        # (S, H) daily P50 of gross bookings
    p50_7: np.ndarray        # (S, H) 7-day P50
    naive7: np.ndarray       # (S, H) trailing-rate naive over 7 days
    retention: np.ndarray    # (S,) 1 - cancellation share (net demand = gross × retention)
    params: dict


def pickup_curves(p: Panel, as_of: int, horizon: int) -> np.ndarray:
    m = (p.typ == type_code("booking")) & (p.fd >= as_of - C.PICKUP_LOOKBACK_DAYS) & (p.fd < as_of)
    lead = np.clip(p.lead[m], 0, horizon)
    hist = np.zeros((p.n_city, horizon + 1))
    np.add.at(hist, (p.city[m], lead), 1.0)
    series_hist = p.agg @ hist                      # (S, H+1)
    n = series_hist.sum(axis=1, keepdims=True)
    cum_below = np.cumsum(series_hist, axis=1)[:, :horizon]   # count with lead < h for h = 1..H
    local = np.divide(cum_below, n, out=np.zeros_like(cum_below), where=n > 0)
    national = local[-1:, :]
    return (n * local + C.PICKUP_PRIOR_BOOKINGS * national) / (n + C.PICKUP_PRIOR_BOOKINGS)


def retention(p: Panel, as_of: int) -> np.ndarray:
    b = trailing_counts(p, as_of, C.PICKUP_LOOKBACK_DAYS, "booking")
    c = trailing_counts(p, as_of, C.PICKUP_LOOKBACK_DAYS, "cancellation")
    nat = c[-1] / b[-1] if b[-1] > 0 else 0.0
    share = (c + C.CANCEL_PRIOR_BOOKINGS * nat) / (b + C.CANCEL_PRIOR_BOOKINGS)
    return np.clip(1 - share, 0, 1)


def series_rates(p: Panel, as_of: int, window: int) -> tuple[np.ndarray, dict]:
    m = (p.typ == type_code("booking")) & (p.fd >= as_of - window) & (p.fd < as_of) & (p.occ < as_of)
    counts = np.bincount(p.city[m], minlength=p.n_city)
    shrunk_city, info = city_rates(counts, window, p.city_region, len(p.regions))
    return p.agg @ shrunk_city, info


def origin_features(p: Panel, as_of: int, horizon: int, window: int, season_idx: dict | None = None) -> OriginFeatures:
    h = np.arange(1, horizon + 1)
    stay = as_of + h
    otb = {t: forward_counts(p, as_of, horizon, t, known_only=True) for t in ("booking", "cancellation", "search", "view")}
    otb7 = {t: centred_window_sum(v, C.WINDOW_DAYS) for t, v in otb.items()}
    rate, info = series_rates(p, as_of, window)
    pick = pickup_curves(p, as_of, horizon)
    idx = season_idx if season_idx is not None else seasonal_indices(p, as_of)
    season = index_for_days(idx, stay)
    season7 = centred_window_sum(season[None, :], C.WINDOW_DAYS)[0] / C.WINDOW_DAYS
    gross = otb["booking"] + rate[:, None] * season[None, :] * pick
    p50_7 = centred_window_sum(gross, C.WINDOW_DAYS)
    naive7 = np.repeat((rate * C.WINDOW_DAYS)[:, None], horizon, axis=1)
    n_city, n_reg = p.n_city, len(p.regions)
    level = np.concatenate([np.zeros(n_city), np.ones(n_reg), [2.0]])
    return OriginFeatures(as_of=as_of, horizon=horizon, level=level, h=h, stay_day=stay, otb=otb, otb7=otb7,
                          rate=rate, pick=pick, season=season, season7=season7, gross=gross, p50_7=p50_7,
                          naive7=naive7, retention=retention(p, as_of),
                          params={**info, "window_days": window, "month_index": idx["month"].tolist(),
                                  "dow_index": idx["dow"].tolist()})


def realised(p: Panel, as_of: int, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    """Realised daily gross bookings and their centred 7-day sums (for training/backtest targets)."""
    y = forward_counts(p, as_of, horizon, "booking", known_only=False)
    return y, centred_window_sum(y, C.WINDOW_DAYS)


def feature_matrix(f: OriginFeatures) -> np.ndarray:
    """Rows = series × horizon, columns = FEATURE_NAMES (the LightGBM design matrix)."""
    S, H = f.p50_7.shape
    month = np.array([(EPOCH + timedelta(days=int(d))).month for d in f.stay_day], dtype=float)
    cols = [
        np.repeat(f.level, H),
        np.tile(f.h.astype(float), S),
        f.otb7["booking"].ravel(), f.otb7["cancellation"].ravel(), f.otb7["search"].ravel(), f.otb7["view"].ravel(),
        np.repeat(f.rate, H), f.p50_7.ravel(), f.naive7.ravel(), np.tile(f.season7, S), np.tile(month, S),
    ]
    return np.column_stack(cols)


FEATURE_NAMES = ["level", "h", "otb7_booking", "otb7_cancellation", "otb7_search", "otb7_view", "rate",
                 "pickup_p50_7", "naive_7", "season_7", "month"]

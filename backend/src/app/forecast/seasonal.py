"""Learned seasonal indices, shrunk toward 1.0 by their own evidence (ARCHITECTURE F9, §7.7 G3).

Month-of-year uses ratio-to-moving-average (classical decomposition), so growth or a data ramp-up is
NOT mistaken for seasonality: each calendar month is compared with the average of its neighbours, and a
month with no neighbour on both sides (the first/last month of history) contributes no evidence.
    index_m = 1 + z_m · (ratio_m − 1),  z_m = τ² / (τ² + noise_m),  τ² estimated by moments.
If the data shows no seasonal spread beyond Poisson noise (as APS-02.db does), every index is 1.0.
If a deployment has real seasonality, the indices grow automatically. Nothing is hard-coded.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.forecast.panel import EPOCH, Panel, type_code


def _shrunk_index(counts: np.ndarray, exposure: np.ndarray) -> np.ndarray:
    ok = exposure > 0
    out = np.ones_like(counts, dtype=np.float64)
    if ok.sum() < 2:
        return out
    rate = np.divide(counts, exposure, out=np.zeros_like(counts, dtype=np.float64), where=ok)
    mu = counts[ok].sum() / exposure[ok].sum()
    if mu <= 0:
        return out
    rel = rate / mu
    noise = np.divide(1.0, mu * exposure, out=np.full_like(rel, np.inf), where=ok)
    tau2 = max(0.0, float(np.var(rel[ok]) - np.mean(noise[ok])))
    if tau2 <= 0:
        return out
    z = tau2 / (tau2 + noise)
    out[ok] = 1 + z[ok] * (rel[ok] - 1)
    return out


def _month_ratio_to_moving_average(ev_days: np.ndarray, first: int, as_of: int) -> tuple[np.ndarray, np.ndarray]:
    """Per month-of-year: exposure-weighted mean of rate(month) / mean(rate(prev month), rate(next month)),
    and the effective exposure behind it. Only complete calendar months with both neighbours count."""
    span = [EPOCH + timedelta(days=int(d)) for d in range(first, as_of)]
    keys = sorted({(d.year, d.month) for d in span})
    days_in = {k: 0 for k in keys}
    for d in span:
        days_in[(d.year, d.month)] += 1
    counts = {k: 0 for k in keys}
    for d in (EPOCH + timedelta(days=int(x)) for x in ev_days):
        if (d.year, d.month) in counts:
            counts[(d.year, d.month)] += 1
    full = [k for k in keys if days_in[k] >= _days_in_month(k)]
    rate = {k: counts[k] / days_in[k] for k in full}
    num = np.zeros(12)
    expo = np.zeros(12)
    for i, k in enumerate(full):
        prev_k, next_k = _shift(k, -1), _shift(k, 1)
        if prev_k in rate and next_k in rate:
            ma = (rate[prev_k] + rate[next_k]) / 2
            if ma > 0:
                num[k[1] - 1] += (rate[k] / ma) * days_in[k]
                expo[k[1] - 1] += days_in[k]
    ratio = np.divide(num, expo, out=np.ones(12), where=expo > 0)
    return ratio, expo


def _days_in_month(k: tuple[int, int]) -> int:
    y, m = k
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - date(y, m, 1)).days


def _shift(k: tuple[int, int], n: int) -> tuple[int, int]:
    y, m = k
    m0 = (m - 1) + n
    return (y + m0 // 12, m0 % 12 + 1)


def _shrink_ratio(ratio: np.ndarray, exposure: np.ndarray, mu: float) -> np.ndarray:
    ok = exposure > 0
    out = np.ones_like(ratio)
    if ok.sum() < 2 or mu <= 0:
        return out
    noise = np.divide(1.0, mu * exposure, out=np.full_like(ratio, np.inf), where=ok)
    tau2 = max(0.0, float(np.var(ratio[ok]) - np.mean(noise[ok])))
    if tau2 <= 0:
        return out
    z = tau2 / (tau2 + noise)
    out[ok] = 1 + z[ok] * (ratio[ok] - 1)
    return out


def seasonal_indices(p: Panel, as_of: int) -> dict[str, np.ndarray]:
    """National month-of-year (12, detrended) and day-of-week (7) indices from complete stay dates before as_of."""
    m = (p.typ == type_code("booking")) & (p.fd < as_of) & (p.occ < as_of)
    if not m.any():
        return {"month": np.ones(12), "dow": np.ones(7)}
    days = p.fd[m]
    first = int(days.min())
    mu = float(days.size) / max(as_of - first, 1)
    ratio, expo = _month_ratio_to_moving_average(days, first, as_of)
    span_dow = np.array([(EPOCH + timedelta(days=int(d))).weekday() for d in range(first, as_of)])
    ev_dow = np.array([(EPOCH + timedelta(days=int(d))).weekday() for d in days])
    dows = np.bincount(ev_dow, minlength=7).astype(float)
    dow_exp = np.bincount(span_dow, minlength=7).astype(float)
    return {"month": _shrink_ratio(ratio, expo, mu), "dow": _shrunk_index(dows, dow_exp)}


def index_for_days(idx: dict[str, np.ndarray], stay_days: np.ndarray) -> np.ndarray:
    dates = [EPOCH + timedelta(days=int(d)) for d in stay_days]
    return np.array([idx["month"][d.month - 1] * idx["dow"][d.weekday()] for d in dates])


def index_for_date(idx: dict[str, np.ndarray], d: date) -> float:
    return float(idx["month"][d.month - 1] * idx["dow"][d.weekday()])

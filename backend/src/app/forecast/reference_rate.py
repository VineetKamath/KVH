"""Reference rate: the hotel's rate card with its per-night noise removed (docs/DECISIONS.md D-17).

The provided nightly rate (inventory_calendar.price) is used as the price baseline. Read raw, it carries two
things: structure the hotel intends (room level, a weekday/weekend profile, slow seasonal drift) and
night-to-night jitter. Jitter passed through the engine becomes a price curve that zig-zags between
neighbouring nights for no reason a guest or manager could see.

Per room, in log space (so every effect is multiplicative):

    log rate = level + weekday effect + trend + residual

  * level          median log rate of the room
  * weekday effect per-room weekday means, shrunk toward the all-room weekday profile by their own noise
                   (empirical Bayes: z = τ² / (τ² + σ²/n), τ² estimated by moments across rooms)
  * trend          centred moving average (defaults.REFERENCE_TREND_HALF_WIDTH each side) of the weekday-adjusted rate
  * residual       kept with weight ρ, the pooled lag-1 autocorrelation of residuals, clipped to [0, 1]

ρ is the self-measuring part. Deliberate date-specific pricing (a festival week, a long weekend) lasts
several nights, so residuals are autocorrelated and ρ keeps them. Independent jitter has ρ ≈ 0 and is
dropped. Nothing here is fitted to one dataset: every weight is estimated from the calendar it is given,
and events a hotel wants priced are still added explicitly by approved event signals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from app.forecast import defaults as C




@dataclass(frozen=True)
class ReferenceFit:
    reference: dict[tuple[str, str], float]   # (entity_id, for_date) → reference rate
    residual_weight: float                     # ρ: share of the night-specific deviation kept
    weekday_profile: list[float]               # pooled weekday multipliers, Monday first
    jitter_before: float                       # mean |log change| between consecutive nights, raw
    jitter_after: float                        # same, reference rate
    noise_sd: float                            # sd of the dropped log residual


def _centred_mean(x: np.ndarray, k: int) -> np.ndarray:
    c = np.concatenate([[0.0], np.cumsum(x)])
    n = x.size
    lo = np.clip(np.arange(n) - k, 0, n)
    hi = np.clip(np.arange(n) + k + 1, 0, n)
    return (c[hi] - c[lo]) / (hi - lo)


def _lag1(resid: list[np.ndarray]) -> float:
    num = sum(float(np.sum(r[1:] * r[:-1])) for r in resid if r.size > 2)
    den = sum(float(np.sum(r * r)) for r in resid if r.size > 2)
    return num / den if den > 0 else 0.0


def fit(rows: list[tuple[str, str, float]]) -> ReferenceFit:
    """rows: (entity_id, for_date ISO, price). Returns the reference rate for every input row."""
    by_room: dict[str, list[tuple[date, float]]] = {}
    for ent, fd, price in rows:
        if price and price > 0:
            by_room.setdefault(ent, []).append((date.fromisoformat(fd), float(price)))
    rooms = {e: sorted(v) for e, v in by_room.items()}
    if not rooms:
        return ReferenceFit({}, 0.0, [1.0] * 7, 0.0, 0.0, 0.0)

    # 1. level and raw weekday effects per room
    level, dev, dows = {}, {}, {}
    for e, v in rooms.items():
        x = np.log([p for _, p in v])
        level[e] = float(np.median(x))
        dev[e] = x - level[e]
        dows[e] = np.array([d.weekday() for d, _ in v])
    # means (not medians) so the moment estimator of τ² below is consistent: var(mean) = σ²/n exactly
    pooled = np.array([float(np.mean(np.concatenate([dev[e][dows[e] == w] for e in rooms])))
                       if any((dows[e] == w).any() for e in rooms) else 0.0 for w in range(7)])
    raw_eff = {e: np.array([float(np.mean(dev[e][dows[e] == w])) if (dows[e] == w).any() else pooled[w] for w in range(7)])
               for e in rooms}
    counts = {e: np.bincount(dows[e], minlength=7).astype(float) for e in rooms}

    # noise variance of one night around its room's weekday effect
    resid0 = np.concatenate([dev[e] - raw_eff[e][dows[e]] for e in rooms])
    sigma2 = float(np.var(resid0)) if resid0.size > 1 else 0.0

    # 2. shrink each room's weekday effect toward the pooled profile (empirical Bayes)
    diffs = np.array([raw_eff[e] - pooled for e in rooms])
    noise_var = np.array([sigma2 / np.maximum(counts[e], 1.0) for e in rooms])
    tau2 = max(0.0, float(np.var(diffs) - np.mean(noise_var))) if len(rooms) > 1 else float(np.var(diffs))
    eff = {}
    for i, e in enumerate(rooms):
        tot = tau2 + noise_var[i]
        z = np.divide(tau2, tot, out=np.ones_like(tot), where=tot > 0)
        eff[e] = pooled + z * (raw_eff[e] - pooled)

    # 3. trend of the weekday-adjusted series, 4. residual persistence
    trend, resid = {}, {}
    for e in rooms:
        adj = dev[e] - eff[e][dows[e]]
        trend[e] = _centred_mean(adj, C.REFERENCE_TREND_HALF_WIDTH)
        resid[e] = adj - trend[e]
    rho = float(np.clip(_lag1(list(resid.values())), 0.0, 1.0))

    ref, before, after, dropped = {}, [], [], []
    for e, v in rooms.items():
        logr = level[e] + eff[e][dows[e]] + trend[e] + rho * resid[e]
        r = np.exp(logr)
        for (d, _), val in zip(v, r):
            ref[(e, d.isoformat())] = float(val)
        raw = np.log([p for _, p in v])
        before.append(np.abs(np.diff(raw)))
        after.append(np.abs(np.diff(logr)))
        dropped.append((1 - rho) * resid[e])
    mean = lambda parts: float(np.mean(np.concatenate(parts))) if parts and np.concatenate(parts).size else 0.0  # noqa: E731
    return ReferenceFit(ref, rho, [float(np.exp(p)) for p in pooled], mean(before), mean(after),
                        float(np.std(np.concatenate(dropped))) if dropped else 0.0)

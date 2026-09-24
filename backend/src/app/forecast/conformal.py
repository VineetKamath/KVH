"""Conformal calibration of the P10-P90 band (ARCHITECTURE §7.7 G2).

CQR (conformalised quantile regression) with ADAPTIVE conformal inference over calibration batches:
    score  E = max(q10 − y, y − q90) / s,   s = sqrt(P50 + offset)        (normalised, shared across levels)
    band   [q10 − Q·s, q90 + Q·s],  Q = (1 − α_t) quantile of past scores
    ACI    α_{t+1} = α_t + γ (α* − miss_t)      (Gibbs & Candès 2021; long-run coverage without stationarity)
Also provides the split-conformal band around the pickup P50 (the fallback when LightGBM is unavailable).
"""
from __future__ import annotations

import numpy as np

from app.forecast import defaults as C

NOMINAL_MISS = 1 - C.TARGET_COVERAGE


def scale(p50: np.ndarray) -> np.ndarray:
    return np.sqrt(np.maximum(p50, 0) + C.SCORE_OFFSET)


def cqr_scores(y: np.ndarray, q_lo: np.ndarray, q_hi: np.ndarray, p50: np.ndarray) -> np.ndarray:
    return np.maximum(q_lo - y, y - q_hi) / scale(p50)


def aci_calibrate(batches: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]) -> dict:
    """batches: time-ordered (y, q_lo, q_hi, p50) per calibration origin. Returns the final Q and the trace."""
    alpha = NOMINAL_MISS
    history: list[np.ndarray] = []
    trace = []
    for y, lo, hi, p50 in batches:
        scores = cqr_scores(y, lo, hi, p50)
        pool = np.concatenate(history) if history else scores
        level = float(np.clip(1 - alpha, 0, 1))
        q = float(np.quantile(pool, level))
        s = scale(p50)
        miss = float(np.mean((y < lo - q * s) | (y > hi + q * s)))
        trace.append({"alpha": alpha, "Q": q, "coverage": 1 - miss})
        alpha = alpha + C.ACI_GAMMA * (NOMINAL_MISS - miss)
        history.append(scores)
    pool = np.concatenate(history) if history else np.zeros(1)
    final_q = float(np.quantile(pool, float(np.clip(1 - alpha, 0, 1))))
    return {"Q": final_q, "alpha": alpha, "trace": trace}


def apply_band(q_lo: np.ndarray, q_hi: np.ndarray, p50: np.ndarray, Q: float) -> tuple[np.ndarray, np.ndarray]:
    s = scale(p50)
    lo = np.maximum(0, np.minimum(q_lo - Q * s, p50))
    hi = np.maximum(q_hi + Q * s, p50)
    return lo, hi


def split_conformal(calib_y: np.ndarray, calib_p50: np.ndarray) -> tuple[float, float]:
    r = (calib_y - calib_p50) / scale(calib_p50)
    return float(np.quantile(r, NOMINAL_MISS / 2)), float(np.quantile(r, 1 - NOMINAL_MISS / 2))


def split_conformal_band(p50: np.ndarray, r_lo: float, r_hi: float) -> tuple[np.ndarray, np.ndarray]:
    s = scale(p50)
    return np.maximum(0, np.minimum(p50 + r_lo * s, p50)), np.maximum(p50 + r_hi * s, p50)


def interval_score(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    a = NOMINAL_MISS
    return float(np.mean((hi - lo) + (2 / a) * (lo - y) * (y < lo) + (2 / a) * (y - hi) * (y > hi)))


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))

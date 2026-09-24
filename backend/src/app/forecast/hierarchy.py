"""Hierarchical empirical-Bayes pooling (ARCHITECTURE §7.7 G3/G4). Every strength is ESTIMATED.

For Poisson counts n_g over exposure T_g with true rates λ_g ~ (μ, τ²):
    Var(n_g/T_g) = τ² + μ/T_g   →   τ² = max(0, var(r) − mean(μ/T))   (method of moments)
    credibility z_g = T_g / (T_g + k),  k = μ / τ²       (k = ∞ ⇒ full pooling when τ² = 0)
The same logic gives κ for the demand-index credibility: κ = 1 / τ²_rel, where τ²_rel is the
between-period variance of relative demand beyond Poisson noise.
"""
from __future__ import annotations

import numpy as np


def method_of_moments_k(rates: np.ndarray, exposure: np.ndarray) -> float:
    """Shrinkage strength k (in exposure units). Returns +inf when the data shows no real spread."""
    ok = exposure > 0
    if ok.sum() < 2:
        return float("inf")
    r, t = rates[ok], exposure[ok]
    mu = float(np.average(r, weights=t))
    if mu <= 0:
        return float("inf")
    tau2 = float(np.var(r) - np.mean(mu / t))
    return float("inf") if tau2 <= 0 else mu / tau2


def shrink(rates: np.ndarray, exposure: np.ndarray, parent: np.ndarray, k: float) -> np.ndarray:
    if not np.isfinite(k):
        return parent.astype(np.float64).copy()
    z = exposure / (exposure + k)
    return z * rates + (1 - z) * parent


def city_rates(counts: np.ndarray, window: int, city_region: np.ndarray, n_regions: int) -> tuple[np.ndarray, dict]:
    """Two-level shrinkage: city → mean city rate of its region → national mean city rate."""
    n = counts.astype(np.float64)
    exposure = np.full(n.shape, float(window))
    r = n / window
    national = np.full(n.shape, r.mean() if r.size else 0.0)
    reg_sum = np.bincount(city_region, weights=r, minlength=n_regions)
    reg_cnt = np.bincount(city_region, minlength=n_regions).astype(np.float64)
    reg_mean = np.divide(reg_sum, reg_cnt, out=np.zeros(n_regions), where=reg_cnt > 0)
    reg_exposure = reg_cnt * window
    k_region = method_of_moments_k(reg_mean, reg_exposure)
    reg_shrunk = shrink(reg_mean, reg_exposure, np.full(n_regions, national[0] if n.size else 0.0), k_region)
    k_city = method_of_moments_k(r, exposure)
    shrunk = shrink(r, exposure, reg_shrunk[city_region], k_city)
    return shrunk, {"k_city_days": k_city, "k_region_days": k_region}


def relative_signal_variance(series: np.ndarray) -> float:
    """τ²_rel of a count series (e.g. national weekly demand): var(y/μ) beyond Poisson noise 1/μ."""
    y = series[np.isfinite(series)]
    if y.size < 2:
        return 0.0
    mu = y.mean()
    if mu <= 0:
        return 0.0
    return max(0.0, float(np.var(y / mu) - 1 / mu))


def kappa_from_signal_variance(tau2_rel: float) -> float:
    return float("inf") if tau2_rel <= 0 else 1 / tau2_rel


def credibility(n_eff: np.ndarray, kappa: float) -> np.ndarray:
    if not np.isfinite(kappa):
        return np.zeros_like(n_eff, dtype=np.float64)
    return n_eff / (n_eff + kappa)

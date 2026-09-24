"""LightGBM quantile regression for P10 / P90 of the 7-day demand signal (ARCHITECTURE §7.3-7.4).

Models are stored as LightGBM's own text format (never pickle), so loading a model can never execute code.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np

from app.forecast import defaults as C


def fit_quantiles(X: np.ndarray, y: np.ndarray) -> dict[float, str]:
    models: dict[float, str] = {}
    for q in C.QUANTILES:
        booster = lgb.train({**C.LGBM_PARAMS, "objective": "quantile", "alpha": q},
                            lgb.Dataset(X, y, free_raw_data=True), num_boost_round=C.LGBM_ROUNDS)
        models[q] = booster.model_to_string()
    return models


def predict_quantiles(models: dict[float, str], X: np.ndarray) -> dict[float, np.ndarray]:
    return {q: lgb.Booster(model_str=s).predict(X) for q, s in models.items()}

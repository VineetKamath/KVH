"""LightGBM Poisson point model: the P50 challenger. Reported by selection; ships only if it wins (G1)."""
from __future__ import annotations

import lightgbm as lgb
import numpy as np

from app.forecast import defaults as C


def fit_point(X: np.ndarray, y: np.ndarray) -> str:
    booster = lgb.train({**C.LGBM_PARAMS, "objective": "poisson"}, lgb.Dataset(X, y, free_raw_data=True),
                        num_boost_round=C.LGBM_ROUNDS)
    return booster.model_to_string()


def predict_point(model: str, X: np.ndarray) -> np.ndarray:
    return lgb.Booster(model_str=model).predict(X)

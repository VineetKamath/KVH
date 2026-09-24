"""Champion / challenger selection on the deployment's OWN recent history (ARCHITECTURE §7.7 G1).

A challenger replaces the incumbent only if it wins on Poisson deviance in at least
SELECTION_MIN_WINS of the last CALIBRATION_ORIGINS origins, improves the pooled deviance by at least
SELECTION_MIN_GAIN, and a Diebold-Mariano style paired test on per-point loss differences gives
p < SELECTION_P_VALUE. If the champion is worse than the trailing-rate naive forecast on a majority
of origins, the naive forecast ships: by construction we are never worse than the baseline we can measure.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

from app.forecast import defaults as C


def poisson_deviance_terms(y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    mu = np.maximum(mu, np.finfo(float).eps)
    safe_y = np.where(y > 0, y, 1)
    return 2 * (np.where(y > 0, y * np.log(safe_y / mu), 0) - (y - mu))


def decide(per_origin: dict[str, list[tuple[np.ndarray, np.ndarray]]], incumbent: str = "pickup") -> dict:
    """per_origin[name] = [(y, prediction) per calibration origin, in time order]."""
    scores = {name: [float(poisson_deviance_terms(y, m).mean()) for y, m in batches] for name, batches in per_origin.items()}
    pooled = {name: float(np.mean(v)) for name, v in scores.items()}
    decision, champion, challenger, p_value = "keep", incumbent, None, None
    for name in per_origin:
        if name in (incumbent, "naive"):
            continue
        wins = sum(c < i for c, i in zip(scores[name], scores[incumbent]))
        gain = 1 - pooled[name] / pooled[incumbent] if pooled[incumbent] > 0 else 0.0
        diff = np.concatenate([poisson_deviance_terms(y, m) for y, m in per_origin[name]]) - \
            np.concatenate([poisson_deviance_terms(y, m) for y, m in per_origin[incumbent]])
        p = float(stats.ttest_1samp(diff, 0.0, alternative="less").pvalue) if diff.size > 2 else 1.0
        challenger, p_value = name, p
        if wins >= C.SELECTION_MIN_WINS and gain >= C.SELECTION_MIN_GAIN and p < C.SELECTION_P_VALUE:
            decision, champion = "switch", name
    if "naive" in scores:
        naive_better = sum(n < c for n, c in zip(scores["naive"], scores[champion]))
        if naive_better > len(scores["naive"]) / 2:
            decision, champion = "fallback_naive", "naive"
    gain_vs_naive = 1 - pooled[champion] / pooled["naive"] if pooled.get("naive") else None
    return {"decision": decision, "champion": champion, "challenger": challenger, "p_value": p_value,
            "scores_per_origin": scores, "pooled_deviance": pooled, "gain_vs_naive": gain_vs_naive}

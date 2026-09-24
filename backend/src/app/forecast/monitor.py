"""Drift and quality monitors (ARCHITECTURE §7.7 G6). Pure: inputs are arrays and counts."""
from __future__ import annotations

import numpy as np

from app.forecast import defaults as C


def psi(reference: np.ndarray, current: np.ndarray, bins: int = C.PSI_BINS) -> float:
    """Population stability index of `current` against `reference` (quantile bins of the reference)."""
    ref = reference[np.isfinite(reference)]
    cur = current[np.isfinite(current)]
    if ref.size == 0 or cur.size == 0:
        return 0.0
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0
    r = np.histogram(np.clip(ref, edges[0], edges[-1]), edges)[0] / ref.size
    c = np.histogram(np.clip(cur, edges[0], edges[-1]), edges)[0] / cur.size
    eps = np.finfo(float).eps
    r, c = np.maximum(r, eps), np.maximum(c, eps)
    return float(np.sum((c - r) * np.log(c / r)))


def evaluate(selection: dict, coverage_trace: list[dict], feature_psi: dict[str, float], quality: dict) -> dict:
    alerts = []
    if selection.get("decision") == "fallback_naive":
        alerts.append("champion worse than naive on recent origins → naive forecast in use")
    covs = [t["coverage"] for t in coverage_trace]
    notes = []
    if covs and covs[-1] < C.COVERAGE_BAND[0]:
        alerts.append(f"P10-P90 coverage {covs[-1]:.2f} below {C.COVERAGE_BAND[0]}; ACI is widening the band")
    elif covs and covs[-1] > C.COVERAGE_BAND[1]:
        notes.append(f"P10-P90 coverage {covs[-1]:.2f} above {C.COVERAGE_BAND[1]} (conservative; expected for sparse counts)")
    for name, v in feature_psi.items():
        if v > C.PSI_ALERT:
            alerts.append(f"feature drift: PSI({name}) = {v:.2f}")
    for name, v in quality.items():
        if v.get("alert"):
            alerts.append(f"data quality: {name} {v}")
    return {"status": "degraded" if alerts else "ok", "alerts": alerts, "notes": notes, "feature_psi": feature_psi,
            "coverage_trace": covs, "quality": quality}

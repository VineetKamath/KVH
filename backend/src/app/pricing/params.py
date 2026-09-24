"""Default engine settings and (de)serialisation of dp_engine_config.

These are *business* settings (how far each factor may move a price, how events weigh), stated and
editable by the revenue manager. They are not fitted to the dataset. Demand pressure 0.70-1.30 is
justified by the provided price_history.demand_index 5th-95th percentile (ARCHITECTURE F3).
"""
from __future__ import annotations

import json
from decimal import Decimal

from app.pricing.types import EngineParams, FactorBound

D = Decimal

DEFAULT_FACTOR_BOUNDS: dict[str, tuple[str, str]] = {
    "seasonality": ("0.95", "1.08"),
    "demand": ("0.70", "1.30"),
    "pace": ("0.95", "1.10"),
    "lead_time": ("0.92", "1.12"),
    "event": ("1.00", "1.15"),
    "competitor": ("0.90", "1.06"),
    "cancellation": ("0.93", "1.10"),
    "uncertainty": ("0.94", "1.06"),
}

DEFAULT_EVENT_IMPACT = {"minor": "0.03", "moderate": "0.07", "major": "0.12"}
DEFAULT_EVENT_CONFIDENCE = {"high": "1.0", "medium": "0.7", "low": "0.4"}


def default_config_json() -> dict:
    return {
        "factor_bounds": {k: {"lo": lo, "hi": hi, "enabled": True} for k, (lo, hi) in DEFAULT_FACTOR_BOUNDS.items()},
        "event_impact": DEFAULT_EVENT_IMPACT,
        "event_confidence": DEFAULT_EVENT_CONFIDENCE,
        "competitor_sensitivity": "0.06",
        "cancellation_sensitivity": "0.10",
        "damper_max_pull": "0.5",
    }


def params_from_row(row: dict) -> EngineParams:
    fb_json = json.loads(row["factor_bounds"])
    bounds = fb_json["factor_bounds"] if "factor_bounds" in fb_json else fb_json
    extra = fb_json if "factor_bounds" in fb_json else default_config_json()
    return EngineParams(
        version=int(row["version"]),
        factor_bounds={k: FactorBound(D(v["lo"]), D(v["hi"]), bool(v.get("enabled", True))) for k, v in bounds.items()},
        auto_band_pct=D(row["auto_band_pct"]) / D(100),
        anomaly_z=D(row["anomaly_z"]),
        anomaly_move_pct=D(row["anomaly_move_pct"]) / D(100),
        kill_switch=bool(row["kill_switch_active"]),
        event_impact={k: D(v) for k, v in extra.get("event_impact", DEFAULT_EVENT_IMPACT).items()},
        event_confidence={k: D(v) for k, v in extra.get("event_confidence", DEFAULT_EVENT_CONFIDENCE).items()},
        competitor_sensitivity=D(extra.get("competitor_sensitivity", "0.06")),
        cancellation_sensitivity=D(extra.get("cancellation_sensitivity", "0.10")),
        damper_max_pull=D(extra.get("damper_max_pull", "0.5")),
    )


def default_params(version: int = 1) -> EngineParams:
    return params_from_row({
        "version": version,
        "factor_bounds": json.dumps(default_config_json()),
        "auto_band_pct": "8.00",
        "anomaly_z": "2.50",
        "anomaly_move_pct": "12.00",
        "kill_switch_active": 0,
    })


def with_overrides(params: EngineParams, factor_bounds: dict[str, FactorBound] | None = None, **kw) -> EngineParams:
    from dataclasses import replace

    fb = dict(params.factor_bounds)
    if factor_bounds:
        fb.update(factor_bounds)
    return replace(params, factor_bounds=fb, **kw)

"""Forecast lifecycle: fit weekly on the business clock, cache, persist, and record every selection.

Models persist as JSON (LightGBM's own text model inside) under var/models/, never pickle.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import date, timedelta

import pandas as pd

from app.config import VAR_DIR
from app.core.clock import wall_now_iso
from app.core.ids import new_id
from app.forecast import defaults as FC
from app.forecast.interface import ForecastState, fit
from app.forecast.panel import EPOCH, Panel, build_panel, day_number
from app.services.data import load_events

MODEL_DIR = VAR_DIR / "models"
RETRAIN_EVERY_DAYS = 7
_lock = threading.Lock()
_cache: dict[int, ForecastState] = {}


def jsonable(o):
    """Recursively convert numpy scalars and non-finite floats so the result is STRICT JSON (json_valid)."""
    import math

    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if hasattr(o, "item"):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def strict_dumps(o) -> str:
    return json.dumps(jsonable(o), allow_nan=False, default=str)


def _to_json(state: ForecastState) -> str:
    d = asdict(state)
    if d["quantile_models"] is not None:
        d["quantile_models"] = {str(k): v for k, v in d["quantile_models"].items()}
    return json.dumps(d, default=lambda o: o.item() if hasattr(o, "item") else str(o))


def _from_json(text: str) -> ForecastState:
    d = json.loads(text)
    if d.get("quantile_models") is not None:
        d["quantile_models"] = {float(k): v for k, v in d["quantile_models"].items()}
    d["conformal"] = tuple(d["conformal"])
    d["skill_by_level"] = {int(k): v for k, v in d["skill_by_level"].items()}
    d["kappa_by_level"] = {int(k): (float("inf") if v is None else float(v)) for k, v in d.get("kappa_by_level", {}).items()}
    d["window_scores"] = {int(k): v for k, v in d["window_scores"].items()}
    return ForecastState(**d)


def _load_from_disk(as_of: int) -> ForecastState | None:
    path = MODEL_DIR / f"forecast_{as_of}.json"
    if path.exists():
        return _from_json(path.read_text(encoding="utf-8"))
    return None


def panel(conn: sqlite3.Connection) -> Panel:
    return build_panel(load_events(conn))


def state_for(conn: sqlite3.Connection, business: date, p: Panel | None = None, force: bool = False) -> tuple[ForecastState, Panel]:
    """The forecast state in force on `business`: the latest fit made within the last RETRAIN_EVERY_DAYS days."""
    p = p if p is not None else panel(conn)
    target = day_number(business)
    with _lock:
        if not force:
            candidates = sorted([k for k in _cache if target - RETRAIN_EVERY_DAYS < k <= target], reverse=True)
            if candidates:
                return _cache[candidates[0]], p
            for back in range(RETRAIN_EVERY_DAYS):
                s = _load_from_disk(target - back)
                if s is not None:
                    _cache[s.as_of] = s
                    _ensure_selection_recorded(conn, s)  # the disk cache outlives a reseed; the DB record must not be lost
                    return s, p
        state = fit(p, target)
        _cache[target] = state
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        (MODEL_DIR / f"forecast_{target}.json").write_text(_to_json(state), encoding="utf-8")
    record_selection(conn, state)
    return state, p


def _ensure_selection_recorded(conn: sqlite3.Connection, state: ForecastState) -> None:
    as_of = (EPOCH + timedelta(days=state.as_of)).isoformat()
    if conn.execute("SELECT 1 FROM dp_model_selection WHERE as_of_date = ? LIMIT 1", (as_of,)).fetchone() is None:
        record_selection(conn, state)


def record_selection(conn: sqlite3.Connection, state: ForecastState) -> None:
    as_of = (EPOCH + timedelta(days=state.as_of)).isoformat()
    start = (EPOCH + timedelta(days=state.as_of - FC.TRAIN_WEEKS * FC.WINDOW_DAYS)).isoformat()
    sel, iv = state.selection, state.interval_selection
    params = {**{k: v for k, v in state.params.items() if k not in ("month_index", "dow_index")},
              "month_index": state.params.get("month_index"), "dow_index": state.params.get("dow_index"),
              "window_days": state.window, "window_scores": state.window_scores, "aci_alpha": state.alpha,
              "cqr_Q": state.Q, "monitor": state.monitor}
    clean = jsonable(params)
    now = wall_now_iso()
    conn.execute(
        "INSERT INTO dp_model_selection (selection_id, as_of_date, window_from_date, window_to_date, component, champion, "
        "challenger, scores, dm_p_value, decision, params, created_at) VALUES (?,?,?,?, 'p50', ?,?,?,?,?,?,?)",
        (new_id("dpms"), as_of, start, as_of, sel["champion"], sel.get("challenger"),
         strict_dumps({"per_origin": sel["scores_per_origin"], "pooled": sel["pooled_deviance"],
                       "gain_vs_naive": sel.get("gain_vs_naive")}),
         None if sel.get("p_value") is None else str(sel["p_value"]), sel["decision"], strict_dumps(clean), now))
    conn.execute(
        "INSERT INTO dp_model_selection (selection_id, as_of_date, window_from_date, window_to_date, component, champion, "
        "challenger, scores, dm_p_value, decision, params, created_at) VALUES (?,?,?,?, 'interval', ?,?,?,?,?,?,?)",
        (new_id("dpms"), as_of, start, as_of, iv["method"],
         "pickup_lgbmq" if iv["method"] != "pickup_lgbmq" else "pickup_conformal", strict_dumps(iv["scores"]), None,
         "keep" if iv["method"] != "trailing_naive" else "fallback_naive", strict_dumps(clean), now))


def reset_cache() -> None:
    with _lock:
        _cache.clear()


def events_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    return load_events(conn)

"""Forecasting gates (Phase 3): backtest thresholds, no leakage, no dataset-fitted literals, pure modules."""
from __future__ import annotations

import ast
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from app.config import SOURCE_DB
from app.db.conn import connect_readonly
from app.forecast.panel import build_panel, day_number
from app.forecast.pickup import origin_features
from app.services.data import load_events

FORECAST_DIR = Path(__file__).resolve().parents[2] / "backend" / "src" / "app" / "forecast"


@lru_cache(maxsize=1)
def events():
    return load_events(connect_readonly(SOURCE_DB))


def test_backtest_gate_matches_architecture():
    """ARCHITECTURE §7.4 ship gate, recomputed through production code on the §7.2 protocol."""
    from app.forecast.backtest import run

    r = run(build_panel(events()), date(2025, 10, 1), date(2026, 4, 1),
            [date(2026, 6, 1), date(2026, 6, 15), date(2026, 7, 1)], 60, date(2026, 8, 30), use_lightgbm=False)
    imp = r["improvement_vs_naive"]
    assert imp["city_day_poisson_deviance"] >= 0.20, imp
    assert imp["city_day_mae"] >= 0.20, imp
    assert r["pickup"]["national_week_accuracy"] >= 0.85, r["pickup"]
    assert r["pickup"]["national_week_accuracy"] > r["naive"]["national_week_accuracy"]
    assert r["pickup"]["national_day_accuracy"] > r["naive"]["national_day_accuracy"]
    cov = r["interval"]["pickup_conformal"]["coverage"]
    assert 0.72 <= cov <= 0.88, cov


def test_no_leakage_features_ignore_the_future():
    """Features at as-of D must not change when events that occurred on/after D are removed."""
    ev = events()
    D = date(2026, 6, 1)
    full = origin_features(build_panel(ev), day_number(D), 60, 56)
    past_only = ev[ev["occurred_date"] < D]
    cut = origin_features(build_panel(past_only), day_number(D), 60, 56)
    # same series ordering is guaranteed when no city disappears; compare on the national series
    assert np.allclose(full.gross[-1], cut.gross[-1])
    assert np.allclose(full.otb["booking"][-1], cut.otb["booking"][-1])
    assert np.isclose(full.rate[-1], cut.rate[-1])


ALLOWED_INTS = {0, 1, 2, 7, 12}     # arithmetic identities and calendar facts (days/week, months/year)
ALLOWED_FLOATS = {0.0, 1.0, 2.0}


@pytest.mark.parametrize("path", sorted(p for p in FORECAST_DIR.glob("*.py") if p.name not in {"defaults.py", "__init__.py"}))
def test_no_fitted_literals_outside_defaults(path: Path):
    """G3: nothing in forecast/ may contain a number fitted to APS-02.db; constants live in defaults.py."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            v = node.value
            if (isinstance(v, int) and v not in ALLOWED_INTS) or (isinstance(v, float) and v not in ALLOWED_FLOATS):
                bad.append((node.lineno, v))
    assert not bad, f"{path.name}: numeric literals outside defaults.py: {bad}"


PURE_DIRS = ("pricing", "forecast")
FORBIDDEN_IMPORTS = ("app.db", "app.api", "app.services", "app.ai", "sqlite3")
FORBIDDEN_CALLS = ("datetime.now", "date.today", "time.time", "wall_now")


@pytest.mark.parametrize("path", sorted(p for d in PURE_DIRS for p in (FORECAST_DIR.parent / d).glob("*.py")))
def test_pure_modules_do_no_io_and_read_no_clock(path: Path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for n in names:
                assert not any(n == f or n.startswith(f + ".") for f in FORBIDDEN_IMPORTS), f"{path.name} imports {n}"
    for call in FORBIDDEN_CALLS:
        assert call not in src, f"{path.name} reads the wall clock via {call}"

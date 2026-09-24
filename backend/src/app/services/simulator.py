"""What-if simulation (ARCHITECTURE §9.3): the SAME engine (`price_all` → `price_one`) on a different config.

A = the live configuration, B = A with the validated WhatIfConfig applied. Nothing is published; the result is
stored in dp_experiment. Revenue is reported as a range across elasticity assumptions (§7.6), never a point.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.contracts.models import WhatIfConfig
from app.core.clock import business_date, wall_now_iso
from app.core.ids import new_id
from app.core.money import ZERO, money_str, quantize
from app.forecast.elasticity import estimate
from app.pricing.params import with_overrides
from app.pricing.types import EngineParams, FactorBound
from app.services import config_service
from app.services.cycle import _anchor_prices, _live_prices, price_all
from app.services.data import load_events
from app.services.errors import infeasible, invalid_id

_elasticity_cache: dict[int, dict] = {}


def elasticity(conn: sqlite3.Connection) -> dict:
    n = conn.execute("SELECT COUNT(*) FROM pricing_events").fetchone()[0]
    if n not in _elasticity_cache:
        _elasticity_cache.clear()
        _elasticity_cache[n] = estimate(load_events(conn))
    return _elasticity_cache[n]


def apply_config(params: EngineParams, cfg: WhatIfConfig) -> EngineParams:
    fb: dict[str, FactorBound] = {}
    for name, b in cfg.factor_bounds.items():
        fb[name] = FactorBound(Decimal(b.lo), Decimal(b.hi), b.enabled)
    for name in cfg.disable_factors:
        fb[name] = FactorBound(Decimal("1.00"), Decimal("1.00"), False)
    out = with_overrides(params, fb)
    if cfg.auto_band_pct is not None:
        out = replace(out, auto_band_pct=Decimal(cfg.auto_band_pct) / 100)
    return out


def _metrics(priced, eps_list: list[tuple[str, float]], live: dict) -> dict:
    prices = [p.decision.published for p in priced]
    n = len(prices)
    clamps = {"ceiling": 0, "floor": 0, "max_daily_movement": 0, "max_weekly_movement": 0}
    for p in priced:
        if p.source == "engine" and p.decision.guardrail.clamp_bound:
            clamps[p.decision.guardrail.clamp_bound] += 1
    needs_approval = sum(1 for p in priced if p.approval_status == "pending_approval")
    avg = quantize(sum(prices, ZERO) / n) if n else ZERO
    # revenue / demand indices relative to each date's baseline price (demand scale cancels in A-vs-B ratios)
    rev = {}
    for label, eps in eps_list:
        r = sum(float(p.decision.published) * (float(p.decision.published) / float(p.decision.inputs.baseline)) ** eps
                for p in priced)
        d = sum((float(p.decision.published) / float(p.decision.inputs.baseline)) ** eps for p in priced)
        rev[label] = {"revenue_index": r, "demand_index": d}
    return {"dates": n, "avg_price": money_str(avg), "clamps": clamps, "clamped": sum(clamps.values()),
            "approvals_needed": needs_approval, "_rev": rev}


def simulate(conn: sqlite3.Connection, entity_id: str, cfg: WhatIfConfig, name: str, prompt_text: str | None,
             actor: str) -> dict:
    bounds_all = config_service.all_bounds(conn)
    if entity_id not in bounds_all:
        raise invalid_id("room")
    bd = business_date(conn)
    params_a = config_service.engine_params(conn)
    params_b = apply_config(params_a, cfg)
    b_bounds = dict(bounds_all)
    base = bounds_all[entity_id]
    ceil_pct = Decimal(cfg.ceiling_change_pct or "0") / 100
    floor_pct = Decimal(cfg.floor_change_pct or "0") / 100
    new_floor, new_ceiling = quantize(base.floor * (1 + floor_pct)), quantize(base.ceiling * (1 + ceil_pct))
    if new_floor > new_ceiling:
        raise infeasible("the scenario would put the floor above the ceiling")
    b_bounds[entity_id] = replace(base, floor=new_floor, ceiling=new_ceiling)
    anchors = (_anchor_prices(conn, bd), _anchor_prices(conn, date.fromordinal(bd.toordinal() - 7), inclusive=True))
    live = _live_prices(conn)
    a, _ = price_all(conn, bd, "simulation", params_a, entities=[entity_id], anchors=anchors, live=live)
    b, _ = price_all(conn, bd, "simulation", params_b, bounds_override=b_bounds, entities=[entity_id], anchors=anchors, live=live)
    lo, hi = cfg.from_date, cfg.to_date
    if lo or hi:
        keep = lambda p: (lo is None or p.decision.inputs.for_date >= lo.isoformat()) and \
            (hi is None or p.decision.inputs.for_date <= hi.isoformat())  # noqa: E731
        a, b = [p for p in a if keep(p)], [p for p in b if keep(p)]
    if not a:
        raise infeasible("no priced dates in the chosen window")
    el = elasticity(conn)
    eps_list = [("data", el["elasticity"]), ("data_low", el["interval80"][0]), ("data_high", el["interval80"][1]),
                ("literature_prior", el["prior"]["mean"])]
    ma, mb = _metrics(a, eps_list, live), _metrics(b, eps_list, live)
    changes = {k: (mb["_rev"][k]["revenue_index"] / ma["_rev"][k]["revenue_index"] - 1) * 100 for k, _ in eps_list}
    occ = {k: (mb["_rev"][k]["demand_index"] / ma["_rev"][k]["demand_index"] - 1) * 100 for k, _ in eps_list}
    rng = sorted(changes.values())
    result = {
        "entity_id": entity_id, "business_date": bd.isoformat(), "window": [a[0].decision.inputs.for_date, a[-1].decision.inputs.for_date],
        "A": {k: v for k, v in ma.items() if k != "_rev"}, "B": {k: v for k, v in mb.items() if k != "_rev"},
        "revenue_change_pct": {k: round(v, 2) for k, v in changes.items()},
        "revenue_change_range_pct": [round(rng[0], 2), round(rng[-1], 2)],
        "demand_change_pct": {k: round(v, 2) for k, v in occ.items()},
        "per_date": [{"for_date": pa.decision.inputs.for_date, "a": money_str(pa.decision.published),
                      "b": money_str(pb.decision.published), "a_bound": pa.decision.guardrail.clamp_bound,
                      "b_bound": pb.decision.guardrail.clamp_bound} for pa, pb in zip(a, b)],
        "assumptions": {"elasticity": el, "bounds_b": {"floor": money_str(new_floor), "ceiling": money_str(new_ceiling)},
                        "engine_b": {"disabled": list(cfg.disable_factors),
                                     "factor_bounds": {k: v.model_dump() for k, v in cfg.factor_bounds.items()},
                                     "auto_band_pct": cfg.auto_band_pct}},
    }
    if any(not math.isfinite(v) for v in changes.values()):
        raise infeasible("simulation produced a non-finite revenue estimate")
    exp_id = new_id("dpe")
    now = wall_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("INSERT INTO dp_experiment (experiment_id, name, kind, config_a, config_b, split_pct, window_from_date, "
                     "window_to_date, prompt_text, metrics, assumptions, status, created_at, updated_at) "
                     "VALUES (?,?, 'what_if', ?,?,?,?,?,?,?,?, 'completed', ?, ?)",
                     (exp_id, name, json.dumps({"engine_config_version": params_a.version}),
                      cfg.model_dump_json(), cfg.split_pct, result["window"][0], result["window"][1], prompt_text,
                      json.dumps({k: result[k] for k in ("A", "B", "revenue_change_pct", "revenue_change_range_pct",
                                                          "demand_change_pct")}),
                      json.dumps(result["assumptions"], default=str), now, now))
        from app.services import audit

        audit.record(conn, actor, "simulate", f"dp_experiment:{exp_id}", after={"entity_id": entity_id, "name": name},
                     reason=prompt_text or name)
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"experiment_id": exp_id, **result}

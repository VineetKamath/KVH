"""The pricing cycle (ARCHITECTURE §6.1): one business day → a decision for every entity × stay date.

    kinds: warmup (seed history, auto-applied) · advance (clock + 1, then price) · reprice (same day, after a
           control change) · simulation (never publishes; see services/simulator.py)

Control order per decision: kill switch ▸ active override ▸ bound enforcement ▸ anomaly ▸ auto-band gate.
The whole cycle publishes in ONE `BEGIN IMMEDIATE` transaction: all-or-nothing, previous prices intact on failure.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.core.clock import business_date, set_business_date, wall_now_iso
from app.core.ids import new_id
from app.core.money import ONE, ZERO, dec, money_str
from app.features.builder import entity_on_the_books, simulated_comp_index, to_dec
from app.forecast import defaults as FC
from app.forecast.interface import ForecastResult, predict
from app.forecast.panel import EPOCH, day_number
from app.pricing.anomaly import is_anomalous
from app.pricing.engine import fixed_price_decision, move_fraction, price_one
from app.pricing.types import Bounds, Decision, EngineParams, EventUplift, PriceInputs
from app.services import audit, config_service, forecast_service
from app.services.data import entity_city_map, load_events
from app.services.serialize import canonical_factor_values, chain_json, explanation, factors_json

_cycle_lock = threading.Lock()
LIVE_STATUSES = ("auto_applied", "approved")


@dataclass
class Priced:
    decision: Decision
    source: str
    approval_status: str
    approval_reason: str | None
    anomaly: bool
    is_live: bool
    live_before: Decimal
    feature: dict
    forecast_key: tuple[str, str, str]


def _anchor_prices(conn: sqlite3.Connection, before: date, inclusive: bool = False) -> dict[tuple[str, str], Decimal]:
    op = "<=" if inclusive else "<"
    sql = (f"SELECT entity_id, for_date, published_price FROM (SELECT entity_id, for_date, published_price, "  # noqa: S608 - op is a constant
           f"ROW_NUMBER() OVER (PARTITION BY entity_id, for_date ORDER BY business_date DESC, created_at DESC, decision_id DESC) rn "
           f"FROM dp_price_decision WHERE entity_type = 'room_type' AND business_date {op} ? "
           f"AND approval_status IN ('auto_applied','approved')) WHERE rn = 1")
    return {(r[0], r[1]): dec(r[2]) for r in conn.execute(sql, (before.isoformat(),))}


def _live_prices(conn: sqlite3.Connection) -> dict[tuple[str, str], Decimal]:
    return {(r[0], r[1]): dec(r[2]) for r in conn.execute(
        "SELECT entity_id, for_date, published_price FROM dp_price_decision WHERE is_live = 1 AND entity_type = 'room_type'")}


def _approved_signals(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM dp_event_signal WHERE approved_at IS NOT NULL AND status = 'active'"):
        out[r["city_id"]].append(dict(r))
    return out


def _active_overrides(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    """Overrides expire on the WALL clock (a manager's hold is real time). Expired ones flip to 'expired'."""
    now = wall_now_iso()
    out = {}
    for r in conn.execute("SELECT * FROM dp_override WHERE status = 'active'"):
        if r["expires_at"] <= now:
            continue
        d = date.fromisoformat(r["from_date"])
        end = date.fromisoformat(r["to_date"])
        while d <= end:
            out[(r["entity_id"], d.isoformat())] = dict(r)
            d += timedelta(days=1)
    return out


def expire_overrides(conn: sqlite3.Connection) -> int:
    now = wall_now_iso()
    rows = conn.execute("SELECT override_id, entity_type, entity_id FROM dp_override WHERE status = 'active' AND expires_at <= ?",
                        (now,)).fetchall()
    for r in rows:
        conn.execute("UPDATE dp_override SET status = 'expired', updated_at = ? WHERE override_id = ?", (now, r["override_id"]))
        still = conn.execute("SELECT 1 FROM dp_override WHERE status = 'active' AND entity_id = ? AND expires_at > ?",
                             (r["entity_id"], now)).fetchone()
        if still is None:
            config_service.set_override_flag(conn, r["entity_type"], r["entity_id"], False)
        audit.record(conn, "system", "override_expired", f"dp_override:{r['override_id']}", reason="expiry reached")
    return len(rows)


def _series_index(result: ForecastResult) -> dict[tuple[str, str], int]:
    return {lab: i for i, lab in enumerate(result.labels)}


def _choose_series(city: str | None, region: str | None, idx: dict, skill: dict[int, float]) -> tuple[int, str]:
    """Finest hierarchy level whose measured credibility clears CREDIBILITY_MIN (G4)."""
    if city and ("city", city) in idx and skill.get(0, 0.0) >= FC.CREDIBILITY_MIN:
        return idx[("city", city)], "city"
    if region and ("region", region) in idx and skill.get(1, 0.0) >= FC.CREDIBILITY_MIN:
        return idx[("region", region)], "region"
    return idx[("national", "all")], "national"


def price_all(conn: sqlite3.Connection, business: date, kind: str, params: EngineParams,
              bounds_override: dict[str, Bounds] | None = None, entities: list[str] | None = None,
              anchors: tuple[dict, dict] | None = None, live: dict | None = None) -> tuple[list[Priced], dict]:
    """Price every (entity, stay date) for `business`. Reads the DB; writes nothing."""
    events = load_events(conn)
    state, pnl = forecast_service.state_for(conn, business)
    last_day = conn.execute("SELECT MAX(for_date) FROM dp_baseline").fetchone()[0]
    horizon = max(1, (date.fromisoformat(last_day) - business).days)
    result = predict(pnl, state, day_number(business), horizon)
    sidx = _series_index(result)
    city_of = entity_city_map(conn)
    region_of = {r[0]: r[1] for r in conn.execute("SELECT city_id, region FROM cities")}
    bounds = bounds_override or config_service.all_bounds(conn)
    signals = _approved_signals(conn)
    overrides = _active_overrides(conn)
    a1, a7 = anchors or (_anchor_prices(conn, business), _anchor_prices(conn, business - timedelta(days=7), inclusive=True))
    live = live if live is not None else _live_prices(conn)
    otb = entity_on_the_books(events, business)
    occ = {(r[0], r[1]): (r[2], r[3], r[4]) for r in conn.execute(
        "SELECT entity_id, for_date, booked_units, held_units, total_units FROM inventory_calendar WHERE entity_type = 'room_type'")}
    base_rows = conn.execute("SELECT entity_id, for_date, baseline_price, currency FROM dp_baseline "
                             "WHERE entity_type = 'room_type' AND for_date > ? ORDER BY entity_id, for_date",
                             (business.isoformat(),)).fetchall()
    wanted = set(entities) if entities else None
    f = result.features
    priced: list[Priced] = []
    per_entity_moves: dict[str, list[Decimal]] = defaultdict(list)
    for r in base_rows:
        ent, fd_s = r["entity_id"], r["for_date"]
        if wanted is not None and ent not in wanted:
            continue
        b = bounds.get(ent)
        if b is None:
            continue
        fd = date.fromisoformat(fd_s)
        h = (fd - business).days
        if h < 1 or h > horizon:
            continue
        city = city_of.get(ent)
        s, level = _choose_series(city, region_of.get(city) if city else None, sidx, state.skill_by_level)
        baseline = dec(r["baseline_price"])
        key = (ent, fd_s)
        live_price = live.get(key, baseline)
        evs = tuple(EventUplift(x["signal_id"], x["title"], x["impact_tag"], x["confidence_band"])
                    for x in signals.get(city, []) if x["start_date"] <= fd_s <= x["end_date"]) if city else ()
        inp = PriceInputs(
            entity_type="room_type", entity_id=ent, for_date=fd_s, business_date=business.isoformat(), currency=r["currency"],
            baseline=baseline, lead_time_days=h, season_index=to_dec(f.season[h - 1]),
            demand_ratio=to_dec(result.demand_ratio[s, h - 1]), credibility=to_dec(result.credibility[s, h - 1]),
            pace_ratio=to_dec(result.pace_ratio[s, h - 1]), lead_cdf=to_dec(f.pick[s, h - 1]), events=evs,
            comp_index=simulated_comp_index(ent, fd, business), cxl_ratio=to_dec(result.cxl_ratio[s]),
            rel_width=to_dec(result.rel_width[s, h - 1]), daily_anchor=a1.get(key, baseline),
            weekly_anchor=a7.get(key, baseline), live_price=live_price)
        if params.kill_switch:
            d, source = fixed_price_decision(inp, b, params, baseline), "kill_switch"
        elif key in overrides:
            d, source = fixed_price_decision(inp, b, params, dec(overrides[key]["price"])), "override"
        else:
            d, source = price_one(inp, b, params), "engine"
        booked, held, total = occ.get(key, (0, 0, 1))
        feature = {"lead_time_days": h, "occupancy_pct": money_str(Decimal(booked + held) * 100 / Decimal(max(total, 1))),
                   "otb_bookings": otb.get((ent, fd, "booking"), 0), "otb_cancellations": otb.get((ent, fd, "cancellation"), 0),
                   "otb_searches": otb.get((ent, fd, "search"), 0), "otb_views": otb.get((ent, fd, "view"), 0),
                   "pace_ratio": str(inp.pace_ratio), "cxl_rate_28d": str(inp.cxl_ratio), "comp_index": str(inp.comp_index),
                   "event_score": str(next(x.value for x in d.factors if x.name == "event")), "city_id": city, "level": level}
        lab = result.labels[s]
        priced.append(Priced(d, source, "auto_applied", None, False, True, live_price, feature, (lab[0], lab[1], fd_s)))
        per_entity_moves[ent].append(move_fraction(d.published, live_price) * (ONE if d.published >= live_price else -ONE))

    # approval gate (after all moves are known, so anomalies are judged against the room's own move distribution)
    for p in priced:
        d, b = p.decision, p.decision.bounds
        move = move_fraction(d.published, p.live_before)
        signed = move if d.published >= p.live_before else -move
        flagged, _ = is_anomalous(signed, per_entity_moves[d.inputs.entity_id], params.anomaly_z, params.anomaly_move_pct)
        p.anomaly = flagged and p.source == "engine" and move > ZERO
        live_outside = not (b.floor <= p.live_before <= b.ceiling)
        if kind == "warmup" or p.source != "engine" or live_outside or move == ZERO:
            continue
        if p.anomaly:
            p.approval_status, p.approval_reason, p.is_live = "pending_approval", "anomaly_flagged", False
        elif move > params.auto_band_pct:
            p.approval_status, p.approval_reason, p.is_live = "pending_approval", "outside_auto_band", False
    context = {"result": result, "state": state, "horizon": horizon}
    return priced, context


def publish(conn: sqlite3.Connection, business: date, kind: str, params: EngineParams, priced: list[Priced],
            context: dict, actor: str = "system", reason: str | None = None) -> dict:
    """Write one cycle atomically. Caller must NOT already hold a transaction."""
    result: ForecastResult = context["result"]
    state = context["state"]
    now = wall_now_iso()
    cycle_id = new_id("dpy")
    bd = business.isoformat()
    forecast_ids: dict[tuple[str, str, str], str] = {}
    fc_rows = []
    f = result.features
    for s, (level, key) in enumerate(result.labels):
        z = float(result.credibility[s, 0])
        band = "high" if z >= FC.BAND_HIGH else ("medium" if z >= FC.CREDIBILITY_MIN else "low")
        for hi in range(result.p50.shape[1]):
            fd = (EPOCH + timedelta(days=int(f.stay_day[hi]))).isoformat()
            fid = new_id("dpf")
            forecast_ids[(level, key, fd)] = fid
            fc_rows.append((fid, level, key, fd, bd, f"{result.p10[s, hi]:.4f}", f"{result.p50[s, hi]:.4f}",
                            f"{result.p90[s, hi]:.4f}", f"{result.normal[s, hi]:.4f}", f"{z:.4f}", band,
                            _method(result.method), state.model_version, now))
    n_clamped = 0
    with _cycle_lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("INSERT INTO dp_cycle (cycle_id, kind, business_date, engine_config_version, model_version, "
                         "status, started_at, updated_at) VALUES (?,?,?,?,?, 'running', ?, ?)",
                         (cycle_id, kind, bd, params.version, state.model_version, now, now))
            conn.executemany("INSERT INTO dp_forecast (forecast_id, level, level_key, for_date, as_of_date, p10, p50, p90, "
                             "normal_level, credibility, confidence_band, method, model_version, created_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", fc_rows)
            feat_rows, dec_rows, live_keys, sup_keys, inv_rows, hist_rows = [], [], [], [], [], []
            for p in priced:
                d = p.decision
                i = d.inputs
                fid = new_id("dpx")
                ft = p.feature
                feat_rows.append((fid, "room_type", i.entity_id, ft["city_id"], i.for_date, bd, ft["lead_time_days"],
                                  ft["occupancy_pct"], ft["otb_bookings"], ft["otb_cancellations"], ft["otb_searches"],
                                  ft["otb_views"], ft["pace_ratio"], ft["cxl_rate_28d"], ft["comp_index"], ft["event_score"], now))
                clamped = d.clamp_status == "clamped" and p.source == "engine"
                status = ("clamped" if clamped else "accepted") if p.source == "engine" else "not_applicable"
                if clamped and p.is_live:
                    n_clamped += 1
                did = new_id("dpd")
                dec_rows.append((did, cycle_id, bd, "room_type", i.entity_id, i.for_date, i.currency, money_str(i.baseline),
                                 money_str(d.raw_price), money_str(d.published), money_str(p.live_before), status,
                                 d.guardrail.clamp_bound if p.source == "engine" else None,
                                 money_str(d.guardrail.bound_value) if (p.source == "engine" and d.guardrail.bound_value is not None) else None,
                                 chain_json(d) if p.source == "engine" else "[]",
                                 money_str(i.daily_anchor), money_str(i.weekly_anchor), factors_json(d, p.source),
                                 forecast_ids.get(p.forecast_key), fid, d.bounds.version, params.version, state.model_version,
                                 p.source, p.approval_status, p.approval_reason, int(p.anomaly), int(p.is_live), now, now))
                sup_keys.append((now, i.entity_id, i.for_date))
                if p.is_live:
                    live_keys.append((i.entity_id, i.for_date))
                    if d.published != p.live_before:
                        inv_rows.append((money_str(d.published), now, i.entity_id, i.for_date))
                    vals = canonical_factor_values(d)
                    hist_rows.append((new_id("phs"), i.entity_id, i.for_date, money_str(d.published), i.currency,
                                      money_str(i.baseline), vals["demand_index"], ft["occupancy_pct"],
                                      vals["lead_time_factor"], vals["seasonality_factor"], vals["event_factor"],
                                      vals["competitor_factor"], int(clamped), explanation(d, p.source), now))
            conn.executemany("INSERT INTO dp_feature (feature_id, entity_type, entity_id, city_id, for_date, as_of_date, "
                             "lead_time_days, occupancy_pct, otb_bookings, otb_cancellations, otb_searches, otb_views, "
                             "pace_ratio, cxl_rate_28d, comp_index, event_score, created_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", feat_rows)
            conn.executemany("UPDATE dp_price_decision SET approval_status = 'superseded', updated_at = ? "
                             "WHERE entity_type = 'room_type' AND entity_id = ? AND for_date = ? "
                             "AND approval_status = 'pending_approval'", sup_keys)
            conn.executemany("UPDATE dp_price_decision SET is_live = 0 WHERE entity_type = 'room_type' AND entity_id = ? "
                             "AND for_date = ? AND is_live = 1", live_keys)
            conn.executemany(
                "INSERT INTO dp_price_decision (decision_id, cycle_id, business_date, entity_type, entity_id, for_date, "
                "currency, baseline_price, raw_price, published_price, live_price_before, clamp_status, clamp_bound, "
                "bound_value, clamp_chain, daily_anchor_price, weekly_anchor_price, factors, forecast_id, feature_id, "
                "bounds_version, engine_config_version, model_version, source, approval_status, approval_reason, "
                "anomaly_flag, is_live, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                dec_rows)
            conn.executemany("UPDATE inventory_calendar SET price = ?, updated_at = ? WHERE entity_type = 'room_type' "
                             "AND entity_id = ? AND for_date = ?", inv_rows)
            conn.executemany(
                "INSERT INTO price_history (history_id, entity_type, entity_id, effective_date, price, currency, baseline_price, "
                "demand_index, occupancy_pct, lead_time_factor, seasonality_factor, event_factor, competitor_factor, "
                "bound_clamped, explanation, computed_at) VALUES (?, 'room_type', ?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(entity_type, entity_id, effective_date) DO UPDATE SET price = excluded.price, "
                "currency = excluded.currency, baseline_price = excluded.baseline_price, demand_index = excluded.demand_index, "
                "occupancy_pct = excluded.occupancy_pct, lead_time_factor = excluded.lead_time_factor, "
                "seasonality_factor = excluded.seasonality_factor, event_factor = excluded.event_factor, "
                "competitor_factor = excluded.competitor_factor, bound_clamped = excluded.bound_clamped, "
                "explanation = excluded.explanation, computed_at = excluded.computed_at", hist_rows)
            pending = sum(1 for p in priced if p.approval_status == "pending_approval")
            summary = {"kind": kind, "business_date": bd, "decisions": len(priced), "live_changes": len(inv_rows),
                       "clamped_live": n_clamped, "pending_approval": pending, "model_version": state.model_version,
                       "engine_config_version": params.version}
            conn.execute("UPDATE dp_cycle SET status = 'completed', n_decisions = ?, n_clamped = ?, finished_at = ?, "
                         "updated_at = ? WHERE cycle_id = ?", (len(priced), n_clamped, wall_now_iso(), wall_now_iso(), cycle_id))
            audit.record(conn, actor, f"cycle_{kind}", f"dp_cycle:{cycle_id}", after=summary, reason=reason)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    return {"cycle_id": cycle_id, **summary}


def _method(m: str) -> str:
    if m.startswith("naive") or m.endswith("trailing_naive"):
        return "trailing_naive"
    if m.startswith("lgbm_poisson"):
        return "lgbm"
    return "pickup_lgbmq" if m.endswith("pickup_lgbmq") else "pickup_conformal"


def run_cycle(conn: sqlite3.Connection, kind: str, business: date | None = None, actor: str = "system",
              reason: str | None = None) -> dict:
    business = business or business_date(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        expire_overrides(conn)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    params = config_service.engine_params(conn)
    priced, ctx = price_all(conn, business, kind, params)
    return publish(conn, business, kind, params, priced, ctx, actor=actor, reason=reason)


def advance_day(conn: sqlite3.Connection, actor: str, reason: str | None = None) -> dict:
    nxt = business_date(conn) + timedelta(days=1)
    conn.execute("BEGIN IMMEDIATE")
    try:
        set_business_date(conn, nxt)
        audit.record(conn, actor, "clock_advance", "dp_clock", after={"business_date": nxt.isoformat()}, reason=reason)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return run_cycle(conn, "advance", nxt, actor=actor, reason=reason)


def warmup_replay(conn: sqlite3.Connection, start: date, end: date) -> dict:
    """Seed real price history: one auto-applied cycle per business day, so daily/weekly anchors are genuine."""
    stats = {"cycles": 0, "decisions": 0, "clamped_last": 0}
    d = start
    while d <= end:
        conn.execute("BEGIN IMMEDIATE")
        set_business_date(conn, d)
        conn.execute("COMMIT")
        out = run_cycle(conn, "warmup", d, actor="seed", reason="warm-up replay")
        stats["cycles"] += 1
        stats["decisions"] += out["decisions"]
        stats["clamped_last"] = out["clamped_live"]
        d += timedelta(days=1)
    return stats


def json_loads(s: str) -> dict:
    return json.loads(s)

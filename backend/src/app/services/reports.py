"""Read models for the Clamp Report, curves and explanations (ARCHITECTURE §8, §11)."""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.core.money import ZERO, dec, money_str, pct
from app.pricing.engine import operating_band, price_one
from app.pricing.guardrails import effective_bounds
from app.pricing.params import params_from_row
from app.pricing.types import Bounds, EventUplift, PriceInputs
from app.services.errors import invalid_id

BOUNDS = ("ceiling", "floor", "max_daily_movement", "max_weekly_movement")


def clamp_summary(conn: sqlite3.Connection, entity_id: str) -> dict:
    """Counts only (no money in SQL). Live, engine-sourced prices: overrides and kill switch are never counted."""
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(clamp_status = 'clamped') AS clamped, "
        "SUM(clamp_bound = 'ceiling') AS ceiling, SUM(clamp_bound = 'floor') AS floor, "
        "SUM(clamp_bound = 'max_daily_movement') AS daily, SUM(clamp_bound = 'max_weekly_movement') AS weekly, "
        "SUM(source <> 'engine') AS controlled, MAX(cycle_id) AS any_cycle "
        "FROM dp_price_decision WHERE entity_type = 'room_type' AND entity_id = ? AND is_live = 1", (entity_id,)).fetchone()
    by = {"ceiling": row["ceiling"] or 0, "floor": row["floor"] or 0, "max_daily_movement": row["daily"] or 0,
          "max_weekly_movement": row["weekly"] or 0}
    total, clamped = row["total"] or 0, row["clamped"] or 0
    parts = [f"{by['ceiling']} by ceiling", f"{by['floor']} by floor", f"{by['max_daily_movement']} by daily-movement"]
    if by["max_weekly_movement"]:
        parts.append(f"{by['max_weekly_movement']} by weekly-movement")
    bd = conn.execute("SELECT business_date FROM dp_clock").fetchone()
    last = conn.execute("SELECT cycle_id, kind, finished_at FROM dp_cycle WHERE status = 'completed' "
                        "ORDER BY finished_at DESC LIMIT 1").fetchone()
    return {"entity_id": entity_id, "total": total, "clamped": clamped, "by_bound": by,
            "controlled": row["controlled"] or 0,
            "headline": f"{clamped} of {total} prices clamped — " + ", ".join(parts),
            "business_date": bd[0] if bd else None, "cycle_id": last["cycle_id"] if last else None}


def curve(conn: sqlite3.Connection, entity_id: str, from_date: str | None = None, to_date: str | None = None) -> dict:
    b = conn.execute("SELECT floor_price, ceiling_price, currency FROM price_bounds WHERE entity_type = 'room_type' "
                     "AND entity_id = ?", (entity_id,)).fetchone()
    if b is None:
        raise invalid_id("room")
    live = conn.execute(
        "SELECT d.decision_id, d.for_date, d.baseline_price, d.raw_price, d.published_price, d.clamp_status, d.clamp_bound, "
        "d.bound_value, d.source, d.approval_status, d.anomaly_flag, d.bounds_version, d.engine_config_version, "
        "f.p10, f.p50, f.p90, f.confidence_band "
        "FROM dp_price_decision d LEFT JOIN dp_forecast f ON f.forecast_id = d.forecast_id "
        "WHERE d.entity_type = 'room_type' AND d.entity_id = ? AND d.is_live = 1 "
        "AND (? IS NULL OR d.for_date >= ?) AND (? IS NULL OR d.for_date <= ?) ORDER BY d.for_date",
        (entity_id, from_date, from_date, to_date, to_date)).fetchall()
    pending = {r["for_date"]: r for r in conn.execute(
        "SELECT decision_id, for_date, published_price, approval_reason FROM dp_price_decision WHERE entity_type = 'room_type' "
        "AND entity_id = ? AND approval_status = 'pending_approval'", (entity_id,))}
    points = []
    params_at, bounds_at = {}, {}
    for r in live:
        p = pending.get(r["for_date"])
        cv, bv = r["engine_config_version"], r["bounds_version"]
        if cv not in params_at:
            params_at[cv] = params_from_row(conn.execute("SELECT * FROM dp_engine_config WHERE version = ?", (cv,)).fetchone())
        if bv not in bounds_at:
            bounds_at[bv] = _bounds_at(conn, entity_id, bv)
        f_used, c_used, _, _ = effective_bounds(bounds_at[bv], operating_band(dec(r["baseline_price"]), params_at[cv]))
        points.append({
            "for_date": r["for_date"], "decision_id": r["decision_id"],
            "baseline": r["baseline_price"], "raw": r["raw_price"], "published": r["published_price"],
            "floor": b["floor_price"], "ceiling": b["ceiling_price"], "currency": b["currency"],
            "floor_used": money_str(f_used), "ceiling_used": money_str(c_used),
            "clamp_status": r["clamp_status"], "clamp_bound": r["clamp_bound"], "bound_value": r["bound_value"],
            "source": r["source"], "approval_status": r["approval_status"], "anomaly": bool(r["anomaly_flag"]),
            "pending": None if p is None else {"decision_id": p["decision_id"], "price": p["published_price"],
                                               "reason": p["approval_reason"]},
            "forecast": None if r["p50"] is None else {"p10": r["p10"], "p50": r["p50"], "p90": r["p90"],
                                                       "band": r["confidence_band"]},
        })
    return {"entity_id": entity_id, "currency": b["currency"], "floor": b["floor_price"], "ceiling": b["ceiling_price"],
            "points": points, "summary": clamp_summary(conn, entity_id)}


def allowed_range(conn: sqlite3.Connection, decisions: list[dict]) -> tuple[Decimal, Decimal]:
    """The range the engine was actually allowed to publish in, across these nights: the hotel's bounds narrowed
    by the operating band around each night's reference rate (D-18). Lowest floor, highest ceiling."""
    lows, highs = [], []
    params_at: dict[int, object] = {}
    for d in decisions:
        cv = d["engine_config_version"]
        if cv not in params_at:
            params_at[cv] = params_from_row(conn.execute("SELECT * FROM dp_engine_config WHERE version = ?", (cv,)).fetchone())
        f_used, c_used, _, _ = effective_bounds(_bounds_at(conn, d["entity_id"], d["bounds_version"]),
                                                operating_band(dec(d["baseline_price"]), params_at[cv]))
        lows.append(f_used)
        highs.append(c_used)
    return min(lows), max(highs)


def _bounds_at(conn: sqlite3.Connection, entity_id: str, version: int) -> Bounds:
    pb = conn.execute("SELECT bound_id FROM price_bounds WHERE entity_type = 'room_type' AND entity_id = ?", (entity_id,)).fetchone()
    v = conn.execute("SELECT * FROM dp_bounds_version WHERE bound_id = ? AND version = ?", (pb["bound_id"], version)).fetchone()
    return Bounds(bound_id=pb["bound_id"], floor=dec(v["floor_price"]), ceiling=dec(v["ceiling_price"]), currency=v["currency"],
                  daily_pct=pct(v["max_daily_move_pct"]), weekly_pct=pct(v["max_weekly_move_pct"]),
                  rounding_step=dec(v["rounding_step"]), override_active=bool(v["override_active"]), version=version)


def replay(conn: sqlite3.Connection, decision: sqlite3.Row | dict):
    """Invariant I4: recompute a stored engine decision from its stored inputs, bounds version and config version."""
    f = json.loads(decision["factors"])
    i = f["inputs"]
    inp = PriceInputs(
        entity_type="room_type", entity_id=decision["entity_id"], for_date=decision["for_date"],
        business_date=decision["business_date"], currency=decision["currency"], baseline=dec(i["baseline"]),
        lead_time_days=int(i["lead_time_days"]), season_index=Decimal(i["season_index"]), demand_ratio=Decimal(i["demand_ratio"]),
        credibility=Decimal(i["credibility"]), pace_ratio=Decimal(i["pace_ratio"]), lead_cdf=Decimal(i["lead_cdf"]),
        events=tuple(EventUplift(e["signal_id"], e["title"], e["impact_tag"], e["confidence_band"]) for e in i["events"]),
        comp_index=Decimal(i["comp_index"]), cxl_ratio=Decimal(i["cxl_ratio"]), rel_width=Decimal(i["rel_width"]),
        daily_anchor=dec(i["daily_anchor"]), weekly_anchor=dec(i["weekly_anchor"]), live_price=dec(i["live_price"]))
    cfg = conn.execute("SELECT * FROM dp_engine_config WHERE version = ?", (decision["engine_config_version"],)).fetchone()
    return price_one(inp, _bounds_at(conn, decision["entity_id"], int(decision["bounds_version"])), params_from_row(dict(cfg)))


def explain(conn: sqlite3.Connection, decision_id: str) -> dict:
    d = conn.execute("SELECT * FROM dp_price_decision WHERE decision_id = ?", (decision_id,)).fetchone()
    if d is None:
        raise invalid_id("decision")
    f = json.loads(d["factors"])
    wf = f.get("waterfall", [])
    total = sum((dec(w["contribution"]) for w in wf), ZERO)
    reconstruction_ok = total == dec(d["published_price"]) - dec(d["baseline_price"])
    replay_ok = None
    if d["source"] == "engine" and not f.get("compact"):
        again = replay(conn, d)
        replay_ok = money_str(again.published) == d["published_price"] and money_str(again.raw_price) == d["raw_price"]
    fc = conn.execute("SELECT * FROM dp_forecast WHERE forecast_id = ?", (d["forecast_id"],)).fetchone() if d["forecast_id"] else None
    hb = _bounds_at(conn, d["entity_id"], d["bounds_version"])
    prm = params_from_row(conn.execute("SELECT * FROM dp_engine_config WHERE version = ?", (d["engine_config_version"],)).fetchone())
    f_used, c_used, _, _ = effective_bounds(hb, operating_band(dec(d["baseline_price"]), prm))
    limits = {"hotel_floor": money_str(hb.floor), "hotel_ceiling": money_str(hb.ceiling),
              "floor_used": money_str(f_used), "ceiling_used": money_str(c_used),
              "band": None if prm.band_below is None else {"below": str(prm.band_below), "above": str(prm.band_above)},
              "max_daily_move_pct": str(hb.daily_pct * 100), "max_weekly_move_pct": str(hb.weekly_pct * 100)}
    ranked = sorted([i for i in f.get("items", []) if "contribution" in i],
                    key=lambda i: -abs(dec(i["contribution"])))
    return {
        "decision_id": d["decision_id"], "entity_id": d["entity_id"], "for_date": d["for_date"],
        "business_date": d["business_date"], "currency": d["currency"],
        "baseline": d["baseline_price"], "raw": d["raw_price"], "published": d["published_price"],
        "live_before": d["live_price_before"], "source": d["source"],
        "clamp": {"status": d["clamp_status"], "bound": d["clamp_bound"], "bound_value": d["bound_value"],
                  "chain": json.loads(d["clamp_chain"])},
        "anchors": {"daily": d["daily_anchor_price"], "weekly": d["weekly_anchor_price"]}, "limits": limits,
        "waterfall": wf, "factors": f.get("items", []), "top_drivers": [i["name"] for i in ranked[:3]],
        "inputs": f.get("inputs", {}),
        "forecast": None if fc is None else {"p10": fc["p10"], "p50": fc["p50"], "p90": fc["p90"], "normal": fc["normal_level"],
                                             "band": fc["confidence_band"], "method": fc["method"], "level": fc["level"],
                                             "credibility": fc["credibility"]},
        "approval": {"status": d["approval_status"], "reason": d["approval_reason"], "decided_by": d["decided_by"],
                     "note": d["decision_note"], "anomaly": bool(d["anomaly_flag"])},
        "versions": {"bounds": d["bounds_version"], "engine_config": d["engine_config_version"], "model": d["model_version"]},
        "reconstruction_ok": reconstruction_ok, "replay_ok": replay_ok,
    }

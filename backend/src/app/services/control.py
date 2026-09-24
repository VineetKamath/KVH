"""Control plane: overrides, approvals, kill switch, bounds and engine-config edits.

Every action is ONE audited transaction; prices then follow through a `reprice` cycle (same business date,
so no day-over-day move is invented). A manual override must itself sit inside [floor, ceiling]: invariant I1
holds for every published price, manual or automatic.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal

from app.core.clock import business_date, parse_at, wall_now, wall_now_iso
from app.core.ids import new_id
from app.core.money import dec, money_str
from app.pricing.params import DEFAULT_OPERATING_BAND
from app.services import audit, config_service
from app.services.cycle import price_all, publish
from app.services.errors import AppError, infeasible, invalid_id


def _tx(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")


def _done(conn: sqlite3.Connection, ok: bool) -> None:
    if conn.in_transaction:
        conn.execute("COMMIT" if ok else "ROLLBACK")


def reprice(conn: sqlite3.Connection, actor: str, reason: str, entities: list[str] | None = None,
            manager_approved: bool = False) -> dict:
    params = config_service.engine_params(conn)
    bd = business_date(conn)
    priced, ctx = price_all(conn, bd, "reprice", params, entities=entities,
                            approved_by=actor if manager_approved else None)
    return publish(conn, bd, "reprice", params, priced, ctx, actor=actor, reason=reason)


def update_bounds(conn: sqlite3.Connection, entity_id: str, changes: dict, actor: str, reason: str) -> dict:
    _tx(conn)
    try:
        b = config_service.update_bounds(conn, "room_type", entity_id, changes, actor, reason)
        _done(conn, True)
    except KeyError:
        _done(conn, False)
        raise invalid_id("room") from None
    except ValueError as e:
        _done(conn, False)
        raise infeasible(str(e)) from None
    except BaseException:
        _done(conn, False)
        raise
    cycle = reprice(conn, actor, f"bounds change: {reason}", entities=[entity_id])
    return {"bounds_version": b.version, "cycle": cycle}


def update_engine(conn: sqlite3.Connection, actor: str, reason: str, factor_bounds: dict | None,
                  auto_band_pct: str | None, band_below_pct: str | None = None, band_above_pct: str | None = None) -> dict:
    extra = None
    if band_below_pct is not None or band_above_pct is not None:
        cur = json.loads(config_service.active_engine_row(conn)["factor_bounds"]).get("operating_band", DEFAULT_OPERATING_BAND)
        below = str((Decimal(100) - Decimal(band_below_pct)) / 100) if band_below_pct is not None else cur["below"]
        above = str((Decimal(100) + Decimal(band_above_pct)) / 100) if band_above_pct is not None else cur["above"]
        extra = {"operating_band": {"below": below, "above": above}}
    _tx(conn)
    try:
        v = config_service.new_engine_version(conn, actor, reason, factor_bounds=factor_bounds, auto_band_pct=auto_band_pct,
                                              extra=extra)
        _done(conn, True)
    except BaseException:
        _done(conn, False)
        raise
    return {"engine_config_version": v, "cycle": reprice(conn, actor, f"engine config v{v}: {reason}")}


def set_kill_switch(conn: sqlite3.Connection, active: bool, actor: str, reason: str) -> dict:
    _tx(conn)
    try:
        v = config_service.new_engine_version(conn, actor, reason, kill_switch=active)
        audit.record(conn, actor, "kill_switch_on" if active else "kill_switch_off", "dp_engine_config",
                     after={"version": v, "kill_switch_active": active}, reason=reason)
        _done(conn, True)
    except BaseException:
        _done(conn, False)
        raise
    return {"engine_config_version": v, "kill_switch_active": active,
            "cycle": reprice(conn, actor, f"kill switch {'on' if active else 'off'}: {reason}",
                             manager_approved=not active)}


def create_override(conn: sqlite3.Connection, entity_id: str, from_date: date, to_date: date, price: Decimal,
                    reason: str, expires_at: str, actor: str) -> dict:
    if to_date < from_date:
        raise infeasible("to_date must not be before from_date")
    if parse_at(expires_at) <= wall_now():
        raise infeasible("expires_at must be in the future")
    if from_date <= business_date(conn):
        raise infeasible("overrides apply to future stay dates only")
    b = config_service.bounds_for(conn, "room_type", entity_id)
    if b is None:
        raise invalid_id("room")
    if not (b.floor <= price <= b.ceiling):
        raise infeasible(f"override price must be within the room's bounds ({money_str(b.floor)} - {money_str(b.ceiling)})")
    oid = new_id("dpo")
    now = wall_now_iso()
    _tx(conn)
    try:
        conn.execute("INSERT INTO dp_override (override_id, entity_type, entity_id, from_date, to_date, price, currency, reason, "
                     "expires_at, created_by, status, created_at, updated_at) VALUES (?, 'room_type', ?,?,?,?,?,?,?,?, 'active', ?, ?)",
                     (oid, entity_id, from_date.isoformat(), to_date.isoformat(), money_str(price), b.currency, reason,
                      expires_at, actor, now, now))
        config_service.set_override_flag(conn, "room_type", entity_id, True)
        audit.record(conn, actor, "override_create", f"dp_override:{oid}",
                     after={"entity_id": entity_id, "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
                            "price": money_str(price), "expires_at": expires_at}, reason=reason)
        _done(conn, True)
    except sqlite3.IntegrityError as e:
        _done(conn, False)
        raise infeasible("override rejected by a data rule (reason must be at least 5 characters)") from e
    except BaseException:
        _done(conn, False)
        raise
    return {"override_id": oid, "cycle": reprice(conn, actor, f"override {oid}", entities=[entity_id])}


def revoke_override(conn: sqlite3.Connection, override_id: str, actor: str, reason: str) -> dict:
    _tx(conn)
    try:
        row = conn.execute("SELECT * FROM dp_override WHERE override_id = ?", (override_id,)).fetchone()
        if row is None:
            raise invalid_id("override")
        if row["status"] != "active":
            raise AppError("idempotency_conflict", "override is not active", 409)
        now = wall_now_iso()
        conn.execute("UPDATE dp_override SET status = 'revoked', updated_at = ? WHERE override_id = ?", (now, override_id))
        still = conn.execute("SELECT 1 FROM dp_override WHERE status = 'active' AND entity_id = ? AND override_id <> ?",
                             (row["entity_id"], override_id)).fetchone()
        if still is None:
            config_service.set_override_flag(conn, "room_type", row["entity_id"], False)
        audit.record(conn, actor, "override_revoke", f"dp_override:{override_id}", before=dict(row), reason=reason)
        _done(conn, True)
    except BaseException:
        _done(conn, False)
        raise
    return {"override_id": override_id, "status": "revoked",
            "cycle": reprice(conn, actor, f"override {override_id} revoked", entities=[row["entity_id"]])}


def decide_approval(conn: sqlite3.Connection, decision_id: str, action: str, note: str, actor: str) -> dict:
    if action not in ("approve", "reject"):
        raise infeasible("action must be approve or reject")
    _tx(conn)
    try:
        d = conn.execute("SELECT * FROM dp_price_decision WHERE decision_id = ?", (decision_id,)).fetchone()
        if d is None:
            raise invalid_id("decision")
        if d["approval_status"] != "pending_approval":
            raise AppError("idempotency_conflict", f"decision is {d['approval_status']}, not pending", 409)
        now = wall_now_iso()
        if action == "reject":
            conn.execute("UPDATE dp_price_decision SET approval_status = 'rejected', decided_by = ?, decision_note = ?, "
                         "updated_at = ? WHERE decision_id = ?", (actor, note, now, decision_id))
        else:
            b = config_service.bounds_for(conn, "room_type", d["entity_id"])
            if b is not None and not (b.floor <= dec(d["published_price"]) <= b.ceiling):
                raise infeasible("bounds changed since this decision; it can no longer be approved")
            conn.execute("UPDATE dp_price_decision SET is_live = 0 WHERE entity_type = 'room_type' AND entity_id = ? "
                         "AND for_date = ? AND is_live = 1", (d["entity_id"], d["for_date"]))
            conn.execute("UPDATE dp_price_decision SET approval_status = 'approved', is_live = 1, decided_by = ?, "
                         "decision_note = ?, updated_at = ? WHERE decision_id = ?", (actor, note, now, decision_id))
            conn.execute("UPDATE inventory_calendar SET price = ?, updated_at = ? WHERE entity_type = 'room_type' "
                         "AND entity_id = ? AND for_date = ?", (d["published_price"], now, d["entity_id"], d["for_date"]))
            _upsert_history(conn, d, now)
        audit.record(conn, actor, f"approval_{action}", f"dp_price_decision:{decision_id}",
                     before={"approval_status": "pending_approval", "price": d["published_price"],
                             "live_before": d["live_price_before"]},
                     after={"approval_status": "approved" if action == "approve" else "rejected"}, reason=note)
        _done(conn, True)
    except BaseException:
        _done(conn, False)
        raise
    return {"decision_id": decision_id, "approval_status": "approved" if action == "approve" else "rejected"}


def _upsert_history(conn: sqlite3.Connection, d: sqlite3.Row, now: str) -> None:
    """Re-derive the canonical price_history row for an approved decision from its stored factors."""
    f = json.loads(d["factors"])
    vals = {i["name"]: Decimal(i["value"]) for i in f["items"]}
    canon = {"demand_index": vals["demand"], "lead_time_factor": vals["lead_time"], "seasonality_factor": vals["seasonality"],
             "event_factor": vals["event"], "competitor_factor": vals["competitor"]}
    occ = conn.execute("SELECT occupancy_pct FROM dp_feature WHERE feature_id = ?", (d["feature_id"],)).fetchone()
    parts = [f"{k} {v.quantize(Decimal('0.01'))}" for k, v in (("demand", vals["demand"]), ("lead", vals["lead_time"]),
             ("season", vals["seasonality"]), ("event", vals["event"]), ("competitor", vals["competitor"]))]
    text = " x ".join(parts) + (f" (clamped to {d['clamp_bound'].replace('_', ' ')} {d['bound_value']})"
                                if d["clamp_status"] == "clamped" else "") + " (approved by revenue manager)"
    conn.execute(
        "INSERT INTO price_history (history_id, entity_type, entity_id, effective_date, price, currency, baseline_price, "
        "demand_index, occupancy_pct, lead_time_factor, seasonality_factor, event_factor, competitor_factor, bound_clamped, "
        "explanation, computed_at) VALUES (?, 'room_type', ?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(entity_type, entity_id, effective_date) DO UPDATE SET price = excluded.price, "
        "demand_index = excluded.demand_index, lead_time_factor = excluded.lead_time_factor, "
        "seasonality_factor = excluded.seasonality_factor, event_factor = excluded.event_factor, "
        "competitor_factor = excluded.competitor_factor, bound_clamped = excluded.bound_clamped, "
        "explanation = excluded.explanation, computed_at = excluded.computed_at",
        (new_id("phs"), d["entity_id"], d["for_date"], d["published_price"], d["currency"], d["baseline_price"],
         str(canon["demand_index"].quantize(Decimal("0.001"))), occ[0] if occ else "0.00",
         str(canon["lead_time_factor"].quantize(Decimal("0.001"))), str(canon["seasonality_factor"].quantize(Decimal("0.001"))),
         str(canon["event_factor"].quantize(Decimal("0.001"))), str(canon["competitor_factor"].quantize(Decimal("0.001"))),
         int(d["clamp_status"] == "clamped"), text, now))


def approve_signal(conn: sqlite3.Connection, signal_id: str, actor: str, note: str) -> dict:
    _tx(conn)
    try:
        row = conn.execute("SELECT * FROM dp_event_signal WHERE signal_id = ?", (signal_id,)).fetchone()
        if row is None:
            raise invalid_id("event signal")
        if row["approved_at"] is not None:
            raise AppError("idempotency_conflict", "signal already approved", 409)
        now = wall_now_iso()
        conn.execute("UPDATE dp_event_signal SET approved_by = ?, approved_at = ?, updated_at = ? WHERE signal_id = ?",
                     (actor, now, now, signal_id))
        audit.record(conn, actor, "event_signal_approve", f"dp_event_signal:{signal_id}",
                     after={"title": row["title"], "city_id": row["city_id"], "impact_tag": row["impact_tag"]}, reason=note)
        _done(conn, True)
    except BaseException:
        _done(conn, False)
        raise
    ents = [r[0] for r in conn.execute("SELECT room_type_id FROM dp_catalog_link WHERE city_id = ?", (row["city_id"],))]
    return {"signal_id": signal_id, "cycle": reprice(conn, actor, f"event signal approved: {row['title']}", entities=ents or None)}


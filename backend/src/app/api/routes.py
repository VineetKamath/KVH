"""HTTP routes (ARCHITECTURE §11). Traveller routes are public and rate-limited; everything else requires the
admin bearer token. Handlers are thin: validate (Pydantic), call a service, return JSON."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response

from app.api.security import require_admin
from app.config import get_settings
from app.contracts import models as M
from app.core.clock import business_date
from app.db.conn import get_conn
from app.services import audit, catalog, control, cycle, quotes, reports, simulator
from app.services.errors import infeasible, invalid_id

public = APIRouter(prefix="/v1")
admin = APIRouter(prefix="/v1", dependencies=[Depends(require_admin)])
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
ROOM_RE = r"^rmt_[0-9a-f]{6,16}$"
DP_RE = r"^dp[a-z]{0,3}_[0-9a-z_]{4,32}$"


def db() -> sqlite3.Connection:
    return get_conn()


# ---------------------------------------------------------------- traveller (public) ----------------------------
@public.get("/health")
def health(conn: sqlite3.Connection = Depends(db)) -> dict:
    bd = conn.execute("SELECT business_date FROM dp_clock").fetchone()
    last = conn.execute("SELECT kind, status, finished_at FROM dp_cycle ORDER BY started_at DESC LIMIT 1").fetchone()
    return {"status": "ok" if bd and last and last["status"] == "completed" else "degraded",
            "business_date": bd[0] if bd else None, "llm": get_settings().llm_provider,
            "last_cycle": dict(last) if last else None}


@public.get("/catalog/cities")
def catalog_cities(conn: sqlite3.Connection = Depends(db)) -> dict:
    bd = business_date(conn)
    last = conn.execute("SELECT MAX(for_date) FROM dp_baseline").fetchone()[0]
    return {"business_date": bd.isoformat(), "bookable_from": (bd + timedelta(days=1)).isoformat(), "bookable_to": last,
            "cities": catalog.cities(conn)}


@public.get("/catalog/cities/{city_id}/rooms")
def catalog_rooms(city_id: str = Path(..., pattern=r"^cty_[0-9a-f]{6,16}$"),
                  conn: sqlite3.Connection = Depends(db)) -> dict:
    return catalog.rooms(conn, city_id)


@public.get("/catalog/rooms/{room_id}")
def catalog_room(room_id: str = Path(..., pattern=ROOM_RE), conn: sqlite3.Connection = Depends(db)) -> dict:
    meta = catalog.room_meta(conn, room_id)
    if meta.get("hotel_name") is None:
        raise invalid_id("room")
    return meta


@public.post("/quote")
def create_quote(req: M.QuoteRequest, conn: sqlite3.Connection = Depends(db)) -> Response:
    body = quotes.get_or_create(conn, req.entity_id, req.checkin_date, req.checkout_date, req.party_size, req.session_id,
                                req.locale)
    return Response(content=body.encode("utf-8"), media_type="application/json")


@public.post("/quote/{quote_id}/confirm")
def confirm_quote(quote_id: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    if not quote_id.startswith("dpq_") or len(quote_id) > 40:
        raise invalid_id("quote")
    return quotes.confirm(conn, quote_id)


# ---------------------------------------------------------------- auth check ------------------------------------
@admin.get("/session")
def session(actor: str = Depends(require_admin)) -> dict:
    return {"actor": actor, "ok": True}


# ---------------------------------------------------------------- reports ---------------------------------------
@admin.get("/entities")
def entities(conn: sqlite3.Connection = Depends(db)) -> dict:
    rows = conn.execute(
        "SELECT l.room_type_id AS entity_id, l.room_name, h.name AS hotel_name, c.name AS city_name, c.city_id, "
        "b.currency FROM dp_catalog_link l JOIN hotels h ON h.hotel_id = l.hotel_id JOIN cities c ON c.city_id = l.city_id "
        "JOIN price_bounds b ON b.entity_id = l.room_type_id ORDER BY c.name, h.name").fetchall()
    return {"entities": [dict(r) for r in rows]}


@admin.get("/prices/curve")
def price_curve(entity_id: str = Query(..., pattern=ROOM_RE), from_date: str | None = Query(None, pattern=DATE_RE),
                to_date: str | None = Query(None, pattern=DATE_RE), conn: sqlite3.Connection = Depends(db)) -> dict:
    return {**reports.curve(conn, entity_id, from_date, to_date), "room": catalog.room_meta(conn, entity_id)}


@admin.get("/clamps/summary")
def clamp_summary(entity_id: str = Query(..., pattern=ROOM_RE), conn: sqlite3.Connection = Depends(db)) -> dict:
    return reports.clamp_summary(conn, entity_id)


@admin.get("/decisions/{decision_id}/explain")
def explain(decision_id: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    if not decision_id.startswith("dpd_") or len(decision_id) > 40:
        raise invalid_id("decision")
    return reports.explain(conn, decision_id)


@admin.get("/forecast")
def forecast(entity_id: str = Query(..., pattern=ROOM_RE), conn: sqlite3.Connection = Depends(db)) -> dict:
    rows = conn.execute(
        "SELECT d.for_date, f.p10, f.p50, f.p90, f.normal_level, f.credibility, f.confidence_band, f.level, f.level_key, "
        "f.method, f.as_of_date FROM dp_price_decision d JOIN dp_forecast f ON f.forecast_id = d.forecast_id "
        "WHERE d.entity_id = ? AND d.is_live = 1 ORDER BY d.for_date", (entity_id,)).fetchall()
    city = conn.execute("SELECT city_id FROM dp_catalog_link WHERE room_type_id = ?", (entity_id,)).fetchone()
    actuals = []
    if city:
        actuals = [dict(r) for r in conn.execute(
            "SELECT for_date, SUM(event_type = 'booking') AS bookings FROM pricing_events WHERE city_id = ? "
            "AND for_date >= date(?, '-60 day') AND for_date <= ? GROUP BY for_date ORDER BY for_date",
            (city[0], business_date(conn).isoformat(), business_date(conn).isoformat()))]
    sel = conn.execute("SELECT * FROM dp_model_selection ORDER BY created_at DESC LIMIT 2").fetchall()
    return {"entity_id": entity_id, "series": [dict(r) for r in rows], "actuals_city_daily": actuals,
            "selection": [{**{k: r[k] for k in ("component", "champion", "challenger", "decision", "dm_p_value", "as_of_date")},
                           "scores": json.loads(r["scores"])} for r in sel]}


# ---------------------------------------------------------------- controls --------------------------------------
@admin.get("/bounds/{entity_id}")
def get_bounds(entity_id: str = Path(..., pattern=ROOM_RE), conn: sqlite3.Connection = Depends(db)) -> dict:
    row = conn.execute("SELECT * FROM price_bounds WHERE entity_type = 'room_type' AND entity_id = ?", (entity_id,)).fetchone()
    if row is None:
        raise invalid_id("room")
    versions = conn.execute("SELECT version, floor_price, ceiling_price, max_daily_move_pct, max_weekly_move_pct, rounding_step, "
                            "actor, reason, created_at FROM dp_bounds_version WHERE bound_id = ? ORDER BY version DESC",
                            (row["bound_id"],)).fetchall()
    return {"bounds": {k: str(row[k]) for k in row.keys()}, "versions": [{k: str(v[k]) for k in v.keys()} for v in versions]}


@admin.put("/bounds/{entity_id}")
def put_bounds(req: M.BoundsUpdate, entity_id: str = Path(..., pattern=ROOM_RE), actor: str = Depends(require_admin),
               conn: sqlite3.Connection = Depends(db)) -> dict:
    changes = {k: v for k, v in req.model_dump(exclude={"reason"}).items() if v is not None}
    if not changes:
        raise infeasible("no bound fields to change")
    return control.update_bounds(conn, entity_id, changes, actor, req.reason)


@admin.get("/engine-config")
def get_engine(conn: sqlite3.Connection = Depends(db)) -> dict:
    from app.services.config_service import active_engine_row

    r = active_engine_row(conn)
    return {"version": r["version"], "auto_band_pct": r["auto_band_pct"], "kill_switch_active": bool(r["kill_switch_active"]),
            "config": json.loads(r["factor_bounds"]), "actor": r["actor"], "reason": r["reason"],
            "effective_from_at": r["effective_from_at"]}


@admin.put("/engine-config")
def put_engine(req: M.EngineUpdate, actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    fb = {k: v.model_dump() for k, v in (req.factor_bounds or {}).items()}
    return control.update_engine(conn, actor, req.reason, fb or None, req.auto_band_pct)


@admin.post("/killswitch")
def killswitch(req: M.KillSwitch, actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    return control.set_kill_switch(conn, req.active, actor, req.reason)


@admin.get("/overrides")
def list_overrides(conn: sqlite3.Connection = Depends(db)) -> dict:
    return {"overrides": [dict(r) for r in conn.execute("SELECT * FROM dp_override ORDER BY created_at DESC LIMIT 200")]}


@admin.post("/overrides")
def create_override(req: M.OverrideCreate, actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    return control.create_override(conn, req.entity_id, req.from_date, req.to_date, Decimal(req.price), req.reason,
                                   req.expires_at, actor)


@admin.post("/overrides/{override_id}/revoke")
def revoke_override(override_id: str, req: M.ReasonOnly, actor: str = Depends(require_admin),
                    conn: sqlite3.Connection = Depends(db)) -> dict:
    if not override_id.startswith("dpo_"):
        raise invalid_id("override")
    return control.revoke_override(conn, override_id, actor, req.reason)


@admin.get("/approvals")
def approvals(conn: sqlite3.Connection = Depends(db)) -> dict:
    rows = conn.execute(
        "SELECT d.decision_id, d.entity_id, d.for_date, d.business_date, d.live_price_before, d.published_price, d.currency, "
        "d.approval_reason, d.anomaly_flag, d.clamp_bound, l.room_name, h.name AS hotel_name FROM dp_price_decision d "
        "LEFT JOIN dp_catalog_link l ON l.room_type_id = d.entity_id LEFT JOIN hotels h ON h.hotel_id = l.hotel_id "
        "WHERE d.approval_status = 'pending_approval' ORDER BY d.anomaly_flag DESC, d.for_date LIMIT 300").fetchall()
    from app.ai.anomaly_summary import summary_for

    return {"pending": [{**dict(r), "summary": summary_for(dict(r))} for r in rows]}


@admin.post("/approvals/{decision_id}")
def decide(decision_id: str, req: M.ApprovalDecision, actor: str = Depends(require_admin),
           conn: sqlite3.Connection = Depends(db)) -> dict:
    return control.decide_approval(conn, decision_id, req.action, req.note, actor)


@admin.get("/clock")
def clock(conn: sqlite3.Connection = Depends(db)) -> dict:
    return {"business_date": business_date(conn).isoformat()}


@admin.post("/clock/advance")
def advance(req: M.ReasonOnly, actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    last = conn.execute("SELECT MAX(for_date) FROM dp_baseline").fetchone()[0]
    if business_date(conn) + timedelta(days=2) > date.fromisoformat(last):
        raise infeasible("the business clock has reached the end of the priced calendar")
    return cycle.advance_day(conn, actor, req.reason)


@admin.get("/cycles/latest")
def latest_cycle(conn: sqlite3.Connection = Depends(db)) -> dict:
    r = conn.execute("SELECT cycle_id, kind, business_date, n_decisions, n_clamped, status, finished_at FROM dp_cycle "
                     "ORDER BY started_at DESC LIMIT 1").fetchone()
    return dict(r) if r else {}


@admin.get("/event-signals")
def event_signals(conn: sqlite3.Connection = Depends(db)) -> dict:
    rows = conn.execute("SELECT s.*, c.name AS city_name FROM dp_event_signal s JOIN cities c ON c.city_id = s.city_id "
                        "ORDER BY s.approved_at IS NOT NULL, s.start_date").fetchall()
    return {"signals": [dict(r) for r in rows]}


@admin.post("/event-signals/{signal_id}/approve")
def approve_signal(signal_id: str, req: M.ReasonOnly, actor: str = Depends(require_admin),
                   conn: sqlite3.Connection = Depends(db)) -> dict:
    if not signal_id.startswith("dps_"):
        raise invalid_id("event signal")
    return control.approve_signal(conn, signal_id, actor, req.reason)


@admin.post("/event-signals/extract")
def extract_signals(actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    from app.ai.event_extractor.extractor import extract_pending

    return extract_pending(conn, actor)


@admin.post("/events")
def ingest(req: M.EventBatch, actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    from app.services.ingest import ingest_batch

    return ingest_batch(conn, req.events, actor)


# ---------------------------------------------------------------- simulation ------------------------------------
@admin.post("/whatif/parse")
def whatif_parse(req: M.WhatIfPrompt, actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    from app.ai.whatif.parser import parse

    return parse(req.prompt, business_date(conn))


@admin.post("/simulate")
def simulate(req: M.SimulateRequest, actor: str = Depends(require_admin), conn: sqlite3.Connection = Depends(db)) -> dict:
    return simulator.simulate(conn, req.entity_id, req.config, req.name, req.prompt_text, actor)


@admin.get("/experiments")
def experiments(conn: sqlite3.Connection = Depends(db)) -> dict:
    rows = conn.execute("SELECT experiment_id, name, kind, prompt_text, metrics, window_from_date, window_to_date, created_at "
                        "FROM dp_experiment ORDER BY created_at DESC LIMIT 50").fetchall()
    return {"experiments": [{**dict(r), "metrics": json.loads(r["metrics"]) if r["metrics"] else None} for r in rows]}


# ---------------------------------------------------------------- evidence --------------------------------------
@admin.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=500), conn: sqlite3.Connection = Depends(db)) -> dict:
    rows = conn.execute("SELECT audit_id, seq, actor, action, target, reason, created_at, row_hash FROM dp_audit_log "
                        "ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
    return {"entries": [dict(r) for r in rows]}


@admin.get("/audit/verify")
def audit_verify(conn: sqlite3.Connection = Depends(db)) -> dict:
    return audit.verify(conn)


@admin.get("/metrics")
def metrics(conn: sqlite3.Connection = Depends(db)) -> dict:
    from app.services.metrics import metrics_payload

    return metrics_payload(conn)


@admin.get("/proof")
def proof(conn: sqlite3.Connection = Depends(db)) -> dict:
    from app.services.proof import run_proof

    return run_proof(conn)


@admin.post("/narrate/{decision_id}")
def narrate(decision_id: str, locale: M.LOCALE = Query("en-IN"), actor: str = Depends(require_admin),
            conn: sqlite3.Connection = Depends(db)) -> dict:
    from app.ai.narrator.narrator import narrate_decision

    if not decision_id.startswith("dpd_"):
        raise invalid_id("decision")
    return narrate_decision(conn, decision_id, locale, force=True)


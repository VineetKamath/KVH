"""POST /v1/events → pricing_events (append-only, validated, idempotent on a client event_id).

Events are stamped on the business clock (docs/DECISIONS.md D-09): today's activity feeds tomorrow's cycle.
lead_time_days is computed server-side (for_date − business date), never taken from the client.
"""
from __future__ import annotations

import sqlite3

from app.core.clock import business_date, wall_now_iso
from app.core.ids import new_id
from app.services import audit


def ingest_batch(conn: sqlite3.Connection, events: list, actor: str) -> dict:
    today = business_date(conn)
    accepted, rejected = [], []
    conn.execute("BEGIN IMMEDIATE")
    try:
        for i, ev in enumerate(events):
            city = conn.execute("SELECT MIN(city_id) FROM pricing_events WHERE entity_id = ?", (ev.entity_id,)).fetchone()[0]
            if city is None:
                row = conn.execute("SELECT city_id FROM dp_catalog_link WHERE room_type_id = ?", (ev.entity_id,)).fetchone()
                city = row[0] if row else None
            if city is None:
                rejected.append({"index": i, "error_code": "invalid_id", "message": "unknown room or room without a city"})
                continue
            if ev.event_id and conn.execute("SELECT 1 FROM pricing_events WHERE event_id = ?", (ev.event_id,)).fetchone():
                rejected.append({"index": i, "error_code": "idempotency_conflict", "message": "event_id already ingested"})
                continue
            lead = (ev.for_date - today).days
            if lead < 0 and ev.event_type in ("search", "view", "booking"):
                rejected.append({"index": i, "error_code": "constraint_infeasible", "message": "stay date is in the past"})
                continue
            event_id = ev.event_id or new_id("pev")
            conn.execute(
                "INSERT INTO pricing_events (event_id, entity_type, entity_id, city_id, event_type, occurred_at, for_date, "
                "lead_time_days, channel, party_size, quoted_price, currency, converted, session_id) "
                "VALUES (?, 'room_type', ?,?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, ev.entity_id, city, ev.event_type, f"{today.isoformat()}T{wall_now_iso()[11:]}",
                 ev.for_date.isoformat(), lead, ev.channel, ev.party_size, ev.quoted_price,
                 "INR" if ev.quoted_price else None, int(ev.event_type == "booking"), ev.session_id))
            accepted.append(event_id)
        audit.record(conn, actor, "events_ingest", "pricing_events", after={"accepted": len(accepted), "rejected": len(rejected)})
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"accepted": len(accepted), "event_ids": accepted, "rejected": rejected,
            "note": "events count toward the forecast from the next business day"}

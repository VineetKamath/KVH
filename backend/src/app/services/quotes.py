"""Traveller quotes (ARCHITECTURE §9.1): stable, bounded, explained, and never waiting on an LLM.

Stability is a DATABASE guarantee: a partial unique index on dp_quote(key_hash) WHERE status='active' lets
exactly one quote exist per search key; concurrent identical searches converge on it. The exact response
body is stored per locale, so a repeat search returns it byte for byte. A live quote is honoured until it
expires, whatever happens to rules or prices in the meantime (the trust promise).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta

from app.config import get_settings
from app.core.clock import business_date, iso_in, wall_now_iso
from app.core.ids import new_id
from app.core.money import ZERO, dec, money_str
from app.services import narration
from app.services.errors import AppError, infeasible, invalid_id

MAX_NIGHTS = 14


def search_key(session_id: str, entity_id: str, checkin: date, checkout: date, party: int) -> str:
    raw = f"{session_id}|room_type|{entity_id}|{checkin.isoformat()}|{checkout.isoformat()}|{party}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _expire_if_stale(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Lazy expiry (no deletes, R8). Returns True if the quote was expired now."""
    if row["status"] != "active" or row["expires_at"] > wall_now_iso():
        return False
    now = wall_now_iso()
    conn.execute("UPDATE dp_quote SET status = 'expired', updated_at = ? WHERE quote_id = ? AND status = 'active'",
                 (now, row["quote_id"]))
    for n in json.loads(row["nightly"]):
        conn.execute("UPDATE inventory_calendar SET held_units = held_units - 1, updated_at = ? WHERE entity_type = 'room_type' "
                     "AND entity_id = ? AND for_date = ? AND held_units > 0", (now, row["entity_id"], n["for_date"]))
    return True


def expire_stale(conn: sqlite3.Connection) -> int:
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute("SELECT * FROM dp_quote WHERE status = 'active' AND expires_at <= ?", (wall_now_iso(),)).fetchall()
        n = sum(_expire_if_stale(conn, r) for r in rows)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return n


def _reasons(conn: sqlite3.Connection, decisions: list[dict], locale: str, floor, ceiling, symbol: str) -> tuple[list[str], str]:
    first = decisions[0]["decision_id"]
    llm = narration.cached(conn, first, locale) if len(decisions) == 1 else None
    if llm:
        return llm, "llm"
    return narration.render_template(narration.facts(decisions), locale, floor, ceiling, symbol), "template"


def _body(quote: dict, reasons: list[str], reason_source: str, locale: str) -> dict:
    return {"quote_id": quote["quote_id"], "status": quote["status"], "entity_type": "room_type",
            "entity_id": quote["entity_id"], "checkin_date": quote["checkin_date"], "checkout_date": quote["checkout_date"],
            "party_size": quote["party_size"], "nightly": quote["nightly"],
            "total": {"amount": quote["total_price"], "currency": quote["currency"]},
            "expires_at": quote["expires_at"], "locale": locale,
            "reasons": [{"text": r, "locale": locale, "source": reason_source} for r in reasons],
            "confidence_band": quote["confidence_band"], "warnings": quote["warnings"]}


def _canonical(body: dict) -> str:
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def get_or_create(conn: sqlite3.Connection, entity_id: str, checkin: date, checkout: date, party: int,
                  session_id: str, locale: str) -> str:
    """Returns the exact JSON body (string) for this search. Byte-identical on repeat within the hold."""
    nights = (checkout - checkin).days
    if nights < 1 or nights > MAX_NIGHTS:
        raise infeasible(f"stay must be 1-{MAX_NIGHTS} nights")
    today = business_date(conn)
    if checkin <= today:
        raise infeasible("check-in must be after the current business date")
    key = search_key(session_id, entity_id, checkin, checkout, party)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM dp_quote WHERE key_hash = ? AND status = 'active'", (key,)).fetchone()
        if row is not None and _expire_if_stale(conn, row):
            row = None
        if row is not None:
            stored = json.loads(row["response_json"])
            if locale not in stored:  # same quote, same prices; reasons frozen per locale on first view
                base = json.loads(stored[next(iter(stored))])
                decisions = [dict(r) for r in conn.execute(
                    "SELECT * FROM dp_price_decision WHERE decision_id IN (SELECT value FROM json_each(?))",
                    (json.dumps([n["decision_id"] for n in base["nightly"]]),))]
                decisions.sort(key=lambda d: d["for_date"])
                meta = _meta(conn, entity_id)
                reasons, src = _reasons(conn, decisions, locale, meta["floor"], meta["ceiling"], meta["symbol"])
                base.update({"locale": locale, "reasons": [{"text": r, "locale": locale, "source": src} for r in reasons]})
                stored[locale] = _canonical(base)
                conn.execute("UPDATE dp_quote SET response_json = ?, updated_at = ? WHERE quote_id = ?",
                             (json.dumps(stored, ensure_ascii=False), wall_now_iso(), row["quote_id"]))
            conn.execute("COMMIT")
            return stored[locale]
        body = _create(conn, key, entity_id, checkin, checkout, party, session_id, locale, today)
        conn.execute("COMMIT")
        return body
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _meta(conn: sqlite3.Connection, entity_id: str) -> dict:
    b = conn.execute("SELECT floor_price, ceiling_price, currency FROM price_bounds WHERE entity_type = 'room_type' "
                     "AND entity_id = ?", (entity_id,)).fetchone()
    if b is None:
        raise invalid_id("room")
    sym = conn.execute("SELECT symbol FROM currencies WHERE iso4217 = ?", (b["currency"],)).fetchone()
    return {"floor": dec(b["floor_price"]), "ceiling": dec(b["ceiling_price"]), "currency": b["currency"],
            "symbol": sym["symbol"] if sym else ""}


def _create(conn, key, entity_id, checkin, checkout, party, session_id, locale, today) -> str:
    meta = _meta(conn, entity_id)
    days = [(checkin + timedelta(days=i)).isoformat() for i in range((checkout - checkin).days)]
    inv = {r["for_date"]: r for r in conn.execute(
        "SELECT * FROM inventory_calendar WHERE entity_type = 'room_type' AND entity_id = ? "
        "AND for_date IN (SELECT value FROM json_each(?))", (entity_id, json.dumps(days)))}
    if len(inv) != len(days):
        raise infeasible("dates outside the priced calendar")
    first = inv[days[0]]
    if first["closed_to_arrival"]:
        raise infeasible("the hotel is closed to arrival on the check-in date")
    if len(days) < int(first["min_stay_nights"]):
        raise infeasible(f"minimum stay from this date is {first['min_stay_nights']} nights")
    for d in days:
        r = inv[d]
        if r["booked_units"] + r["held_units"] >= r["total_units"]:
            raise AppError("sold_out", f"no rooms left on {d}", 409)
        if r["currency"] != meta["currency"]:
            raise AppError("currency_mismatch", "calendar and bounds currencies differ", 409)
    decisions = [dict(r) for r in conn.execute(
        "SELECT * FROM dp_price_decision WHERE entity_type = 'room_type' AND entity_id = ? AND is_live = 1 "
        "AND for_date IN (SELECT value FROM json_each(?)) ORDER BY for_date", (entity_id, json.dumps(days)))]
    if len(decisions) != len(days):
        raise infeasible("no published price for one or more nights")
    total = sum((dec(d["published_price"]) for d in decisions), ZERO)
    forecast_bands = [r[0] for r in conn.execute(
        "SELECT confidence_band FROM dp_forecast WHERE forecast_id IN (SELECT value FROM json_each(?))",
        (json.dumps([d["forecast_id"] for d in decisions if d["forecast_id"]]),)) if r[0]]
    band = "low" if "low" in forecast_bands else ("medium" if "medium" in forecast_bands else "high")
    warnings = ["low_confidence"] if band == "low" else []
    quote_id = new_id("dpq")
    now = wall_now_iso()
    expires = iso_in(get_settings().quote_ttl_seconds)
    nightly = [{"for_date": d["for_date"], "price": {"amount": money_str(dec(d["published_price"])), "currency": d["currency"]},
                "decision_id": d["decision_id"]} for d in decisions]
    reasons, src = _reasons(conn, decisions, locale, meta["floor"], meta["ceiling"], meta["symbol"])
    quote = {"quote_id": quote_id, "status": "active", "entity_id": entity_id, "checkin_date": days[0],
             "checkout_date": checkout.isoformat(), "party_size": party, "nightly": nightly, "total_price": money_str(total),
             "currency": meta["currency"], "expires_at": expires, "confidence_band": band, "warnings": warnings}
    body = _canonical(_body(quote, reasons, src, locale))
    bounds_versions = {d["decision_id"]: d["bounds_version"] for d in decisions}
    conn.execute(
        "INSERT INTO dp_quote (quote_id, key_hash, session_id, entity_type, entity_id, checkin_date, checkout_date, party_size, "
        "nightly, total_price, currency, locale, response_json, engine_config_version, bounds_versions, business_date, status, "
        "expires_at, created_at, updated_at) VALUES (?,?,?, 'room_type', ?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?,?,?) "
        "ON CONFLICT DO NOTHING",
        (quote_id, key, session_id, entity_id, days[0], checkout.isoformat(), party,
         json.dumps([{"for_date": n["for_date"], "price": n["price"]["amount"], "decision_id": n["decision_id"]} for n in nightly]),
         money_str(total), meta["currency"], locale, json.dumps({locale: body}, ensure_ascii=False),
         int(decisions[0]["engine_config_version"]), json.dumps(bounds_versions), today.isoformat(), expires, now, now))
    for d in days:  # hold one unit per night; the canonical CHECK (booked + held <= total) guards oversell
        try:
            conn.execute("UPDATE inventory_calendar SET held_units = held_units + 1, updated_at = ? WHERE entity_type = 'room_type' "
                         "AND entity_id = ? AND for_date = ?", (now, entity_id, d))
        except sqlite3.IntegrityError:
            raise AppError("sold_out", f"no rooms left on {d}", 409) from None
    _append_event(conn, "search", entity_id, days[0], party, decisions[0]["published_price"], meta["currency"], session_id,
                  converted=0, today=today)
    return body


def _append_event(conn, event_type, entity_id, for_date, party, price, currency, session_id, converted, today) -> str:
    """pricing_events rows are stamped on the BUSINESS clock (the simulation's 'now'; docs/DECISIONS.md D-09),
    with the wall time of day, so today's activity feeds tomorrow's cycle."""
    city = conn.execute("SELECT MIN(city_id) FROM pricing_events WHERE entity_id = ?", (entity_id,)).fetchone()[0]
    if city is None:
        city = conn.execute("SELECT city_id FROM dp_catalog_link WHERE room_type_id = ?", (entity_id,)).fetchone()
        city = city[0] if city else None
    if city is None:
        return ""
    event_id = new_id("pev")
    occurred = f"{today.isoformat()}T{wall_now_iso()[11:]}"
    lead = (date.fromisoformat(for_date) - today).days
    conn.execute(
        "INSERT INTO pricing_events (event_id, entity_type, entity_id, city_id, event_type, occurred_at, for_date, "
        "lead_time_days, channel, party_size, quoted_price, currency, converted, session_id) "
        "VALUES (?, 'room_type', ?,?,?,?,?,?, 'web', ?,?,?,?,?)",
        (event_id, entity_id, city, event_type, occurred, for_date, lead, party, money_str(dec(price)), currency, converted,
         session_id))
    return event_id


def confirm(conn: sqlite3.Connection, quote_id: str) -> dict:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM dp_quote WHERE quote_id = ?", (quote_id,)).fetchone()
        if row is None:
            raise invalid_id("quote")
        if row["status"] == "confirmed":
            conn.execute("COMMIT")
            return {"quote_id": quote_id, "status": "confirmed", "idempotent_replay": True}
        if _expire_if_stale(conn, row) or row["status"] != "active":
            conn.execute("COMMIT")  # keep the lazy expiry (holds released) even though we refuse the confirm
            raise AppError("hold_expired", "this price hold has expired; please search again", 410)
        now = wall_now_iso()
        for n in json.loads(row["nightly"]):
            conn.execute("UPDATE inventory_calendar SET held_units = held_units - 1, booked_units = booked_units + 1, "
                         "updated_at = ? WHERE entity_type = 'room_type' AND entity_id = ? AND for_date = ?",
                         (now, row["entity_id"], n["for_date"]))
        conn.execute("UPDATE dp_quote SET status = 'confirmed', updated_at = ? WHERE quote_id = ?", (now, quote_id))
        first = json.loads(row["nightly"])[0]
        event_id = _append_event(conn, "booking", row["entity_id"], row["checkin_date"], row["party_size"], first["price"],
                                 row["currency"], row["session_id"], converted=1, today=business_date(conn))
        conn.execute("COMMIT")
        return {"quote_id": quote_id, "status": "confirmed", "event_id": event_id}
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise

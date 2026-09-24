"""Time. Two clocks, never mixed (rule R4 + ARCHITECTURE F1/F12).

* The **business clock** (`dp_clock.business_date`) drives every pricing and forecasting calculation.
  The organiser data ends on 2026-08-30 and the forward calendar starts 2026-09-01, so pricing runs
  on a simulated business date, not on today's date.
* The **wall clock** is used only for `_at` audit stamps and the quote-hold TTL.

`pricing/`, `forecast/` and `features/` never import this module's wall-clock functions; a test enforces it.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
CLOCK_ID = "dpck_main"


def wall_now() -> datetime:
    return datetime.now(IST)


def wall_now_iso() -> str:
    """The ONLY producer of `_at` strings: ISO-8601 with an explicit +05:30 offset (passes the validator)."""
    return wall_now().isoformat(timespec="seconds")


def iso_in(seconds: int) -> str:
    return (wall_now() + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def parse_at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def business_date(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT business_date FROM dp_clock WHERE clock_id = ?", (CLOCK_ID,)).fetchone()
    if row is None:
        raise RuntimeError("business clock not initialised; run `python -m scripts.seed`")
    return date.fromisoformat(row[0])


def set_business_date(conn: sqlite3.Connection, value: date) -> None:
    conn.execute(
        "INSERT INTO dp_clock (clock_id, business_date, status, updated_at) VALUES (?, ?, 'active', ?) "
        "ON CONFLICT(clock_id) DO UPDATE SET business_date = excluded.business_date, updated_at = excluded.updated_at",
        (CLOCK_ID, value.isoformat(), wall_now_iso()),
    )

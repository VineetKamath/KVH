"""Loading canonical data into the shapes the pure modules take. All SQL is parameterized."""
from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd


def load_events(conn: sqlite3.Connection) -> pd.DataFrame:
    """pricing_events joined to its city's region. `occurred_at` carries a +05:30 offset (R4), so its
    first 10 characters are the local calendar date."""
    df = pd.read_sql_query(
        "SELECT e.event_type, e.city_id, c.region, e.entity_id, substr(e.occurred_at, 1, 10) AS occurred_date, "
        "e.for_date, e.lead_time_days FROM pricing_events e JOIN cities c ON c.city_id = e.city_id "
        "WHERE e.entity_type = 'room_type'", conn)
    df["occurred_date"] = df["occurred_date"].map(date.fromisoformat)
    df["for_date"] = df["for_date"].map(date.fromisoformat)
    return df


def entity_city_map(conn: sqlite3.Connection) -> dict[str, str]:
    """room_type → city, as resolvable from the organiser data (only via pricing_events.city_id)."""
    return {r[0]: r[1] for r in conn.execute(
        "SELECT entity_id, MIN(city_id) FROM pricing_events WHERE entity_type = 'room_type' GROUP BY entity_id")}


def priced_entities(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT entity_id FROM dp_baseline WHERE entity_type = 'room_type' ORDER BY entity_id")]

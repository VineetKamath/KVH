"""Tier-2 conformance checker (ARCHITECTURE F11). The organisers' validator only checks Tier-1 tables; this
applies the SAME rules (its own regexes, enums.json, money/currency pairing, id prefixes, FKs) to the Tier-2
tables we write: pricing_events, price_bounds, price_history."""
from __future__ import annotations

import json
import re
import sqlite3

from app.config import ENUMS_JSON

ISO_AT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})$")  # validator's regex
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONEY = re.compile(r"^-?\d{1,10}\.\d{2}$")
CCY = re.compile(r"^[A-Z]{3}$")

TABLE_SQL = {"pricing_events": "SELECT * FROM pricing_events", "price_bounds": "SELECT * FROM price_bounds",
             "price_history": "SELECT * FROM price_history"}
CITY_IDS_SQL = "SELECT city_id FROM cities"

SPEC = {
    "pricing_events": {"pk": ("event_id", "pev"), "at": ["occurred_at"], "date": ["for_date"], "money": ["quoted_price"],
                       "enum": {"entity_type": "inventory_entity_type", "event_type": "pricing_event_type", "channel": "channel"},
                       "fk": {"city_id": ("cities", "city_id")}},
    "price_bounds": {"pk": ("bound_id", "pbd"), "at": ["updated_at"], "date": [],
                     "money": ["floor_price", "ceiling_price", "rounding_step"],
                     "enum": {"entity_type": "inventory_entity_type"}, "fk": {}},
    "price_history": {"pk": ("history_id", "phs"), "at": ["computed_at"], "date": ["effective_date"],
                      "money": ["price", "baseline_price"], "enum": {"entity_type": "inventory_entity_type"}, "fk": {}},
}


def check(conn: sqlite3.Connection, max_findings: int = 20) -> dict:
    enums = json.loads(ENUMS_JSON.read_text(encoding="utf-8"))["enums"]
    findings: list[str] = []
    counts = {}
    for table, spec in SPEC.items():
        rows = conn.execute(TABLE_SQL[table]).fetchall()
        counts[table] = len(rows)
        fk_ok = {col: {r[0] for r in conn.execute(CITY_IDS_SQL)} for col in spec["fk"]}
        pk, prefix = spec["pk"]
        for r in rows:
            if len(findings) >= max_findings:
                break
            if not str(r[pk]).startswith(prefix + "_"):
                findings.append(f"{table}.{pk} {r[pk]!r} lacks prefix {prefix}_")
            for c in spec["at"]:
                if r[c] is not None and not ISO_AT.match(str(r[c])):
                    findings.append(f"{table}.{c} {r[c]!r} is not ISO-8601 with offset")
            for c in spec["date"]:
                if r[c] is not None and not ISO_DATE.match(str(r[c])):
                    findings.append(f"{table}.{c} {r[c]!r} is not a zoneless date")
            for c in spec["money"]:
                if r[c] is not None and not MONEY.match(str(r[c])):
                    findings.append(f"{table}.{c} {r[c]!r} is not a 2-place decimal")
                if r[c] is not None and ("currency" not in r.keys() or not CCY.match(str(r["currency"] or ""))):
                    findings.append(f"{table}.{c} has no ISO-4217 currency beside it")
            for c, enum in spec["enum"].items():
                if r[c] not in enums[enum]:
                    findings.append(f"{table}.{c} {r[c]!r} not in enums.{enum}")
            for c, allowed in fk_ok.items():
                if r[c] not in allowed:
                    findings.append(f"{table}.{c} {r[c]!r} does not resolve")
    return {"ok": not findings, "rows": counts, "findings": findings}

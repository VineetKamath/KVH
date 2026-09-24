"""A3 event & festival signal extractor. Reads the curated feed (every row carries a source_ref), classifies
impact / radius / confidence with a one-line justification, and writes UNAPPROVED dp_event_signal rows.
An unapproved signal has zero effect on price by construction (only approved rows reach the engine).

Live: Claude (structured output, enum-constrained). Offline: transparent keyword + attendance rules.
"""
from __future__ import annotations

import csv
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.llm import provider
from app.config import SEED_DIR
from app.core.clock import wall_now_iso
from app.core.ids import new_id
from app.services import audit


class Classification(BaseModel):
    impact_tag: Literal["minor", "moderate", "major"]
    radius_km: int = Field(ge=1, le=200)
    confidence_band: Literal["high", "medium", "low"]
    justification: str = Field(max_length=240)


def feed_rows() -> list[dict]:
    with (SEED_DIR / "event_feed.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def rules(row: dict) -> Classification:
    """Offline classifier: attendance thresholds + source quality. Stated rules, not a model."""
    att = int(row["expected_attendance"])
    impact = "major" if att >= 100_000 else ("moderate" if att >= 15_000 else "minor")
    src = row["source_ref"].lower()
    uncertain = "confirm" in src or "approximate" in src
    official = "government" in src or "gazetted" in src
    conf = "low" if uncertain else ("high" if official else "medium")
    radius = 50 if impact == "major" else (25 if impact == "moderate" else 5)
    return Classification(impact_tag=impact, radius_km=radius, confidence_band=conf,
                          justification=f"Expected attendance {att:,} per '{row['source_ref']}'.")


def classify(row: dict) -> tuple[Classification, str]:
    if provider.available():
        _, system = provider.prompt("event_extractor")
        data = "\n".join(f"{k}: {row[k]}" for k in ("title", "venue", "city_name", "start_date", "end_date",
                                                   "expected_attendance", "source_ref", "description"))
        out = provider.structured(provider.MODEL_SMART, system, data, Classification, 20.0, max_tokens=600)
        if out is not None:
            return out, "llm:" + provider.MODEL_SMART
    return rules(row), "rules"


def extract_pending(conn: sqlite3.Connection, actor: str) -> dict:
    """Classify every feed row not yet extracted; insert as unapproved signals."""
    created = []
    for row in feed_rows():
        city = conn.execute("SELECT city_id FROM cities WHERE name = ?", (row["city_name"],)).fetchone()
        if city is None:
            continue
        exists = conn.execute("SELECT 1 FROM dp_event_signal WHERE city_id = ? AND title = ? AND start_date = ?",
                              (city[0], row["title"], row["start_date"])).fetchone()
        if exists:
            continue
        cls, by = classify(row)
        sid = new_id("dps")
        now = wall_now_iso()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO dp_event_signal (signal_id, city_id, title, start_date, end_date, impact_tag, radius_km, "
                "confidence_band, justification, source_ref, extracted_by, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?, 'active', ?, ?)",
                (sid, city[0], row["title"], row["start_date"], row["end_date"], cls.impact_tag, f"{cls.radius_km}.00",
                 cls.confidence_band, cls.justification, row["source_ref"], by, now, now))
            audit.record(conn, actor, "event_signal_extract", f"dp_event_signal:{sid}",
                         after={"title": row["title"], "impact_tag": cls.impact_tag, "by": by})
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        created.append({"signal_id": sid, "title": row["title"], "city": row["city_name"], **cls.model_dump(), "by": by})
    return {"created": created, "count": len(created), "note": "new signals are inert until approved"}

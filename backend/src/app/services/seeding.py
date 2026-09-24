"""Seed steps (ARCHITECTURE §5.3). Idempotent: the working DB is rebuilt from the checksummed
organiser file every time, so a seed can never drift from the provided data."""
from __future__ import annotations

import csv
import hashlib
import json
import secrets
import shutil
import sqlite3
from datetime import date
from pathlib import Path

from app.config import DP_SCHEMA, ORGANISER_DIR, REPO_ROOT, SEED_DIR, SOURCE_DB
from app.core.clock import set_business_date, wall_now_iso
from app.core.ids import new_id
from app.core.money import dec, money_str
from app.pricing.params import default_config_json
from app.services import audit

ROOM_NAMES = ["Deluxe King", "Heritage Suite", "Lake View Double", "Premier Twin", "Garden Room",
              "Courtyard Queen", "Royal Suite", "Classic Double", "Terrace King", "Family Room"]
WARMUP_START = date(2026, 8, 17)
DEMO_DATE = date(2026, 8, 31)


def verify_checksums(root: Path = ORGANISER_DIR) -> int:
    ok = 0
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        path = root / name.strip().lstrip("*")
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        if h != digest:
            raise RuntimeError(f"organiser file changed or corrupt: {name}")
        ok += 1
    return ok


def ensure_admin_token(env_path: Path = REPO_ROOT / ".env") -> bool:
    """Generate ADMIN_TOKEN (32 random bytes, url-safe) into .env if absent. Returns True if created."""
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    if not lines and (REPO_ROOT / ".env.example").exists():
        lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("ADMIN_TOKEN="):
            if len(line.split("=", 1)[1].strip()) >= 32:
                return False
            lines[i] = "ADMIN_TOKEN=" + secrets.token_urlsafe(32)
            break
    else:
        lines.append("ADMIN_TOKEN=" + secrets.token_urlsafe(32))
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def copy_database(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(target) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(SOURCE_DB, target)


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DP_SCHEMA.read_text(encoding="utf-8"))


def snapshot_baseline(conn: sqlite3.Connection) -> dict:
    now = wall_now_iso()
    inv = conn.execute("SELECT entity_type, entity_id, for_date, price, currency FROM inventory_calendar "
                       "WHERE entity_type = 'room_type'").fetchall()
    conn.executemany(
        "INSERT INTO dp_baseline (baseline_id, entity_type, entity_id, for_date, baseline_price, currency, source, created_at) "
        "VALUES (?,?,?,?,?,?, 'inventory_calendar_snapshot', ?)",
        [(new_id("dpbl"), r["entity_type"], r["entity_id"], r["for_date"], money_str(dec(r["price"])), r["currency"], now)
         for r in inv],
    )
    pb = conn.execute("SELECT * FROM price_bounds").fetchall()
    conn.executemany(
        "INSERT INTO dp_bounds_version (bounds_version_id, bound_id, version, floor_price, ceiling_price, currency, "
        "max_daily_move_pct, max_weekly_move_pct, rounding_step, override_active, actor, reason, created_at) "
        "VALUES (?,?,1,?,?,?,?,?,?,?, 'seed', 'snapshot of the provided price_bounds row', ?)",
        [(new_id("dpv"), r["bound_id"], money_str(dec(r["floor_price"])), money_str(dec(r["ceiling_price"])), r["currency"],
          str(dec(r["max_daily_move_pct"])), str(dec(r["max_weekly_move_pct"])), money_str(dec(r["rounding_step"])),
          int(r["override_active"]), now) for r in pb],
    )
    cfg = default_config_json()
    conn.execute(
        "INSERT INTO dp_engine_config (config_id, version, factor_bounds, auto_band_pct, anomaly_z, anomaly_move_pct, "
        "kill_switch_active, actor, reason, status, effective_from_at, updated_at) "
        "VALUES (?, 1, ?, '8.00', '2.50', '12.00', 0, 'seed', 'initial engine configuration', 'active', ?, ?)",
        (new_id("dpc"), json.dumps(cfg, sort_keys=True), now, now),
    )
    set_business_date(conn, WARMUP_START)
    return {"baselines": len(inv), "bounds_versions": len(pb)}


def catalog_links(conn: sqlite3.Connection) -> int:
    """Link each city-resolvable room type to a same-city hotel. The organisers' platform has
    hotel_room_types, but this dataset does not include it, so the link is synthetic and says so."""
    now = wall_now_iso()
    ents = conn.execute(
        "SELECT DISTINCT e.entity_id, e.city_id FROM pricing_events e "
        "WHERE e.entity_type = 'room_type' AND e.entity_id IN (SELECT entity_id FROM inventory_calendar) "
        "ORDER BY e.city_id, e.entity_id").fetchall()
    by_city: dict[str, list[str]] = {}
    for r in ents:
        by_city.setdefault(r["city_id"], []).append(r["entity_id"])
    n = 0
    for city_id, rooms in by_city.items():
        hotels = [h["hotel_id"] for h in conn.execute(
            "SELECT hotel_id FROM hotels WHERE city_id = ? AND status = 'active' ORDER BY hotel_id", (city_id,))]
        if not hotels:
            continue
        for i, room in enumerate(rooms):
            conn.execute(
                "INSERT INTO dp_catalog_link (link_id, room_type_id, hotel_id, city_id, room_name, link_source, status, updated_at) "
                "VALUES (?,?,?,?,?, 'synthetic', 'active', ?)",
                (new_id("dpk"), room, hotels[i % len(hotels)], city_id, ROOM_NAMES[i % len(ROOM_NAMES)], now))
            n += 1
    return n


def event_signals(conn: sqlite3.Connection) -> dict:
    now = wall_now_iso()
    added = approved = 0
    with (SEED_DIR / "event_signals.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            city = conn.execute("SELECT city_id FROM cities WHERE name = ?", (row["city_name"],)).fetchone()
            if city is None:
                continue
            is_approved = row["approved"] == "1"
            conn.execute(
                "INSERT INTO dp_event_signal (signal_id, city_id, title, start_date, end_date, impact_tag, radius_km, "
                "confidence_band, justification, source_ref, extracted_by, approved_by, approved_at, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?, 'curated_seed', ?, ?, 'active', ?, ?)",
                (new_id("dps"), city["city_id"], row["title"], row["start_date"], row["end_date"], row["impact_tag"],
                 row["radius_km"], row["confidence_band"], row["justification"], row["source_ref"],
                 "seed_reviewer" if is_approved else None, now if is_approved else None, now, now))
            added += 1
            approved += int(is_approved)
    return {"signals": added, "approved": approved}


def seed_audit(conn: sqlite3.Connection, summary: dict) -> None:
    audit.record(conn, "seed", "seed_database", "var/pricing.db", after=summary,
                 reason="rebuilt from the checksummed organiser APS-02.db")

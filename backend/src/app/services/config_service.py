"""Engine configuration and price bounds: read, and change by appending a new version (never mutate).

Every change writes the new version and an audit row in the same transaction as the caller.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.core.clock import wall_now_iso
from app.core.ids import new_id
from app.core.money import dec, money_str, pct
from app.pricing.params import params_from_row
from app.pricing.types import Bounds, EngineParams
from app.services import audit


def active_engine_row(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM dp_engine_config ORDER BY version DESC LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("no engine configuration; run the seed")
    return dict(row)


def engine_params(conn: sqlite3.Connection) -> EngineParams:
    return params_from_row(active_engine_row(conn))


def new_engine_version(conn: sqlite3.Connection, actor: str, reason: str, *, factor_bounds: dict | None = None,
                       auto_band_pct: str | None = None, kill_switch: bool | None = None,
                       extra: dict | None = None) -> int:
    cur = active_engine_row(conn)
    cfg = json.loads(cur["factor_bounds"])
    if factor_bounds:
        cfg["factor_bounds"].update(factor_bounds)
    if extra:
        cfg.update(extra)
    version = int(cur["version"]) + 1
    now = wall_now_iso()
    new = {
        "factor_bounds": json.dumps(cfg, sort_keys=True),
        "auto_band_pct": auto_band_pct if auto_band_pct is not None else cur["auto_band_pct"],
        "kill_switch_active": int(kill_switch) if kill_switch is not None else cur["kill_switch_active"],
    }
    conn.execute(
        "INSERT INTO dp_engine_config (config_id, version, factor_bounds, auto_band_pct, anomaly_z, anomaly_move_pct, "
        "kill_switch_active, actor, reason, status, effective_from_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?, 'active', ?, ?)",
        (new_id("dpc"), version, new["factor_bounds"], new["auto_band_pct"], cur["anomaly_z"], cur["anomaly_move_pct"],
         new["kill_switch_active"], actor, reason, now, now))
    conn.execute("UPDATE dp_engine_config SET status = 'archived', updated_at = ? WHERE version = ?", (now, cur["version"]))
    audit.record(conn, actor, "engine_config_update", f"dp_engine_config:v{version}",
                 before={k: cur[k] for k in ("version", "auto_band_pct", "kill_switch_active")} | {"config": json.loads(cur["factor_bounds"])},
                 after={"version": version, "auto_band_pct": new["auto_band_pct"], "kill_switch_active": new["kill_switch_active"],
                        "config": cfg}, reason=reason)
    return version


def _bounds_from(row: sqlite3.Row | dict, version: int) -> Bounds:
    return Bounds(bound_id=row["bound_id"], floor=dec(row["floor_price"]), ceiling=dec(row["ceiling_price"]),
                  currency=row["currency"], daily_pct=pct(row["max_daily_move_pct"]),
                  weekly_pct=pct(row["max_weekly_move_pct"]), rounding_step=dec(row["rounding_step"]),
                  override_active=bool(row["override_active"]), version=version)


def bounds_for(conn: sqlite3.Connection, entity_type: str, entity_id: str) -> Bounds | None:
    row = conn.execute("SELECT * FROM price_bounds WHERE entity_type = ? AND entity_id = ?", (entity_type, entity_id)).fetchone()
    if row is None:
        return None
    v = conn.execute("SELECT MAX(version) FROM dp_bounds_version WHERE bound_id = ?", (row["bound_id"],)).fetchone()[0] or 1
    return _bounds_from(row, int(v))


def all_bounds(conn: sqlite3.Connection, entity_type: str = "room_type") -> dict[str, Bounds]:
    versions = {r[0]: int(r[1]) for r in conn.execute("SELECT bound_id, MAX(version) FROM dp_bounds_version GROUP BY bound_id")}
    return {r["entity_id"]: _bounds_from(r, versions.get(r["bound_id"], 1))
            for r in conn.execute("SELECT * FROM price_bounds WHERE entity_type = ?", (entity_type,))}


def update_bounds(conn: sqlite3.Connection, entity_type: str, entity_id: str, changes: dict, actor: str, reason: str) -> Bounds:
    """changes: any of floor_price, ceiling_price, max_daily_move_pct, max_weekly_move_pct, rounding_step (strings)."""
    row = conn.execute("SELECT * FROM price_bounds WHERE entity_type = ? AND entity_id = ?", (entity_type, entity_id)).fetchone()
    if row is None:
        raise KeyError("invalid_id")
    before = dict(row)
    merged = {**before}
    for k in ("floor_price", "ceiling_price", "rounding_step"):
        if k in changes:
            merged[k] = money_str(dec(changes[k]))
    for k in ("max_daily_move_pct", "max_weekly_move_pct"):
        if k in changes:
            merged[k] = str(dec(changes[k]))  # NUMERIC affinity column, as provided; always read back via dec()
    if dec(merged["floor_price"]) > dec(merged["ceiling_price"]):
        raise ValueError("floor_price must not exceed ceiling_price")
    now = wall_now_iso()
    conn.execute(
        "UPDATE price_bounds SET floor_price = ?, ceiling_price = ?, max_daily_move_pct = ?, max_weekly_move_pct = ?, "
        "rounding_step = ?, updated_at = ? WHERE bound_id = ?",
        (merged["floor_price"], merged["ceiling_price"], merged["max_daily_move_pct"], merged["max_weekly_move_pct"],
         merged["rounding_step"], now, row["bound_id"]))
    version = (conn.execute("SELECT MAX(version) FROM dp_bounds_version WHERE bound_id = ?", (row["bound_id"],)).fetchone()[0] or 0) + 1
    conn.execute(
        "INSERT INTO dp_bounds_version (bounds_version_id, bound_id, version, floor_price, ceiling_price, currency, "
        "max_daily_move_pct, max_weekly_move_pct, rounding_step, override_active, actor, reason, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_id("dpv"), row["bound_id"], version, merged["floor_price"], merged["ceiling_price"], row["currency"],
         merged["max_daily_move_pct"], merged["max_weekly_move_pct"], merged["rounding_step"], int(row["override_active"]),
         actor, reason, now))
    audit.record(conn, actor, "bounds_update", f"price_bounds:{row['bound_id']}", before=_public_bounds(before),
                 after=_public_bounds(merged) | {"version": version}, reason=reason)
    return _bounds_from(merged, version)


def _public_bounds(r: dict) -> dict:
    return {k: str(r[k]) for k in ("floor_price", "ceiling_price", "currency", "max_daily_move_pct", "max_weekly_move_pct",
                                   "rounding_step", "override_active")}


def set_override_flag(conn: sqlite3.Connection, entity_type: str, entity_id: str, active: bool) -> None:
    conn.execute("UPDATE price_bounds SET override_active = ?, updated_at = ? WHERE entity_type = ? AND entity_id = ?",
                 (int(active), wall_now_iso(), entity_type, entity_id))


def auto_band(params: EngineParams) -> Decimal:
    return params.auto_band_pct

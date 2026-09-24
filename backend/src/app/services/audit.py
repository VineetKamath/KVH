"""Append-only, hash-chained audit log (ARCHITECTURE §13).

row_hash = sha256(prev_hash ‖ canonical_json(row fields)). DB triggers reject UPDATE and DELETE on
dp_audit_log, so history can only grow. `verify()` recomputes the chain end to end.
Always call `record()` inside the same transaction as the change it describes.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from app.core.clock import wall_now_iso
from app.core.ids import new_id

GENESIS = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(payload)).encode("utf-8")).hexdigest()


def record(conn: sqlite3.Connection, actor: str, action: str, target: str,
           before: object = None, after: object = None, reason: str | None = None) -> str:
    last = conn.execute("SELECT seq, row_hash FROM dp_audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    seq = (last["seq"] + 1) if last else 1
    prev = last["row_hash"] if last else GENESIS
    audit_id = new_id("dpl")
    created_at = wall_now_iso()
    before_json = _canonical(before) if before is not None else None
    after_json = _canonical(after) if after is not None else None
    payload = {"audit_id": audit_id, "seq": seq, "actor": actor, "action": action, "target": target,
               "before_json": before_json, "after_json": after_json, "reason": reason, "created_at": created_at}
    row_hash = _hash(prev, payload)
    conn.execute(
        "INSERT INTO dp_audit_log (audit_id, seq, actor, action, target, before_json, after_json, reason, prev_hash, "
        "row_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (audit_id, seq, actor, action, target, before_json, after_json, reason, prev, row_hash, created_at),
    )
    return audit_id


def verify(conn: sqlite3.Connection) -> dict:
    prev = GENESIS
    n = 0
    for r in conn.execute("SELECT * FROM dp_audit_log ORDER BY seq"):
        payload = {k: r[k] for k in ("audit_id", "seq", "actor", "action", "target", "before_json", "after_json",
                                     "reason", "created_at")}
        if r["prev_hash"] != prev or _hash(prev, payload) != r["row_hash"]:
            return {"ok": False, "rows_checked": n, "broken_at_seq": r["seq"]}
        prev = r["row_hash"]
        n += 1
    return {"ok": True, "rows_checked": n, "head": prev}

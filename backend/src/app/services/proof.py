"""/v1/proof: the invariants, conformance and integrity checks, run LIVE against the running database."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from decimal import Decimal

from app.config import VALIDATOR, get_settings
from app.core.money import dec, money_str
from app.services import audit, reports, seeding, tier2


def _check(name: str, fn) -> dict:
    t = time.perf_counter()
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001 - a crashing check is a failed check, reported, never hidden
        ok, detail = False, f"error: {type(e).__name__}"
    return {"check": name, "ok": bool(ok), "detail": detail, "ms": round((time.perf_counter() - t) * 1000)}


def run_proof(conn: sqlite3.Connection) -> dict:
    def i1():
        exact = n = 0
        for r in conn.execute("SELECT d.published_price, b.floor_price, b.ceiling_price FROM dp_price_decision d "
                              "JOIN price_bounds b ON b.entity_id = d.entity_id WHERE d.is_live = 1"):
            n += 1
            if not (dec(r[1]) <= dec(r[0]) <= dec(r[2])):  # exact Decimal comparison, never float
                exact += 1
        return exact == 0, f"{n} live prices, {exact} outside [floor, ceiling]"

    def i3():
        n = bad = 0
        for r in conn.execute("SELECT baseline_price, published_price, factors FROM dp_price_decision WHERE is_live = 1"):
            n += 1
            wf = json.loads(r[2])["waterfall"]
            if sum((Decimal(w["contribution"]) for w in wf), Decimal(0)) != dec(r[1]) - dec(r[0]):
                bad += 1
        return bad == 0, f"{n} live prices reconstruct to the paisa, {bad} mismatches"

    def i4():
        rows = conn.execute("SELECT * FROM dp_price_decision WHERE is_live = 1 AND source = 'engine' "
                            "AND factors NOT LIKE '%\"compact\":true%'").fetchall()
        step = max(1, len(rows) // 60)
        sample = rows[::step][:60]  # deterministic, evenly spaced sample
        bad = sum(money_str(reports.replay(conn, r).published) != r["published_price"] for r in sample)
        return bad == 0, f"{len(sample)} sampled decisions replayed exactly from stored inputs, {bad} differ"

    def i5():
        unapproved = {r[0] for r in conn.execute("SELECT signal_id FROM dp_event_signal WHERE approved_at IS NULL")}
        leaked = 0
        for r in conn.execute("SELECT factors FROM dp_price_decision WHERE is_live = 1"):
            evs = json.loads(r[0])["inputs"].get("events", [])
            leaked += any(e["signal_id"] in unapproved for e in evs)
        return leaked == 0, f"{len(unapproved)} unapproved signals; {leaked} live prices touched by one"

    def i6():
        mism = conn.execute(
            "SELECT COUNT(*) FROM dp_price_decision d JOIN price_history h ON h.entity_id = d.entity_id "
            "AND h.effective_date = d.for_date WHERE d.is_live = 1 AND h.bound_clamped <> (d.clamp_status = 'clamped')"
        ).fetchone()[0]
        controlled = conn.execute("SELECT COUNT(*) FROM dp_price_decision WHERE source <> 'engine' AND clamp_status <> "
                                  "'not_applicable'").fetchone()[0]
        return mism == 0 and controlled == 0, f"price_history.bound_clamped agrees with the clamp record ({mism} " \
            f"mismatches); overrides/kill switch never counted ({controlled})"

    def validator():
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run([sys.executable, str(VALIDATOR), str(get_settings().db_path)], capture_output=True,  # noqa: S603
                             text=True, encoding="utf-8", env=env, check=False, timeout=120)
        last = (out.stdout or "").strip().splitlines()[-1:] or [""]
        return last[0] == "PASS", f"organiser validate_conformance.py: {last[0]}"

    def t2():
        r = tier2.check(conn)
        return r["ok"], f"Tier-2 tables {r['rows']}: {len(r['findings'])} findings"

    def chain():
        r = audit.verify(conn)
        return r["ok"], f"{r['rows_checked']} audit rows, hash chain intact" if r["ok"] else f"broken at seq {r.get('broken_at_seq')}"

    def checksums():
        return seeding.verify_checksums() == 29, "29 organiser files match SHA256SUMS.txt"

    checks = [
        _check("I1 bounded: every live price inside [floor, ceiling]", i1),
        _check("I3 explainable: waterfall reconstructs every live price exactly", i3),
        _check("I4 reproducible: stored decisions replay exactly", i4),
        _check("I5 inert: unapproved event signals change no price", i5),
        _check("I6 clamp report consistent with canonical price_history", i6),
        _check("Organiser conformance validator (Tier 1)", validator),
        _check("Tier-2 conformance (pricing_events, price_bounds, price_history)", t2),
        _check("Audit log hash chain", chain),
        _check("Organiser files untouched", checksums),
    ]
    return {"ok": all(c["ok"] for c in checks), "checks": checks,
            "note": "I2 (byte-identical concurrent quotes) is proven by tests/integration (20 threads + mid-flight bounds change)"}

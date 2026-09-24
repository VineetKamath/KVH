"""Seed the working database (ARCHITECTURE §5.3). Idempotent: rebuilds var/pricing.db from the
checksummed organiser file every run.

    python -m scripts.seed            full seed incl. 15-day warm-up replay (≈60 s)
    python -m scripts.seed --no-warmup
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import scripts  # noqa: F401  (adds backend/src to sys.path)
from app.config import VALIDATOR, get_settings
from app.core.clock import set_business_date
from app.db.conn import connect, tx
from app.services import seeding


def run_validator(db_path) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, str(VALIDATOR), str(db_path)], capture_output=True, text=True,  # noqa: S603
                         encoding="utf-8", check=False, env=env)
    text = (out.stdout or "") + (out.stderr or "")
    return out.returncode == 0 and text.strip().endswith("PASS"), text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("--warmup-start", default=None, help="first warm-up business date (default 2026-08-17)")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()

    n = seeding.verify_checksums()
    print(f"[1/9] organiser files verified against SHA256SUMS.txt: {n} OK")
    if seeding.ensure_admin_token():
        print("      generated ADMIN_TOKEN in .env (keep it secret; it unlocks the console)")
    db_path = get_settings().db_path
    seeding.copy_database(db_path)
    print(f"[2/9] copied APS-02.db -> {db_path.relative_to(db_path.parents[1])}")
    conn = connect(db_path)
    seeding.apply_schema(conn)
    print("[3/9] applied data-model/dp_schema.sqlite.sql")
    with tx(conn):
        base = seeding.snapshot_baseline(conn)
        print(f"[4/9] baselines {base['baselines']}, bounds v1 {base['bounds_versions']}, engine config v1")
        links = seeding.catalog_links(conn)
        print(f"[5/9] catalog links (synthetic, same-city): {links}")
        sig = seeding.event_signals(conn)
        print(f"[6/9] event signals: {sig['signals']} curated, {sig['approved']} pre-approved")
        seeding.seed_audit(conn, {**base, "links": links, **sig})

    if args.no_warmup:
        with tx(conn):
            set_business_date(conn, seeding.DEMO_DATE)
        print("[7/9] warm-up skipped (--no-warmup)")
    else:
        from app.services.cycle import warmup_replay

        from datetime import date as _date

        start = _date.fromisoformat(args.warmup_start) if args.warmup_start else seeding.WARMUP_START
        stats = warmup_replay(conn, start, seeding.DEMO_DATE)
        print(f"[7/9] warm-up replay: {stats['cycles']} cycles, {stats['decisions']} decisions, "
              f"{stats['clamped_last']} clamped on {seeding.DEMO_DATE}")
        from app.services.narration import pregenerate_demo

        pre = pregenerate_demo(conn)
        print(f"[8/9] narrations pre-generated: {pre}")
    conn.close()

    ok, text = run_validator(db_path)
    print(f"[9/9] organiser validator: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(text)
        return 1
    print(f"seed complete in {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

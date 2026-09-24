"""Save or restore the demo database (fast reset between rehearsals; a reseed takes minutes).

    python -m scripts.snapshot            # checkpoint WAL, copy var/pricing.db → var/demo_snapshot.db
    python -m scripts.snapshot --restore  # copy it back (stop the server first)
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "var" / "pricing.db"
SNAP = ROOT / "var" / "demo_snapshot.db"


def main(argv: list[str]) -> int:
    if "--restore" in argv:
        if not SNAP.exists():
            print(f"no snapshot at {SNAP}")
            return 1
        for suffix in ("-wal", "-shm"):
            Path(str(DB) + suffix).unlink(missing_ok=True)
        shutil.copyfile(SNAP, DB)
        print(f"restored {DB} from {SNAP}")
        return 0
    if not DB.exists():
        print(f"no database at {DB}; run python -m scripts.seed first")
        return 1
    conn = sqlite3.connect(str(DB))
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    shutil.copyfile(DB, SNAP)
    print(f"saved {SNAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

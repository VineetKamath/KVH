"""SQLite access. Parameterized statements only (never string-built SQL with user input).

Decision recorded in docs/DECISIONS.md (D-01): stdlib `sqlite3` is used directly instead of
SQLAlchemy Core, because explicit `BEGIN IMMEDIATE` transactions (the single-writer lock the
cycle and quote paths rely on) are simpler and more predictable with the stdlib driver. All SQL
lives in `db/` and `services/`, uses `?` placeholders, and is portable to Postgres by swapping the
placeholder style.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

_local = threading.local()


def connect(path: Path | None = None) -> sqlite3.Connection:
    db = path or get_settings().db_path
    conn = sqlite3.connect(str(db), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open a database strictly read-only (URI mode=ro, no pragmas that write). Used for the organiser's
    APS-02.db, which must stay byte-identical to SHA256SUMS.txt."""
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_conn() -> sqlite3.Connection:
    """One connection per thread (FastAPI runs sync endpoints in a thread pool), keyed by database path so a
    changed PIXELMINDS_DB (tests, snapshot restore) never keeps serving the old file."""
    path = get_settings().db_path
    cached = getattr(_local, "conn", None)
    if cached is None or cached[0] != path:
        if cached is not None:
            cached[1].close()
        _local.conn = (path, connect(path))
    return _local.conn[1]


@contextmanager
def tx(conn: sqlite3.Connection, immediate: bool = True) -> Iterator[sqlite3.Connection]:
    """A write transaction. IMMEDIATE takes SQLite's single-writer lock up front, so concurrent
    writers serialise instead of failing mid-transaction."""
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def rows(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r is not None else None

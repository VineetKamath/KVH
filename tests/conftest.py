"""Shared fixtures. Integration tests run against their OWN seeded database (never var/pricing.db, never the
organiser file): a 3-day warm-up keeps it fast while still exercising real cycles."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_SEEDED: Path | None = None


def _seed_once() -> Path:
    global _SEEDED
    if _SEEDED is None:
        tmp = Path(tempfile.mkdtemp(prefix="pixelminds-test-"))
        db = tmp / "seeded.db"
        os.environ["PIXELMINDS_DB"] = str(db)
        from scripts.seed import main

        assert main(["--warmup-start", "2026-08-29"]) == 0
        _SEEDED = db
    return _SEEDED


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """A fresh copy of the seeded test database per test (tests may write freely)."""
    src = _seed_once()
    dst = tmp_path / "work.db"
    shutil.copyfile(src, dst)
    os.environ["PIXELMINDS_DB"] = str(dst)
    return dst


@pytest.fixture()
def conn(db_path: Path):
    from app.db.conn import connect

    c = connect(db_path)
    yield c
    c.close()

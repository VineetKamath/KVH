"""Write docs/openapi.json (the frontend types are generated from it)."""
from __future__ import annotations

import json
from pathlib import Path

import scripts  # noqa: F401
from app.main import export_openapi


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
    out.write_text(json.dumps(export_openapi(), indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Operational scripts. Run from the repo root: `python -m scripts.<name>`."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "backend" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

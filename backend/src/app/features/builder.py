"""As-of feature helpers for the cycle. No wall-clock reads (business dates are passed in).

The competitive index is SIMULATED and labelled as such everywhere it appears: the organiser data has no
competitor table (ARCHITECTURE §6.2). It is a deterministic, smooth function of the entity and the dates,
so the same inputs always give the same price.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date
from decimal import Decimal

import pandas as pd


def _phase(key: str) -> float:
    h = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def simulated_comp_index(entity_id: str, for_date: date, business: date) -> Decimal:
    """In [-1, 1]; > 0 means our rate is above the simulated competitive set. Varies smoothly by stay date
    (period ~5 weeks) and drifts slowly with the business date (period ~3 weeks), never jumps."""
    a = _phase(entity_id + ":a")
    b = _phase(entity_id + ":b")
    stay = 0.7 * math.sin(2 * math.pi * (for_date.toordinal() / 37.0 + a))
    drift = 0.3 * math.sin(2 * math.pi * (business.toordinal() / 23.0 + b))
    return Decimal(f"{stay + drift:.6f}")


def entity_on_the_books(events: pd.DataFrame, business: date) -> dict[tuple[str, date, str], int]:
    """(entity_id, for_date, event_type) → count of events that occurred before `business` for future stay dates."""
    known = events[(events["occurred_date"] < business) & (events["for_date"] > business)]
    grouped = known.groupby(["entity_id", "for_date", "event_type"]).size()
    return {k: int(v) for k, v in grouped.items()}


def to_dec(x: float) -> Decimal:
    """Model outputs (numpy floats) → Decimal via a fixed 6-place string: deterministic, never float arithmetic."""
    if x != x or x in (float("inf"), float("-inf")):  # NaN / inf → caller's neutral default
        return Decimal("NaN")
    return Decimal(f"{float(x):.6f}")

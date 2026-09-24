"""A5 anomaly detection: arithmetic decides, an LLM only writes the summary line.

A move is flagged when its robust z-score (MAD over the room's own recent moves) exceeds
`anomaly_z`, or its absolute size exceeds `anomaly_move_pct`. Pure function.
"""
from __future__ import annotations

from decimal import Decimal
from statistics import median

from app.core.money import ZERO

MAD_SCALE = Decimal("1.4826")


def robust_z(move: Decimal, history: list[Decimal]) -> Decimal:
    if len(history) < 5:
        return ZERO
    med = Decimal(str(median(history)))
    mad = Decimal(str(median([abs(h - med) for h in history])))
    if mad == ZERO:
        return ZERO
    return abs(move - med) / (MAD_SCALE * mad)


def is_anomalous(move: Decimal, history: list[Decimal], z_threshold: Decimal, move_threshold: Decimal) -> tuple[bool, dict]:
    z = robust_z(move, history)
    flagged = z > z_threshold or abs(move) > move_threshold
    return flagged, {"move": str(move.quantize(Decimal("0.0001"))), "robust_z": str(z.quantize(Decimal("0.01"))),
                     "z_threshold": str(z_threshold), "move_threshold": str(move_threshold)}

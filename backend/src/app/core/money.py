"""Money and decimal helpers (rule R3: money is a 2-place decimal plus an ISO-4217 code, never a float).

Everything that touches a price goes through this module. Rounding happens at exactly one
place (`quantize`), with ROUND_HALF_EVEN, and splits use largest-remainder so parts sum exactly.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


def dec(value: object, default: Decimal | None = None) -> Decimal:
    """Convert a stored value to Decimal without passing through binary float arithmetic.

    SQLite returns NUMERIC-affinity columns (e.g. max_daily_move_pct) as int or float; money is TEXT.
    `str(value)` gives the shortest repr, which is the value that was written.
    Non-finite or unparseable input returns `default` (or raises if no default is given).
    """
    try:
        if isinstance(value, Decimal):
            out = value
        elif isinstance(value, bool):
            raise InvalidOperation("bool is not a number")
        else:
            out = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        if default is None:
            raise ValueError(f"not a decimal: {value!r}") from None
        return default
    if not out.is_finite():
        if default is None:
            raise ValueError(f"not a finite decimal: {value!r}")
        return default
    return out


def quantize(value: Decimal) -> Decimal:
    """The single rounding point for money: 2 places, banker's rounding."""
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def money_str(value: Decimal) -> str:
    """Canonical 2-place string for storage and JSON ('5200.00')."""
    return str(quantize(value))


def pct(value: object) -> Decimal:
    """A percentage column (e.g. 8 or 8.00) as a Decimal fraction (0.08)."""
    return dec(value) / HUNDRED


def clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if lo > hi:
        lo, hi = hi, lo
    return min(max(value, lo), hi)


def round_to_step_inward(value: Decimal, step: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    """Round to the nearest multiple of `step`, but never outside [lo, hi].

    If the nearest multiple falls outside, take the nearest multiple inside. If no multiple of the
    step lies inside [lo, hi], the value is returned unchanged (rounding is display hygiene and must
    never breach a guardrail).
    """
    if step <= ZERO:
        return value
    nearest = (value / step).quantize(ONE, rounding=ROUND_HALF_EVEN) * step
    if lo <= nearest <= hi:
        return quantize(nearest)
    if nearest > hi:
        down = (hi / step).to_integral_value(rounding=ROUND_FLOOR) * step
        return quantize(down) if down >= lo else value
    up = (lo / step).to_integral_value(rounding=ROUND_CEILING) * step
    return quantize(up) if up <= hi else value


def largest_remainder(parts: list[Decimal], total: Decimal) -> list[Decimal]:
    """Round each part to 0.01 so that the rounded parts sum exactly to `total` (a 2-place value).

    Works in integer cents: floor every part, then hand the leftover cents to the parts with the
    largest fractional remainders (ties broken by position, so the result is deterministic).
    """
    total_cents = int((quantize(total) * HUNDRED).to_integral_value())
    scaled = [p * HUNDRED for p in parts]
    floors = [int(s.to_integral_value(rounding=ROUND_FLOOR)) for s in scaled]
    remainders = [s - f for s, f in zip(scaled, floors)]
    leftover = total_cents - sum(floors)
    order = sorted(range(len(parts)), key=lambda i: (-remainders[i], i))
    if leftover >= 0:
        for k in range(leftover):
            floors[order[k % len(parts)]] += 1
    else:
        for k in range(-leftover):
            floors[order[::-1][k % len(parts)]] -= 1
    return [Decimal(c) / HUNDRED for c in floors]

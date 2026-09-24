"""Guardrail chain (ARCHITECTURE §6.3). Pure, Decimal only.

Order: weekly movement → daily movement → hard floor/ceiling → rounding (inward).
Hard bounds win over everything. `clamp_bound` is the LAST guardrail in the chain that changed the
price. Rounding alone never counts as a clamp, and rounding is done inward to the full allowed
interval, so it can never breach floor, ceiling or a movement cap (docs/DECISIONS.md D-03).
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from app.core.money import CENT, ONE, ZERO, clamp, quantize, round_to_step_inward
from app.pricing.types import Bounds, ChainStep, GuardrailResult


def _window(anchor: Decimal, frac: Decimal) -> tuple[Decimal, Decimal]:
    lo = (anchor * (ONE - frac)).quantize(CENT, rounding=ROUND_CEILING)
    hi = (anchor * (ONE + frac)).quantize(CENT, rounding=ROUND_FLOOR)
    return lo, hi


def _intersect(a: tuple[Decimal, Decimal], b: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal] | None:
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return (lo, hi) if lo <= hi else None


def _sane(value: Decimal, fallback: Decimal) -> Decimal:
    return value if isinstance(value, Decimal) and value.is_finite() and value > ZERO else fallback


def apply_chain(raw: Decimal, bounds: Bounds, daily_anchor: Decimal, weekly_anchor: Decimal) -> GuardrailResult:
    floor, ceiling = bounds.floor, bounds.ceiling
    if floor > ceiling:  # a mis-configured pair is treated as its sorted interval, never as "no bound"
        floor, ceiling = ceiling, floor
    hard = (floor, ceiling)
    x = _sane(raw, floor)
    a7 = _sane(weekly_anchor, floor)
    a1 = _sane(daily_anchor, floor)
    weekly = _window(a7, bounds.weekly_pct)
    daily = _window(a1, bounds.daily_pct)

    chain: list[ChainStep] = []
    last_bound: str | None = None
    bound_value: Decimal | None = None

    y = clamp(x, *weekly)
    if y != x:
        chain.append(ChainStep("max_weekly_movement", x, y))
        last_bound, bound_value = "max_weekly_movement", y
    x = y

    y = clamp(x, *daily)
    if y != x:
        chain.append(ChainStep("max_daily_movement", x, y))
        last_bound, bound_value = "max_daily_movement", y
    x = y

    y = clamp(x, *hard)
    if y != x:
        name = "floor" if y == floor else "ceiling"
        chain.append(ChainStep(name, x, y))
        last_bound, bound_value = name, y
    x = quantize(y)

    # The allowed interval honours the precedence hard > daily > weekly.
    allowed = hard
    with_daily = _intersect(allowed, daily)
    if with_daily is not None:
        allowed = with_daily
        with_weekly = _intersect(allowed, weekly)
        if with_weekly is not None:
            allowed = with_weekly
    if not (allowed[0] <= x <= allowed[1]):
        allowed = hard

    published = round_to_step_inward(x, bounds.rounding_step, allowed[0], allowed[1])
    published = quantize(clamp(published, *hard))
    return GuardrailResult(
        pre_round=x,
        published=published,
        clamp_bound=last_bound,
        bound_value=quantize(bound_value) if bound_value is not None else None,
        chain=tuple(chain),
        allowed_lo=allowed[0],
        allowed_hi=allowed[1],
    )

"""Exact attribution (ARCHITECTURE §6.4): a telescoping waterfall, no division.

contribution_i = running × (m_i − 1); running ← running × m_i. Contributions telescope, so their
exact sum is (final − baseline) with no Σ ln m denominator (safe when published == baseline).
Then 'guardrail' and 'rounding' steps close the gap to the published price, and largest-remainder
rounding makes the 2-place parts sum exactly to published − baseline (invariant I3).
"""
from __future__ import annotations

from decimal import Decimal

from app.core.money import ONE, largest_remainder
from app.pricing.types import Factor, WaterfallItem


def waterfall(baseline: Decimal, factors: tuple[Factor, ...], raw_exact: Decimal, raw: Decimal,
              pre_round: Decimal, published: Decimal) -> tuple[WaterfallItem, ...]:
    running = baseline
    exact: list[tuple[str, Decimal | None, Decimal]] = []
    for f in factors:
        contribution = running * (f.value - ONE)
        exact.append((f.name, f.value, contribution))
        running = running * f.value
    # running == raw_exact (up to Decimal context precision); close any residue into the last steps
    guard_mult = (pre_round / raw) if raw else None
    exact.append(("guardrail", guard_mult, pre_round - raw))
    exact.append(("rounding", (published / pre_round) if pre_round else None,
                  (published - pre_round) + (raw - running)))
    total = published - baseline
    rounded = largest_remainder([c for _, _, c in exact], total)
    return tuple(WaterfallItem(name, mult, amt) for (name, mult, _), amt in zip(exact, rounded))

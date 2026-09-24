"""`price_one`: the pure price function. Same inputs → same Decision, byte for byte.

    raw        = quantize(baseline × Π m_i)          (8 bounded factors)
    published  = guardrails(raw, bounds, anchors)    (weekly → daily → floor/ceiling → round inward)
    waterfall  = exact telescoping attribution       (sums to published − baseline)

No I/O, no clock reads, no randomness. The simulator calls this exact function, so a simulation is
production run on different inputs (ARCHITECTURE §9.3).
"""
from __future__ import annotations

from decimal import Decimal

from app.core.money import ONE, ZERO, quantize
from app.pricing.attribution import waterfall
from app.pricing.factors import compute_factors
from app.pricing.guardrails import apply_chain
from app.pricing.types import Bounds, Decision, EngineParams, PriceInputs


def price_one(inp: PriceInputs, bounds: Bounds, params: EngineParams) -> Decision:
    baseline = inp.baseline
    if not (isinstance(baseline, Decimal) and baseline.is_finite() and baseline > ZERO):
        baseline = bounds.floor  # a corrupted baseline cannot escape the bounds either (invariant I1)
    factors = compute_factors(inp, params)
    raw_exact = baseline
    for f in factors:
        raw_exact *= f.value
    raw = quantize(raw_exact)
    g = apply_chain(raw, bounds, inp.daily_anchor, inp.weekly_anchor)
    wf = waterfall(baseline, factors, raw_exact, raw, g.pre_round, g.published)
    if baseline is not inp.baseline:
        inp = _with_baseline(inp, baseline)
    return Decision(inputs=inp, bounds=bounds, factors=factors, raw_price=raw, guardrail=g, waterfall=wf)


def _with_baseline(inp: PriceInputs, baseline: Decimal) -> PriceInputs:
    from dataclasses import replace

    return replace(inp, baseline=baseline)


def fixed_price_decision(inp: PriceInputs, bounds: Bounds, params: EngineParams, price: Decimal) -> Decision:
    """A decision whose price is set by control (kill switch → baseline, or a manual override).
    It keeps the engine's factors for context but is never counted as a clamp (source != engine)."""
    d = price_one(inp, bounds, params)
    fixed = quantize(price)
    g = type(d.guardrail)(pre_round=fixed, published=fixed, clamp_bound=None, bound_value=None, chain=(),
                          allowed_lo=bounds.floor, allowed_hi=bounds.ceiling)
    raw_exact = inp.baseline
    for f in d.factors:
        raw_exact *= f.value
    wf = waterfall(d.inputs.baseline, d.factors, raw_exact, d.raw_price, fixed, fixed)
    return Decision(inputs=d.inputs, bounds=bounds, factors=d.factors, raw_price=d.raw_price, guardrail=g, waterfall=wf)


def move_fraction(new: Decimal, live: Decimal) -> Decimal:
    if live <= ZERO:
        return ZERO
    return abs(new / live - ONE)

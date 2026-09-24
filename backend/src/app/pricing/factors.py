"""The 8 bounded factors (ARCHITECTURE §6.2), in waterfall order.

Each factor turns evidence into a multiplier, is clamped to its configured [lo, hi], and records
its evidence so the explanation shows the numbers behind it. Any corrupted input (NaN, infinity,
negative where impossible) is replaced by the neutral value, so a bad feature row can only make a
factor neutral, never unbounded (invariant I1 is enforced again by the guardrails).
"""
from __future__ import annotations

from decimal import Decimal, localcontext

from app.core.money import ONE, ZERO, clamp
from app.pricing.types import FACTOR_ORDER, EngineParams, Factor, PriceInputs

HALF = Decimal("0.5")
TWO = Decimal("2")
CAP = Decimal("1000")  # any ratio beyond this is treated as the cap; factors are bounded far below anyway
Q3 = Decimal("0.001")


def _ev(x: Decimal) -> str:
    """Evidence string that can never raise (quantize overflows on absurd magnitudes)."""
    try:
        return str(x.quantize(Q3))
    except Exception:  # noqa: BLE001
        return str(x)


def _safe(value: object, default: Decimal, lo: Decimal | None = None, hi: Decimal | None = None) -> Decimal:
    try:
        v = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:  # noqa: BLE001 - any unparseable input becomes neutral
        return default
    if not v.is_finite():
        return default
    if lo is not None and v < lo:
        return default
    if hi is not None and v > hi:
        return default
    return min(v, CAP)


def _bounded(name: str, unclamped: Decimal, params: EngineParams, evidence: dict) -> Factor:
    fb = params.factor_bounds[name]
    if not fb.enabled:
        return Factor(name, ONE, unclamped, fb.lo, fb.hi, {**evidence, "disabled": True})
    return Factor(name, clamp(unclamped, fb.lo, fb.hi), unclamped, fb.lo, fb.hi, evidence)


def seasonality(inp: PriceInputs, params: EngineParams) -> Factor:
    s = _safe(inp.season_index, ONE, lo=ZERO)
    return _bounded("seasonality", s, params, {"season_index": str(s)})


def demand(inp: PriceInputs, params: EngineParams) -> Factor:
    """`demand_ratio` is already the credibility-weighted (Bühlmann) posterior: forecast vs normal, shrunk
    city → region → national in proportion to evidence. `credibility` is reported, not applied twice."""
    ratio = _safe(inp.demand_ratio, ONE, lo=ZERO)
    z = _safe(inp.credibility, ZERO, lo=ZERO, hi=ONE)
    m = ratio
    return _bounded("demand", m, params, {"forecast_vs_normal": _ev(ratio),
                                          "credibility": _ev(z)})


def pace(inp: PriceInputs, params: EngineParams) -> Factor:
    """`pace_ratio` is the Bühlmann posterior of on-the-books vs expected at this lead time."""
    ratio = _safe(inp.pace_ratio, ONE, lo=ZERO)
    m = ratio
    return _bounded("pace", m, params, {"pace_ratio": _ev(ratio)})


def lead_time(inp: PriceInputs, params: EngineParams) -> Factor:
    """Early-booking credit far out, firmness close in. `lead_cdf` is the share of bookings that are
    made closer to arrival than this lead time (estimated from data), so it adapts to any market."""
    fb = params.factor_bounds["lead_time"]
    f = _safe(inp.lead_cdf, HALF, lo=ZERO, hi=ONE)
    if f < HALF:
        m = ONE + (fb.hi - ONE) * (ONE - TWO * f)
    else:
        m = ONE - (ONE - fb.lo) * (TWO * f - ONE)
    return _bounded("lead_time", m, params, {"lead_time_days": inp.lead_time_days,
                                             "share_booked_closer_in": _ev(f)})


def event(inp: PriceInputs, params: EngineParams) -> Factor:
    """Only human-approved signals reach this function (the caller filters on approved_at)."""
    m = ONE
    used = []
    for ev in inp.events:
        impact = params.event_impact.get(ev.impact_tag, ZERO)
        conf = params.event_confidence.get(ev.confidence_band, ZERO)
        m *= ONE + impact * conf
        used.append({"signal_id": ev.signal_id, "title": ev.title, "impact": ev.impact_tag, "confidence": ev.confidence_band})
    return _bounded("event", m, params, {"approved_signals": used})


def competitor(inp: PriceInputs, params: EngineParams) -> Factor:
    c = _safe(inp.comp_index, ZERO, lo=Decimal("-1"), hi=ONE)
    m = ONE - params.competitor_sensitivity * c
    return _bounded("competitor", m, params, {"comp_index": _ev(c), "simulated": True})


def cancellation(inp: PriceInputs, params: EngineParams) -> Factor:
    r = _safe(inp.cxl_ratio, ONE, lo=ZERO)
    m = ONE - params.cancellation_sensitivity * (r - ONE)
    return _bounded("cancellation", m, params, {"cancel_rate_vs_normal": _ev(r)})


def uncertainty(inp: PriceInputs, params: EngineParams, product_so_far: Decimal) -> Factor:
    """Pulls the price back toward base in proportion to forecast uncertainty (symmetric: it also
    softens markdowns). pull s = s_max * w / (w + 1), multiplier = (product of factors 1-7) ** -s.
    See docs/DECISIONS.md D-02 for why this is symmetric rather than 0.94-1.00 only."""
    w = _safe(inp.rel_width, ZERO, lo=ZERO)
    s = params.damper_max_pull * w / (w + ONE)
    p = product_so_far if product_so_far > ZERO else ONE
    with localcontext() as ctx:
        ctx.prec = 28
        m = p ** (-s) if s != ZERO else ONE
    return _bounded("uncertainty", m, params, {"forecast_rel_width": _ev(w),
                                               "pull_toward_base": _ev(s)})


def compute_factors(inp: PriceInputs, params: EngineParams) -> tuple[Factor, ...]:
    ordered = [seasonality(inp, params), demand(inp, params), pace(inp, params), lead_time(inp, params),
               event(inp, params), competitor(inp, params), cancellation(inp, params)]
    product = ONE
    for f in ordered:
        product *= f.value
    ordered.append(uncertainty(inp, params, product))
    if tuple(f.name for f in ordered) != FACTOR_ORDER:
        raise RuntimeError("factor order drifted from the explanation contract")
    return tuple(ordered)

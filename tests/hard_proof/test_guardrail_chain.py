"""Clamp Report semantics at the engine level: one test per bound type, precedence, rounding."""
from decimal import Decimal

from app.pricing.engine import price_one
from app.pricing.guardrails import apply_chain
from app.pricing.params import default_params
from tests.pricing_fixtures import bounds, inputs

D = Decimal
PARAMS = default_params()


def test_accepted_when_inside_every_window():
    g = apply_chain(D("5200.00"), bounds(step="1.00"), D("5200.00"), D("5200.00"))
    assert g.clamp_bound is None and g.published == D("5200.00") and g.chain == ()


def test_ceiling_clamp():
    b = bounds(floor="3900.00", ceiling="6300.00", daily="15", weekly="30", step="1.00")
    g = apply_chain(D("6840.00"), b, D("6200.00"), D("6200.00"))
    assert g.clamp_bound == "ceiling" and g.bound_value == D("6300.00") and g.published == D("6300.00")


def test_floor_clamp():
    b = bounds(floor="3900.00", ceiling="9600.00", daily="15", weekly="30", step="1.00")
    g = apply_chain(D("3700.00"), b, D("4000.00"), D("4000.00"))
    assert g.clamp_bound == "floor" and g.published == D("3900.00")


def test_daily_movement_clamp():
    b = bounds(daily="8", weekly="30", step="1.00")
    g = apply_chain(D("6000.00"), b, D("5000.00"), D("5000.00"))
    assert g.clamp_bound == "max_daily_movement" and g.published == D("5400.00")


def test_weekly_movement_clamp():
    b = bounds(daily="15", weekly="18", step="1.00")
    g = apply_chain(D("6500.00"), b, D("6000.00"), D("5000.00"))  # daily allows 6900, weekly only 5900
    assert g.clamp_bound == "max_weekly_movement" and g.published == D("5900.00")


def test_ceiling_beats_daily_when_ceiling_dropped_below_daily_window():
    b = bounds(floor="3000.00", ceiling="4500.00", daily="5", weekly="20", step="1.00")
    g = apply_chain(D("6000.00"), b, D("6000.00"), D("6000.00"))  # daily window 5700-6300 is above the ceiling
    assert g.clamp_bound == "ceiling" and g.published == D("4500.00")
    assert [s.guardrail for s in g.chain] == ["ceiling"] or g.chain[-1].guardrail == "ceiling"


def test_rounding_alone_is_not_a_clamp_and_never_breaches():
    b = bounds(floor="3900.00", ceiling="6275.00", daily="15", weekly="30", step="50.00")
    g = apply_chain(D("5212.34"), b, D("5200.00"), D("5200.00"))
    assert g.clamp_bound is None and g.published == D("5200.00")
    g2 = apply_chain(D("6400.00"), b, D("6200.00"), D("6200.00"))  # ceiling 6275 is not a multiple of 50
    assert g2.clamp_bound == "ceiling" and g2.published <= D("6275.00") and g2.published == D("6250.00")


def test_price_one_reconstructs_to_the_paisa():
    d = price_one(inputs(demand_ratio="1.6", z="0.8", season="1.05", width="0.3"), bounds(), PARAMS)
    assert sum((w.contribution for w in d.waterfall), D(0)) == d.published - d.inputs.baseline


def test_waterfall_safe_when_published_equals_baseline():
    # clamp pulls the price exactly back to the baseline: the old Σ ln m formula divided by zero here
    b = bounds(floor="3900.00", ceiling="5200.00", daily="15", weekly="30", step="1.00")
    d = price_one(inputs(baseline="5200.00", demand_ratio="3", z="1"), b, PARAMS)
    assert d.published == D("5200.00")
    assert sum((w.contribution for w in d.waterfall), D(0)) == D("0.00")


def test_disabled_factor_is_neutral():
    from app.pricing.params import with_overrides
    from app.pricing.types import FactorBound

    p = with_overrides(PARAMS, {"demand": FactorBound(D("1.00"), D("1.00"), True)})
    d = price_one(inputs(demand_ratio="3", z="1"), bounds(), p)
    assert next(f for f in d.factors if f.name == "demand").value == D("1.00")

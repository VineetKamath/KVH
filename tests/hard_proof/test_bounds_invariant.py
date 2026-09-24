"""Invariant I1: no published price is ever outside [floor, ceiling], for any input, including
deliberately corrupted features. Invariant I3: the waterfall reconstructs the price exactly."""
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.pricing.engine import price_one
from app.pricing.params import default_params
from tests.pricing_fixtures import bounds, diwali, inputs

D = Decimal
PARAMS = default_params()

money = st.decimals(min_value=D("100.00"), max_value=D("200000.00"), places=2)
ratio = st.one_of(
    st.decimals(min_value=D("0"), max_value=D("50"), places=4),
    st.sampled_from(["NaN", "Infinity", "-Infinity", "-5", "1e30", "0"]).map(D),
)
unit = st.one_of(st.decimals(min_value=D("0"), max_value=D("1"), places=4), st.sampled_from(["NaN", "-1", "7"]).map(D))


@settings(max_examples=250, deadline=None)
@given(floor=money, span=st.decimals(min_value=D("0.00"), max_value=D("150000.00"), places=2),
       baseline=st.one_of(money, st.sampled_from(["NaN", "-100", "0", "Infinity"]).map(D)),
       a1=money, a7=money, dr=ratio, z=unit, season=ratio, pace=ratio, lead=unit, comp=ratio, cxl=ratio, width=ratio,
       daily=st.sampled_from(["5", "8", "12", "15"]), weekly=st.sampled_from(["18", "24", "30"]),
       step=st.sampled_from(["1.00", "10.00", "50.00"]), with_event=st.booleans())
def test_i1_published_always_within_floor_and_ceiling(floor, span, baseline, a1, a7, dr, z, season, pace, lead, comp,
                                                      cxl, width, daily, weekly, step, with_event):
    b = bounds(floor=str(floor), ceiling=str(floor + span), daily=daily, weekly=weekly, step=step)
    inp = inputs(baseline=baseline, a1=str(a1), a7=str(a7), demand_ratio="1", z="0.5")
    inp = type(inp)(**{**inp.__dict__, "demand_ratio": dr, "credibility": z, "season_index": season,
                       "pace_ratio": pace, "lead_cdf": lead, "comp_index": comp, "cxl_ratio": cxl, "rel_width": width,
                       "events": (diwali(),) if with_event else ()})
    d = price_one(inp, b, PARAMS)
    assert b.floor <= d.published <= b.ceiling
    assert d.published == d.published.quantize(D("0.01"))
    # I3 on every generated case: the waterfall sums to the published price, exactly
    assert sum((w.contribution for w in d.waterfall), D(0)) == d.published - d.inputs.baseline
    for f in d.factors:  # every factor stays inside its configured band
        assert f.lo <= f.value <= f.hi


@settings(max_examples=150, deadline=None)
@given(a1=st.decimals(min_value=D("4400.00"), max_value=D("6600.00"), places=2), dr=st.decimals(min_value=D("0"),
       max_value=D("5"), places=3), daily=st.sampled_from(["5", "8", "15"]))
def test_daily_cap_respected_when_compatible_with_hard_bounds(a1, dr, daily):
    """a1 is drawn so that its daily window overlaps the effective bounds (hotel bounds ∩ operating band
    5200 × [0.80, 1.35] = [4160, 7020]); outside that, the bound wins by design (as for a lowered ceiling)."""
    b = bounds(floor="3000.00", ceiling="12000.00", daily=daily, weekly="30", step="1.00")
    d = price_one(inputs(baseline="5200.00", a1=str(a1), a7=str(a1), demand_ratio=str(dr), z="1"), b, PARAMS)
    frac = D(daily) / 100
    assert a1 * (1 - frac) - D("0.01") <= d.published <= a1 * (1 + frac) + D("0.01")


@settings(max_examples=200, deadline=None)
@given(floor=money, span=st.decimals(min_value=D("0.00"), max_value=D("150000.00"), places=2), baseline=money,
       a1=money, dr=ratio, with_event=st.booleans())
def test_operating_band_only_narrows_hotel_bounds(floor, span, baseline, a1, dr, with_event):
    """D-18: the published price stays inside the hotel's bounds always, and inside reference × band whenever
    that band overlaps the hotel's bounds. The band can never widen what the hotel allows."""
    b = bounds(floor=str(floor), ceiling=str(floor + span), daily="15", weekly="30", step="1.00")
    inp = inputs(baseline=str(baseline), a1=str(a1), a7=str(a1), demand_ratio="1", z="1")
    inp = type(inp)(**{**inp.__dict__, "demand_ratio": dr, "events": (diwali(),) if with_event else ()})
    d = price_one(inp, b, PARAMS)
    assert b.floor <= d.published <= b.ceiling
    lo, hi = baseline * PARAMS.band_below, baseline * PARAMS.band_above
    if max(lo, b.floor) <= min(hi, b.ceiling) - 1:
        assert lo - 1 <= d.published <= hi + 1

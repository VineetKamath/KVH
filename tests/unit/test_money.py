from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.core.money import dec, largest_remainder, money_str, quantize, round_to_step_inward

D = Decimal


def test_largest_remainder_three_way_split():
    # WORKING_WITH_THE_DATA.md: ₹1000.00 three ways is 333.34 + 333.33 + 333.33
    parts = [D("1000") / 3] * 3
    assert largest_remainder(parts, D("1000.00")) == [D("333.34"), D("333.33"), D("333.33")]


@given(st.lists(st.decimals(min_value=-10000, max_value=10000, allow_nan=False, allow_infinity=False, places=6),
                min_size=1, max_size=12))
def test_largest_remainder_always_sums_exactly(parts):
    total = quantize(sum(parts, D(0)))
    out = largest_remainder(parts, total)
    assert sum(out, D(0)) == total
    assert all(o == o.quantize(D("0.01")) for o in out)


def test_quantize_is_bankers():
    assert quantize(D("2.345")) == D("2.34")
    assert quantize(D("2.355")) == D("2.36")
    assert money_str(D("8500")) == "8500.00"


def test_dec_never_goes_through_float_arithmetic():
    assert dec("8500.00") == D("8500.00")
    assert dec(8) == D("8")
    assert dec("NaN", default=D("1")) == D("1")
    assert dec(None, default=D("0")) == D("0")


@given(st.decimals(min_value=1, max_value=100000, places=2), st.sampled_from(["1.00", "10.00", "50.00"]),
       st.decimals(min_value=1, max_value=50000, places=2), st.decimals(min_value=0, max_value=50000, places=2))
def test_round_inward_never_leaves_interval(value, step, lo, width):
    hi = lo + width
    v = min(max(value, lo), hi)
    out = round_to_step_inward(v, D(step), lo, hi)
    assert lo <= out <= hi

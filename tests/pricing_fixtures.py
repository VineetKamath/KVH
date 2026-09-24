"""Shared builders for pricing tests."""
from __future__ import annotations

from decimal import Decimal

from app.pricing.types import Bounds, EventUplift, PriceInputs

D = Decimal


def bounds(floor="3900.00", ceiling="9600.00", daily="8", weekly="20", step="10.00", override=False, version=1) -> Bounds:
    return Bounds(bound_id="pbd_test01", floor=D(floor), ceiling=D(ceiling), currency="INR",
                  daily_pct=D(daily) / 100, weekly_pct=D(weekly) / 100, rounding_step=D(step),
                  override_active=override, version=version)


def inputs(baseline="5200.00", a1=None, a7=None, demand_ratio="1.0", z="0.5", season="1.0", pace="1.0",
           lead_cdf="0.5", comp="0", cxl="1.0", width="0.5", events=(), live=None, lead=30) -> PriceInputs:
    b = D(baseline) if not isinstance(baseline, Decimal) else baseline
    return PriceInputs(
        entity_type="room_type", entity_id="rmt_test01", for_date="2026-10-12", business_date="2026-08-31",
        currency="INR", baseline=b, lead_time_days=lead, season_index=D(season), demand_ratio=D(demand_ratio),
        credibility=D(z), pace_ratio=D(pace), lead_cdf=D(lead_cdf), events=tuple(events), comp_index=D(comp),
        cxl_ratio=D(cxl), rel_width=D(width), daily_anchor=D(a1) if a1 else b, weekly_anchor=D(a7) if a7 else b,
        live_price=D(live) if live else b,
    )


def diwali() -> EventUplift:
    return EventUplift("dps_test01", "Diwali", "major", "high")

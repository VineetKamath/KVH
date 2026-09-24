"""Value types for the pure pricing core. No I/O, no clock, Decimal only."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# Waterfall / factor order (ARCHITECTURE §6.2). The order is part of the explanation contract.
FACTOR_ORDER = (
    "seasonality",
    "demand",
    "pace",
    "lead_time",
    "event",
    "competitor",
    "cancellation",
    "uncertainty",
)

# The five factors that map onto canonical price_history columns.
CANONICAL_FACTOR_COLUMNS = {
    "demand": "demand_index",
    "lead_time": "lead_time_factor",
    "seasonality": "seasonality_factor",
    "event": "event_factor",
    "competitor": "competitor_factor",
}

GUARDRAILS = ("max_weekly_movement", "max_daily_movement", "floor", "ceiling")


@dataclass(frozen=True)
class FactorBound:
    lo: Decimal
    hi: Decimal
    enabled: bool = True


@dataclass(frozen=True)
class EngineParams:
    """Business settings (not fitted to data): editable, versioned in dp_engine_config."""

    version: int
    factor_bounds: dict[str, FactorBound]
    auto_band_pct: Decimal
    anomaly_z: Decimal
    anomaly_move_pct: Decimal
    kill_switch: bool
    # business weights (stated, editable; not learned)
    event_impact: dict[str, Decimal] = field(default_factory=dict)
    event_confidence: dict[str, Decimal] = field(default_factory=dict)
    competitor_sensitivity: Decimal = Decimal("0.06")
    cancellation_sensitivity: Decimal = Decimal("0.10")
    damper_max_pull: Decimal = Decimal("0.5")


@dataclass(frozen=True)
class Bounds:
    bound_id: str
    floor: Decimal
    ceiling: Decimal
    currency: str
    daily_pct: Decimal  # fraction, 0.08 = 8%
    weekly_pct: Decimal
    rounding_step: Decimal
    override_active: bool
    version: int


@dataclass(frozen=True)
class EventUplift:
    signal_id: str
    title: str
    impact_tag: str
    confidence_band: str


@dataclass(frozen=True)
class PriceInputs:
    """Everything `price_one` needs for one entity x stay date, as of one business date."""

    entity_type: str
    entity_id: str
    for_date: str
    business_date: str
    currency: str
    baseline: Decimal
    lead_time_days: int
    season_index: Decimal  # learned, shrunk month x DOW index (1.0 = no effect)
    demand_ratio: Decimal  # net forecast P50 / normal level
    credibility: Decimal  # z in [0, 1]
    pace_ratio: Decimal  # (otb + 1) / (expected otb at this lead + 1)
    lead_cdf: Decimal  # share of bookings made closer in than this lead time, in [0, 1]
    events: tuple[EventUplift, ...]
    comp_index: Decimal  # simulated competitive index in [-1, 1]; > 0 means we are above the set
    cxl_ratio: Decimal  # recent cancellation rate / normal cancellation rate
    rel_width: Decimal  # (P90 - P10) / P50 of the forecast
    daily_anchor: Decimal  # A1: live price for this stay date at D-1 (baseline if none)
    weekly_anchor: Decimal  # A7: live price for this stay date at D-7 (baseline if none)
    live_price: Decimal  # the currently live price (for the approval gate)


@dataclass(frozen=True)
class Factor:
    name: str
    value: Decimal  # the bounded multiplier actually applied
    unclamped: Decimal
    lo: Decimal
    hi: Decimal
    evidence: dict


@dataclass(frozen=True)
class ChainStep:
    guardrail: str
    before: Decimal
    after: Decimal


@dataclass(frozen=True)
class GuardrailResult:
    pre_round: Decimal
    published: Decimal
    clamp_bound: str | None
    bound_value: Decimal | None
    chain: tuple[ChainStep, ...]
    allowed_lo: Decimal
    allowed_hi: Decimal


@dataclass(frozen=True)
class WaterfallItem:
    step: str
    multiplier: Decimal | None
    contribution: Decimal  # rounded to 0.01 (largest remainder); items sum to published - baseline


@dataclass(frozen=True)
class Decision:
    inputs: PriceInputs
    bounds: Bounds
    factors: tuple[Factor, ...]
    raw_price: Decimal
    guardrail: GuardrailResult
    waterfall: tuple[WaterfallItem, ...]

    @property
    def published(self) -> Decimal:
        return self.guardrail.published

    @property
    def clamp_status(self) -> str:
        return "clamped" if self.guardrail.clamp_bound else "accepted"

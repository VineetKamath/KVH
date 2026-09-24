"""API contracts (Pydantic v2, strict). The single schema for the API, config edits and LLM outputs.

Every request model forbids extra fields, bounds every string and number, and validates ids, dates, money
strings and locales. Invalid input is rejected (422), never coerced.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ROOM_ID = Annotated[str, StringConstraints(pattern=r"^rmt_[0-9a-f]{6,16}$", max_length=24)]
DP_ID = Annotated[str, StringConstraints(pattern=r"^dp[a-z]{0,3}_[0-9a-z_]{4,32}$", max_length=40)]
SESSION_ID = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,64}$")]
LOCALE = Literal["en-IN", "hi", "kn"]
MONEY_STR = Annotated[str, StringConstraints(pattern=r"^\d{1,10}\.\d{2}$")]
PCT_STR = Annotated[str, StringConstraints(pattern=r"^\d{1,3}(\.\d{1,2})?$")]
REASON = Annotated[str, StringConstraints(min_length=5, max_length=300, strip_whitespace=True)]
AT_STR = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=2000)


class QuoteRequest(Strict):
    entity_type: Literal["room_type"] = "room_type"
    entity_id: ROOM_ID
    checkin_date: date
    checkout_date: date
    party_size: int = Field(ge=1, le=8)
    session_id: SESSION_ID
    locale: LOCALE = "en-IN"


class BoundsUpdate(Strict):
    floor_price: MONEY_STR | None = None
    ceiling_price: MONEY_STR | None = None
    max_daily_move_pct: PCT_STR | None = None
    max_weekly_move_pct: PCT_STR | None = None
    rounding_step: MONEY_STR | None = None
    reason: REASON

    @field_validator("max_daily_move_pct", "max_weekly_move_pct")
    @classmethod
    def pct_range(cls, v: str | None) -> str | None:
        if v is not None and not (Decimal("0.5") <= Decimal(v) <= Decimal("100")):
            raise ValueError("percentage must be between 0.5 and 100")
        return v


class FactorBoundIn(Strict):
    lo: Annotated[str, StringConstraints(pattern=r"^\d\.\d{1,3}$")]
    hi: Annotated[str, StringConstraints(pattern=r"^\d\.\d{1,3}$")]
    enabled: bool = True

    @field_validator("hi")
    @classmethod
    def ordered(cls, v: str, info) -> str:
        lo = info.data.get("lo")
        if lo is not None and Decimal(lo) > Decimal(v):
            raise ValueError("lo must not exceed hi")
        if not (Decimal("0.5") <= Decimal(v) <= Decimal("2.0")):
            raise ValueError("factor bounds must stay within 0.5-2.0")
        return v


FACTOR = Literal["seasonality", "demand", "pace", "lead_time", "event", "competitor", "cancellation", "uncertainty"]


def _band(v: str | None) -> str | None:
    if v is not None and not (Decimal("0.5") <= Decimal(v) <= Decimal("50")):
        raise ValueError("the auto-apply band must be between 0.5% and 50%")
    return v


class EngineUpdate(Strict):
    factor_bounds: dict[FACTOR, FactorBoundIn] | None = None
    auto_band_pct: PCT_STR | None = None
    reason: REASON

    _check_band = field_validator("auto_band_pct")(classmethod(lambda cls, v: _band(v)))


class KillSwitch(Strict):
    active: bool
    reason: REASON


class OverrideCreate(Strict):
    entity_id: ROOM_ID
    from_date: date
    to_date: date
    price: MONEY_STR
    reason: REASON
    expires_at: AT_STR


class ReasonOnly(Strict):
    reason: REASON


class ApprovalDecision(Strict):
    action: Literal["approve", "reject"]
    note: REASON


class EventIn(Strict):
    entity_type: Literal["room_type"] = "room_type"
    entity_id: ROOM_ID
    event_type: Literal["search", "view", "booking", "cancellation", "abandon"]
    for_date: date
    channel: Literal["web", "mobile_app", "partner", "call_centre", "agent"] = "web"
    party_size: int = Field(ge=1, le=20)
    quoted_price: MONEY_STR | None = None
    session_id: SESSION_ID
    event_id: Annotated[str, StringConstraints(pattern=r"^pev_[0-9a-z]{6,32}$")] | None = None


class EventBatch(Strict):
    events: list[EventIn] = Field(min_length=1, max_length=500)


class WhatIfPrompt(Strict):
    prompt: Annotated[str, StringConstraints(min_length=3, max_length=500, strip_whitespace=True)]
    entity_id: ROOM_ID | None = None


class WhatIfConfig(Strict):
    """The ONLY thing A4 may produce. Enum fields, range-checked values; the engine does the rest."""
    factor_bounds: dict[FACTOR, FactorBoundIn] = Field(default_factory=dict)
    disable_factors: list[FACTOR] = Field(default_factory=list, max_length=8)
    auto_band_pct: PCT_STR | None = None
    ceiling_change_pct: Annotated[str, StringConstraints(pattern=r"^-?\d{1,2}(\.\d{1,2})?$")] | None = None
    floor_change_pct: Annotated[str, StringConstraints(pattern=r"^-?\d{1,2}(\.\d{1,2})?$")] | None = None
    from_date: date | None = None
    to_date: date | None = None
    split_pct: Annotated[str, StringConstraints(pattern=r"^\d{1,2}(\.\d{1,2})?$")] | None = None
    explanation: Annotated[str, StringConstraints(max_length=300)] = ""

    _check_band = field_validator("auto_band_pct")(classmethod(lambda cls, v: _band(v)))

    @field_validator("ceiling_change_pct", "floor_change_pct")
    @classmethod
    def change_range(cls, v: str | None) -> str | None:
        if v is not None and not (Decimal("-50") <= Decimal(v) <= Decimal("50")):
            raise ValueError("bound changes are limited to ±50%")
        return v


class SimulateRequest(Strict):
    entity_id: ROOM_ID
    config: WhatIfConfig
    name: Annotated[str, StringConstraints(min_length=3, max_length=80)] = "what-if"
    prompt_text: Annotated[str, StringConstraints(max_length=500)] | None = None


class LoginRequest(Strict):
    token: Annotated[str, StringConstraints(min_length=16, max_length=256)]

"""A4 natural-language what-if copilot: plain language → a validated WhatIfConfig. The model never computes a
price or a metric; the same deterministic engine runs the config (services/simulator.py).

Two-step contract: the LLM (or the offline rule parser) produces a loose `Draft`; `to_config` validates it
into the strict WhatIfConfig (enum factor names, range checks). Anything outside the schema is REJECTED
with a message, never coerced.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from pydantic import BaseModel, Field, ValidationError

from app.ai.llm import provider
from app.contracts.models import FactorBoundIn, WhatIfConfig
from app.pricing.params import DEFAULT_FACTOR_BOUNDS

FACTORS = ("seasonality", "demand", "pace", "lead_time", "event", "competitor", "cancellation", "uncertainty")
SYNONYMS = {
    "event": "event", "events": "event", "festival": "event", "festivals": "event",
    "competitor": "competitor", "competitors": "competitor", "competition": "competitor", "market": "competitor",
    "competitive": "competitor", "parity": "competitor",
    "demand": "demand", "pace": "pace", "booking pace": "pace", "pickup": "pace",
    "lead time": "lead_time", "lead-time": "lead_time", "early booking": "lead_time", "early-booking": "lead_time",
    "season": "seasonality", "seasonal": "seasonality", "seasonality": "seasonality",
    "cancellation": "cancellation", "cancellations": "cancellation",
    "uncertainty": "uncertainty", "damper": "uncertainty",
}
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


class FactorCap(BaseModel):
    factor: str
    max_uplift_pct: float | None = None
    max_discount_pct: float | None = None


class Draft(BaseModel):
    """What the LLM may fill. Loose types on purpose: validation happens in `to_config`."""
    understood: bool
    disable_factors: list[str] = Field(default_factory=list)
    factor_caps: list[FactorCap] = Field(default_factory=list)
    auto_band_pct: float | None = None
    ceiling_change_pct: float | None = None
    floor_change_pct: float | None = None
    from_date: str | None = None
    to_date: str | None = None
    explanation: str = ""


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".") if "." in f"{x:.2f}" else f"{x}"


def to_config(d: Draft) -> tuple[WhatIfConfig | None, list[str]]:
    errors: list[str] = []
    if not d.understood:
        return None, ["the request could not be mapped to a supported change"]
    disable = []
    for f in d.disable_factors:
        name = SYNONYMS.get(f.strip().lower(), f.strip().lower())
        if name not in FACTORS:
            errors.append(f"unknown factor '{f}'")
        else:
            disable.append(name)
    caps: dict[str, FactorBoundIn] = {}
    for c in d.factor_caps:
        name = SYNONYMS.get(c.factor.strip().lower(), c.factor.strip().lower())
        if name not in FACTORS:
            errors.append(f"unknown factor '{c.factor}'")
            continue
        lo, hi = (float(x) for x in DEFAULT_FACTOR_BOUNDS[name])
        if c.max_uplift_pct is not None:
            if not (0 <= c.max_uplift_pct <= 50):
                errors.append(f"uplift cap {c.max_uplift_pct}% is outside 0-50%")
                continue
            hi = 1 + c.max_uplift_pct / 100
        if c.max_discount_pct is not None:
            if not (0 <= c.max_discount_pct <= 50):
                errors.append(f"discount cap {c.max_discount_pct}% is outside 0-50%")
                continue
            lo = 1 - c.max_discount_pct / 100
        lo = min(lo, hi)
        try:
            caps[name] = FactorBoundIn(lo=f"{lo:.3f}", hi=f"{hi:.3f}")
        except ValidationError as e:
            errors.append(f"{name}: {e.errors()[0]['msg']}")
    if errors:
        return None, errors
    try:
        cfg = WhatIfConfig(
            factor_bounds=caps, disable_factors=disable,
            auto_band_pct=None if d.auto_band_pct is None else _fmt(d.auto_band_pct),
            ceiling_change_pct=None if d.ceiling_change_pct is None else _fmt(d.ceiling_change_pct),
            floor_change_pct=None if d.floor_change_pct is None else _fmt(d.floor_change_pct),
            from_date=d.from_date or None, to_date=d.to_date or None, explanation=d.explanation[:300])
    except ValidationError as e:
        return None, [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
    if not (cfg.factor_bounds or cfg.disable_factors or cfg.auto_band_pct or cfg.ceiling_change_pct or cfg.floor_change_pct):
        return None, ["no supported change found in the request"]
    if cfg.from_date and cfg.to_date and cfg.from_date > cfg.to_date:
        return None, ["the window ends before it starts"]
    return cfg, []


def _window(text: str, today: date) -> tuple[str | None, str | None]:
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:to|-|until|through)\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1), m.group(2)
    for name, num in MONTHS.items():
        if re.search(rf"\b(for|in|during|across|through)\s+{name}\b", text):
            year = today.year if num >= today.month else today.year + 1
            last = calendar.monthrange(year, num)[1]
            return date(year, num, 1).isoformat(), date(year, num, last).isoformat()
    return None, None


def rule_parse(prompt: str, today: date) -> Draft:
    """Offline parser: deterministic patterns for the supported vocabulary (and the 20 eval prompts)."""
    t = prompt.lower()
    d = Draft(understood=False)
    names = "|".join(sorted((re.escape(k) for k in SYNONYMS), key=len, reverse=True))
    for m in re.finditer(rf"(?:switch off|turn off|disable|remove|ignore|without)\s+(?:the\s+)?({names})(?:\s+factor)?", t):
        d.disable_factors.append(m.group(1))
    for m in re.finditer(rf"(?:cap|limit)\s+(?:the\s+)?({names})\s+(?:uplift|factor|premium|increase)?\s*(?:at|to)\s+(-?\d+(?:\.\d+)?)\s*%", t):
        d.factor_caps.append(FactorCap(factor=m.group(1), max_uplift_pct=float(m.group(2))))
    for m in re.finditer(rf"(?:cap|limit)\s+(?:the\s+)?({names})\s+(?:discount|markdown|credit)\s*(?:at|to)\s+(-?\d+(?:\.\d+)?)\s*%", t):
        d.factor_caps.append(FactorCap(factor=m.group(1), max_discount_pct=float(m.group(2))))
    known = {c.factor for c in d.factor_caps}
    for m in re.finditer(r"(?:cap|limit)\s+(?:the\s+)?([a-z-]+)\s+(?:uplift|factor|premium|increase|discount|markdown|credit)", t):
        word = m.group(1)
        if word not in SYNONYMS and word not in known:  # never silently drop part of a request
            d.factor_caps.append(FactorCap(factor=word, max_uplift_pct=0))
    for which in ("ceiling", "floor"):
        m = re.search(rf"(lower|drop|reduce|cut|decrease|raise|increase|lift)\s+(?:the\s+)?{which}\s+by\s+(-?\d+(?:\.\d+)?)\s*%", t)
        if m:
            v = float(m.group(2)) * (-1 if m.group(1) in ("lower", "drop", "reduce", "cut", "decrease") else 1)
            setattr(d, f"{which}_change_pct", v)
    m = re.search(r"auto[- ]?(?:apply\s+)?band\s+(?:to|at|of)\s+(-?\d+(?:\.\d+)?)\s*%", t)
    if m:
        d.auto_band_pct = float(m.group(1))
    d.from_date, d.to_date = _window(t, today)
    d.understood = bool(d.disable_factors or d.factor_caps or d.ceiling_change_pct is not None or
                        d.floor_change_pct is not None or d.auto_band_pct is not None)
    d.explanation = "parsed by deterministic rules"
    return d


def parse(prompt: str, today: date) -> dict:
    source = "rules"
    draft = None
    if provider.available():
        _, system = provider.prompt("whatif_parser")
        draft = provider.structured(provider.MODEL_SMART, system + f"\nToday (business date): {today.isoformat()}.",
                                    prompt, Draft, 30.0, max_tokens=1200)
        if draft is not None:
            source = "llm:" + provider.MODEL_SMART
    if draft is None:
        draft = rule_parse(prompt, today)
    cfg, errors = to_config(draft)
    return {"accepted": cfg is not None, "config": cfg.model_dump(mode="json") if cfg else None, "errors": errors,
            "source": source, "draft": draft.model_dump()}


"""Decision ↔ storage/JSON. Money is always a 2-place string; multipliers are decimal strings."""
from __future__ import annotations

import json
from decimal import Decimal

from app.core.money import money_str
from app.pricing.types import CANONICAL_FACTOR_COLUMNS, Decision, PriceInputs

SHORT = {"demand": "demand", "lead_time": "lead", "seasonality": "season", "event": "event", "competitor": "competitor"}


def inputs_json(inp: PriceInputs) -> dict:
    return {
        "baseline": money_str(inp.baseline), "lead_time_days": inp.lead_time_days,
        "season_index": str(inp.season_index), "demand_ratio": str(inp.demand_ratio), "credibility": str(inp.credibility),
        "pace_ratio": str(inp.pace_ratio), "lead_cdf": str(inp.lead_cdf), "comp_index": str(inp.comp_index),
        "cxl_ratio": str(inp.cxl_ratio), "rel_width": str(inp.rel_width),
        "events": [{"signal_id": e.signal_id, "title": e.title, "impact_tag": e.impact_tag,
                    "confidence_band": e.confidence_band} for e in inp.events],
        "daily_anchor": money_str(inp.daily_anchor), "weekly_anchor": money_str(inp.weekly_anchor),
        "live_price": money_str(inp.live_price),
    }


def factors_json(d: Decision, source: str) -> str:
    contrib = {w.step: w for w in d.waterfall}
    items = [{"name": f.name, "value": str(f.value), "unclamped": str(f.unclamped), "lo": str(f.lo), "hi": str(f.hi),
              "evidence": f.evidence, "contribution": money_str(contrib[f.name].contribution)} for f in d.factors]
    steps = [{"step": w.step if (w.step != "guardrail" or source == "engine") else source,
              "multiplier": None if w.multiplier is None else str(w.multiplier),
              "contribution": money_str(w.contribution)} for w in d.waterfall]
    return json.dumps({"inputs": inputs_json(d.inputs), "items": items, "waterfall": steps}, sort_keys=True,
                      separators=(",", ":"), default=str)


def chain_json(d: Decision) -> str:
    return json.dumps([{"guardrail": s.guardrail, "before": money_str(s.before), "after": money_str(s.after)}
                       for s in d.guardrail.chain], separators=(",", ":"))


def explanation(d: Decision, source: str) -> str:
    """Canonical price_history.explanation, in the same style as the provided rows."""
    vals = {f.name: f.value for f in d.factors}
    parts = [f"{SHORT[n]} {vals[n].quantize(Decimal('0.01'))}" for n in ("demand", "lead_time", "seasonality", "event", "competitor")]
    text = " x ".join(parts)
    if source == "override":
        return text + " (manual override)"
    if source == "kill_switch":
        return text + " (kill switch: base rate)"
    if d.guardrail.clamp_bound:
        return text + f" (clamped to {d.guardrail.clamp_bound.replace('_', ' ')} {money_str(d.guardrail.bound_value)})"
    return text


def canonical_factor_values(d: Decision) -> dict[str, str]:
    vals = {f.name: f.value for f in d.factors}
    return {col: str(vals[name].quantize(Decimal("0.001"))) for name, col in CANONICAL_FACTOR_COLUMNS.items()}

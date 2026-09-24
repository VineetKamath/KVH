"""A5 anomaly summaries for the approval queue. Arithmetic (pricing/anomaly.py) decides what is flagged;
this module only writes the one-line summary: a deterministic template, optionally rewritten by the LLM
(cached per decision) when a key is configured."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.ai.llm import provider

_cache: dict[str, str] = {}


class Summary(BaseModel):
    summary: str = Field(max_length=200)


def template(row: dict) -> str:
    live, new = Decimal(row["live_price_before"]), Decimal(row["published_price"])
    move = (new / live - 1) * 100 if live else Decimal(0)
    direction = "up" if move > 0 else "down"
    why = "unusual for this room's recent moves" if row.get("anomaly_flag") else "larger than the auto-apply band"
    bound = f"; the {row['clamp_bound'].replace('_', ' ')} guardrail also applied" if row.get("clamp_bound") else ""
    return f"Proposed move {direction} {abs(move).quantize(Decimal('0.1'))}% for {row['for_date']} is {why}{bound}."


def summary_for(row: dict, use_llm: bool = False) -> str:
    base = template(row)
    if not use_llm or not provider.available():
        return base
    key = row["decision_id"]
    if key not in _cache:
        _, system = provider.prompt("anomaly_summary")
        out = provider.structured(provider.MODEL_FAST, system, base, Summary, 8.0, max_tokens=200)
        _cache[key] = out.summary if out else base
    return _cache[key]

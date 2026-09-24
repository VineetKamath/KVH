"""A2 numeric faithfulness gate: a hard block, not a metric.

A sentence set passes only if:
  1. every number in the text (after normalising Devanagari ०-९ and Kannada ೦-೯ digits and removing digit
     grouping) is one of the numbers in the facts payload (percentages, floor, ceiling, total);
  2. every signed percentage ('+5.2%' / '-3.1%') has the sign of the fact it states;
  3. no pressure/urgency language appears (the narrator explains; it never sells).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")} | {ord(c): str(i) for i, c in enumerate("೦೧೨೩೪೫೬೭೮೯")}
NUM_RE = re.compile(r"([+\-−]?)\s*(\d[\d,]*(?:\.\d+)?)\s*(%?)")
URGENCY = ("hurry", "last chance", "book now", "limited time", "act fast", "don't miss", "only a few", "जल्दी", "ತ್ವರೆ")


def normalise(text: str) -> str:
    return text.translate(DIGIT_MAP).replace("−", "-")


def allowed_numbers(facts: dict, floor: str, ceiling: str) -> tuple[set[Decimal], dict[Decimal, set[str]]]:
    nums: set[Decimal] = set()
    signs: dict[Decimal, set[str]] = {}
    for it in facts["items"]:
        p = abs(Decimal(it["percent"]))
        nums.add(p)
        signs.setdefault(p, set()).add("+" if Decimal(it["percent"]) > 0 else "-")
    for m in (floor, ceiling, facts.get("total_price", "0")):
        v = Decimal(m)
        nums.update({v, v.quantize(Decimal("1")) if v == v.to_integral_value() else v})
    return nums, signs


def check(sentences: list[str], facts: dict, floor: str, ceiling: str) -> tuple[bool, list[str]]:
    problems = []
    nums, signs = allowed_numbers(facts, floor, ceiling)
    for s in sentences:
        low = s.lower()
        if any(u in low for u in URGENCY):
            problems.append(f"urgency language: {s!r}")
        for sign, raw, is_pct in NUM_RE.findall(normalise(s)):
            try:
                v = Decimal(raw.replace(",", ""))
            except InvalidOperation:
                problems.append(f"unparseable number {raw!r}")
                continue
            if v not in nums:
                problems.append(f"number not in payload: {raw}")
                continue
            if is_pct and sign and v in signs:
                want = "-" if sign in ("-", "−") else "+"
                if want not in signs[v]:
                    problems.append(f"wrong direction for {sign}{raw}%")
    return (not problems), problems

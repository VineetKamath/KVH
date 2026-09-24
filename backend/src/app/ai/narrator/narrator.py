"""A2 price rationale narrator: facts → sentences in en-IN / hi / kn, gated, cached per (decision, locale).

Grounding: the model's ENTIRE input is the facts payload derived from one decision's exact waterfall.
Gate: ai/narrator/gate.py (numbers + direction + no urgency). Retry once, then the deterministic template.
Result: 100% of shipped explanations pass the gate (templates are gated too, as a self-check).
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from pydantic import BaseModel, Field

from app.ai.llm import provider
from app.ai.narrator.gate import check
from app.core.clock import wall_now_iso
from app.core.ids import new_id
from app.services import narration
from app.services.errors import invalid_id

LOCALE_NAMES = {"en-IN": "en-IN (Indian English)", "hi": "hi (Hindi, Devanagari script)", "kn": "kn (Kannada, Kannada script)"}
TIMEOUT_S = 12.0


class Narration(BaseModel):
    sentences: list[str] = Field(min_length=1, max_length=5)


def _context(conn: sqlite3.Connection, decision_id: str) -> tuple[dict, dict, str, str, str]:
    d = conn.execute("SELECT * FROM dp_price_decision WHERE decision_id = ?", (decision_id,)).fetchone()
    if d is None:
        raise invalid_id("decision")
    b = conn.execute("SELECT floor_price, ceiling_price, currency FROM price_bounds WHERE entity_id = ?",
                     (d["entity_id"],)).fetchone()
    sym = conn.execute("SELECT symbol FROM currencies WHERE iso4217 = ?", (b["currency"],)).fetchone()
    return dict(d), narration.facts([dict(d)]), b["floor_price"], b["ceiling_price"], sym["symbol"] if sym else ""


def narrate_decision(conn: sqlite3.Connection, decision_id: str, locale: str, force: bool = False) -> dict:
    if not force:
        cached = narration.cached(conn, decision_id, locale)
        if cached:
            return {"decision_id": decision_id, "locale": locale, "sentences": cached, "source": "cache"}
    d, facts, floor, ceiling, symbol = _context(conn, decision_id)
    template = narration.render_template(facts, locale, Decimal(floor), Decimal(ceiling), symbol)
    template_ok, template_problems = check(template, facts, floor, ceiling)
    sentences, source, attempts, problems = None, "template", 0, []
    if provider.available():
        version, system = provider.prompt("narrator")
        payload = json.dumps({"locale": LOCALE_NAMES.get(locale, locale), "facts": facts["items"],
                              "event_titles": facts["event_titles"], "floor": f"{symbol}{floor}",
                              "ceiling": f"{symbol}{ceiling}", "currency_symbol": symbol}, ensure_ascii=False)
        for attempts in (1, 2):
            out = provider.structured(provider.MODEL_FAST, system, payload, Narration, TIMEOUT_S, max_tokens=800)
            if out is None:
                problems = ["llm unavailable or refused"]
                break
            ok, problems = check(out.sentences, facts, floor, ceiling)
            if ok:
                sentences, source = out.sentences, "llm"
                break
    if sentences is None:
        sentences = template
        if not template_ok:  # should never happen; if it does, record it rather than ship silently
            problems = problems + [f"template: {p}" for p in template_problems]
    gate_passed = source == "llm" or template_ok
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO dp_narration (narration_id, decision_id, locale, text, gate_passed, fallback_used, attempts, "
            "model_version, prompt_version, created_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(decision_id, locale) DO UPDATE SET text = excluded.text, gate_passed = excluded.gate_passed, "
            "fallback_used = excluded.fallback_used, attempts = excluded.attempts, model_version = excluded.model_version, "
            "created_at = excluded.created_at",
            (new_id("dpn"), decision_id, locale, json.dumps(sentences, ensure_ascii=False), int(gate_passed),
             int(source != "llm"), attempts, provider.MODEL_FAST if source == "llm" else "template",
             "v1", wall_now_iso()))
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"decision_id": decision_id, "locale": locale, "sentences": sentences, "source": source,
            "gate_passed": gate_passed, "attempts": attempts, "gate_problems": problems}

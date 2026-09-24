"""Price explanations for travellers (A2). The template renderer here is the deterministic fallback and the
offline provider; the LLM narrator (ai/narrator) rewrites the same facts and must pass the numeric gate.

Every number in a sentence comes from the decision's exact waterfall: a factor's percentage is its
contribution divided by the baseline, so the percentages add up (with the guardrail step) to the total move.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.core.money import HUNDRED, ZERO, dec, money_str

LOCALES = ("en-IN", "hi", "kn")

TITLE_I18N = {
    "Diwali": {"hi": "दिवाली", "kn": "ದೀಪಾವಳಿ"},
    "Dussehra": {"hi": "दशहरा", "kn": "ದಸರಾ"},
    "Sharad Navratri": {"hi": "शारदीय नवरात्रि", "kn": "ಶರನ್ನವರಾತ್ರಿ"},
    "Gandhi Jayanti": {"hi": "गांधी जयंती", "kn": "ಗಾಂಧಿ ಜಯಂತಿ"},
    "Durga Puja": {"hi": "दुर्गा पूजा", "kn": "ದುರ್ಗಾ ಪೂಜೆ"},
}

T = {
    "en-IN": {
        "demand+": "Demand for these dates is running above normal ({pct}).",
        "demand-": "Demand for these dates is softer than usual ({pct}).",
        "pace+": "Bookings are arriving faster than usual for this lead time ({pct}).",
        "pace-": "Bookings are arriving slower than usual for this lead time ({pct}).",
        "lead_time+": "Your stay is close in, so the last-minute rate applies ({pct}).",
        "lead_time-": "You are booking well ahead, so an early-booking credit applies ({pct}).",
        "event+": "{title} overlaps your stay ({pct}).",
        "event-": "{title} overlaps your stay ({pct}).",
        "competitor+": "Market comparison adjustment ({pct}).",
        "competitor-": "Market comparison adjustment ({pct}).",
        "seasonality+": "Seasonal pattern for this time of year ({pct}).",
        "seasonality-": "Seasonal pattern for this time of year ({pct}).",
        "cancellation+": "Recent cancellations are lower than usual ({pct}).",
        "cancellation-": "Recent cancellations are higher than usual ({pct}).",
        "uncertainty+": "Forecast uncertainty pulls the price toward the base rate ({pct}).",
        "uncertainty-": "Forecast uncertainty pulls the price toward the base rate ({pct}).",
        "ceiling": "The price is held at this room's ceiling ({pct}).",
        "floor": "The price is held at this room's floor ({pct}).",
        "max_daily_movement": "A daily price-movement limit was applied ({pct}).",
        "max_weekly_movement": "A weekly price-movement limit was applied ({pct}).",
        "override": "Set by the hotel's revenue manager ({pct}).",
        "kill_switch": "Dynamic pricing is paused; the base rate applies ({pct}).",
        "bounds": "This room's price always stays between {floor} and {ceiling}.",
    },
    "hi": {
        "demand+": "इन तारीखों के लिए मांग सामान्य से अधिक है ({pct})।",
        "demand-": "इन तारीखों के लिए मांग सामान्य से कम है ({pct})।",
        "pace+": "इस समय-सीमा के लिए बुकिंग सामान्य से तेज़ आ रही हैं ({pct})।",
        "pace-": "इस समय-सीमा के लिए बुकिंग सामान्य से धीमी हैं ({pct})।",
        "lead_time+": "यात्रा की तारीख नज़दीक है, इसलिए अंतिम-समय दर लागू है ({pct})।",
        "lead_time-": "आपने काफ़ी पहले बुक किया है, इसलिए अर्ली-बुकिंग छूट लागू है ({pct})।",
        "event+": "{title} आपके ठहरने की तारीखों से मेल खाता है ({pct})।",
        "event-": "{title} आपके ठहरने की तारीखों से मेल खाता है ({pct})।",
        "competitor+": "बाज़ार तुलना के आधार पर समायोजन ({pct})।",
        "competitor-": "बाज़ार तुलना के आधार पर समायोजन ({pct})।",
        "seasonality+": "साल के इस समय का मौसमी पैटर्न ({pct})।",
        "seasonality-": "साल के इस समय का मौसमी पैटर्न ({pct})।",
        "cancellation+": "हाल में रद्दीकरण सामान्य से कम हैं ({pct})।",
        "cancellation-": "हाल में रद्दीकरण सामान्य से अधिक हैं ({pct})।",
        "uncertainty+": "पूर्वानुमान की अनिश्चितता कीमत को मूल दर की ओर खींचती है ({pct})।",
        "uncertainty-": "पूर्वानुमान की अनिश्चितता कीमत को मूल दर की ओर खींचती है ({pct})।",
        "ceiling": "कीमत इस कमरे की अधिकतम सीमा पर रोकी गई है ({pct})।",
        "floor": "कीमत इस कमरे की न्यूनतम सीमा पर रोकी गई है ({pct})।",
        "max_daily_movement": "दैनिक मूल्य-परिवर्तन की सीमा लागू की गई ({pct})।",
        "max_weekly_movement": "साप्ताहिक मूल्य-परिवर्तन की सीमा लागू की गई ({pct})।",
        "override": "होटल के रेवेन्यू मैनेजर द्वारा तय ({pct})।",
        "kill_switch": "डायनेमिक प्राइसिंग रुकी हुई है; मूल दर लागू है ({pct})।",
        "bounds": "इस कमरे की कीमत हमेशा {floor} और {ceiling} के बीच रहती है।",
    },
    "kn": {
        "demand+": "ಈ ದಿನಾಂಕಗಳಿಗೆ ಬೇಡಿಕೆ ಸಾಮಾನ್ಯಕ್ಕಿಂತ ಹೆಚ್ಚಿದೆ ({pct}).",
        "demand-": "ಈ ದಿನಾಂಕಗಳಿಗೆ ಬೇಡಿಕೆ ಸಾಮಾನ್ಯಕ್ಕಿಂತ ಕಡಿಮೆ ಇದೆ ({pct}).",
        "pace+": "ಈ ಅವಧಿಗೆ ಬುಕಿಂಗ್‌ಗಳು ಸಾಮಾನ್ಯಕ್ಕಿಂತ ವೇಗವಾಗಿ ಬರುತ್ತಿವೆ ({pct}).",
        "pace-": "ಈ ಅವಧಿಗೆ ಬುಕಿಂಗ್‌ಗಳು ಸಾಮಾನ್ಯಕ್ಕಿಂತ ನಿಧಾನವಾಗಿವೆ ({pct}).",
        "lead_time+": "ಪ್ರಯಾಣದ ದಿನಾಂಕ ಹತ್ತಿರವಿರುವುದರಿಂದ ಕೊನೆಯ ಕ್ಷಣದ ದರ ಅನ್ವಯಿಸುತ್ತದೆ ({pct}).",
        "lead_time-": "ನೀವು ಮುಂಚಿತವಾಗಿ ಬುಕ್ ಮಾಡುತ್ತಿರುವುದರಿಂದ ಮುಂಗಡ ಬುಕಿಂಗ್ ರಿಯಾಯಿತಿ ಅನ್ವಯಿಸುತ್ತದೆ ({pct}).",
        "event+": "{title} ನಿಮ್ಮ ವಾಸ್ತವ್ಯದ ದಿನಾಂಕಗಳೊಂದಿಗೆ ಹೊಂದಿಕೆಯಾಗುತ್ತದೆ ({pct}).",
        "event-": "{title} ನಿಮ್ಮ ವಾಸ್ತವ್ಯದ ದಿನಾಂಕಗಳೊಂದಿಗೆ ಹೊಂದಿಕೆಯಾಗುತ್ತದೆ ({pct}).",
        "competitor+": "ಮಾರುಕಟ್ಟೆ ಹೋಲಿಕೆಯ ಆಧಾರದ ಹೊಂದಾಣಿಕೆ ({pct}).",
        "competitor-": "ಮಾರುಕಟ್ಟೆ ಹೋಲಿಕೆಯ ಆಧಾರದ ಹೊಂದಾಣಿಕೆ ({pct}).",
        "seasonality+": "ವರ್ಷದ ಈ ಸಮಯದ ಋತುಮಾನದ ಪ್ರವೃತ್ತಿ ({pct}).",
        "seasonality-": "ವರ್ಷದ ಈ ಸಮಯದ ಋತುಮಾನದ ಪ್ರವೃತ್ತಿ ({pct}).",
        "cancellation+": "ಇತ್ತೀಚಿನ ರದ್ದತಿಗಳು ಸಾಮಾನ್ಯಕ್ಕಿಂತ ಕಡಿಮೆ ಇವೆ ({pct}).",
        "cancellation-": "ಇತ್ತೀಚಿನ ರದ್ದತಿಗಳು ಸಾಮಾನ್ಯಕ್ಕಿಂತ ಹೆಚ್ಚಿವೆ ({pct}).",
        "uncertainty+": "ಮುನ್ಸೂಚನೆಯ ಅನಿಶ್ಚಿತತೆ ಬೆಲೆಯನ್ನು ಮೂಲ ದರದ ಕಡೆಗೆ ಎಳೆಯುತ್ತದೆ ({pct}).",
        "uncertainty-": "ಮುನ್ಸೂಚನೆಯ ಅನಿಶ್ಚಿತತೆ ಬೆಲೆಯನ್ನು ಮೂಲ ದರದ ಕಡೆಗೆ ಎಳೆಯುತ್ತದೆ ({pct}).",
        "ceiling": "ಬೆಲೆಯನ್ನು ಈ ಕೊಠಡಿಯ ಗರಿಷ್ಠ ಮಿತಿಯಲ್ಲಿ ನಿಲ್ಲಿಸಲಾಗಿದೆ ({pct}).",
        "floor": "ಬೆಲೆಯನ್ನು ಈ ಕೊಠಡಿಯ ಕನಿಷ್ಠ ಮಿತಿಯಲ್ಲಿ ನಿಲ್ಲಿಸಲಾಗಿದೆ ({pct}).",
        "max_daily_movement": "ದೈನಂದಿನ ಬೆಲೆ ಬದಲಾವಣೆಯ ಮಿತಿ ಅನ್ವಯಿಸಲಾಗಿದೆ ({pct}).",
        "max_weekly_movement": "ವಾರದ ಬೆಲೆ ಬದಲಾವಣೆಯ ಮಿತಿ ಅನ್ವಯಿಸಲಾಗಿದೆ ({pct}).",
        "override": "ಹೋಟೆಲ್‌ನ ರೆವೆನ್ಯೂ ಮ್ಯಾನೇಜರ್ ನಿಗದಿಪಡಿಸಿದ್ದಾರೆ ({pct}).",
        "kill_switch": "ಡೈನಾಮಿಕ್ ಬೆಲೆ ನಿಗದಿ ತಾತ್ಕಾಲಿಕವಾಗಿ ನಿಂತಿದೆ; ಮೂಲ ದರ ಅನ್ವಯಿಸುತ್ತದೆ ({pct}).",
        "bounds": "ಈ ಕೊಠಡಿಯ ಬೆಲೆ ಯಾವಾಗಲೂ {floor} ಮತ್ತು {ceiling} ನಡುವೆ ಇರುತ್ತದೆ.",
    },
}

MAX_REASONS = 4


def fmt_pct(p: Decimal) -> str:
    q = p.quantize(Decimal("0.1"))
    return f"{'+' if q > 0 else ''}{q}%"


def fmt_money(amount: Decimal, symbol: str) -> str:
    """en-IN grouping (12,34,567.89) — the UI re-formats numbers with Intl; this is for text only."""
    s = money_str(amount)
    whole, frac = s.split(".")
    neg = whole.startswith("-")
    whole = whole.lstrip("-")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{'-' if neg else ''}{symbol}{whole}.{frac}"


def facts(decisions: list[dict]) -> dict:
    """Aggregate the exact waterfall across the nights of a quote into percentage facts.

    Each fact: step, direction, contribution (sum over nights), percent of total baseline. These facts are the
    ONLY numbers the narrator may use (A2 grounding contract)."""
    total_base = sum((dec(d["baseline_price"]) for d in decisions), ZERO)
    agg: dict[str, Decimal] = {}
    titles: list[str] = []
    source = decisions[0]["source"]
    bound = None
    for d in decisions:
        f = json.loads(d["factors"])
        for w in f["waterfall"]:
            agg[w["step"]] = agg.get(w["step"], ZERO) + dec(w["contribution"])
        for ev in f["inputs"].get("events", []):
            if ev["title"] not in titles:
                titles.append(ev["title"])
        if d.get("clamp_bound") and bound is None:
            bound = d["clamp_bound"]
    items = []
    for step, c in agg.items():
        if step == "rounding" or c == ZERO:
            continue
        name = step
        if step == "guardrail":
            if not bound:
                continue
            name = bound
        pct = (c * HUNDRED / total_base) if total_base else ZERO
        if pct.quantize(Decimal("0.1")) == ZERO:
            continue
        items.append({"step": name, "direction": "+" if c > 0 else "-", "contribution": money_str(c),
                      "percent": str(pct.quantize(Decimal("0.1")))})
    items.sort(key=lambda x: -abs(Decimal(x["percent"])))
    total = sum((dec(d["published_price"]) for d in decisions), ZERO)
    return {"items": items[:MAX_REASONS], "event_titles": titles, "source": source,
            "total_baseline": money_str(total_base), "total_price": money_str(total)}


def render_template(fx: dict, locale: str, floor: Decimal, ceiling: Decimal, symbol: str) -> list[str]:
    t = T.get(locale, T["en-IN"])
    out = []
    for it in fx["items"]:
        step = it["step"]
        key = step if step in ("ceiling", "floor", "max_daily_movement", "max_weekly_movement", "override", "kill_switch") \
            else f"{step}{it['direction']}"
        if key not in t:
            continue
        title = ", ".join(TITLE_I18N.get(x, {}).get(locale, x) for x in fx["event_titles"]) or ""
        out.append(t[key].format(pct=fmt_pct(Decimal(it["percent"])), title=title))
    out.append(t["bounds"].format(floor=fmt_money(floor, symbol), ceiling=fmt_money(ceiling, symbol)))
    return out


def cached(conn: sqlite3.Connection, decision_id: str, locale: str) -> list[str] | None:
    row = conn.execute("SELECT text FROM dp_narration WHERE decision_id = ? AND locale = ? AND gate_passed = 1",
                       (decision_id, locale)).fetchone()
    return json.loads(row[0]) if row else None


def pregenerate_demo(conn: sqlite3.Connection) -> int:
    """Replaced in Phase 6 by the LLM narrator; templates need no pre-generation."""
    return 0

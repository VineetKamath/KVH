"""/v1/metrics: every number comes from a computation, never typed in. Backtest and eval outputs are produced
by `python -m scripts.metrics` / `scripts.run_evals` (docs/metrics/*.json); live numbers are queried now."""
from __future__ import annotations

import json
import sqlite3

from app.config import REPO_ROOT

METRICS_DIR = REPO_ROOT / "docs" / "metrics"


def _load(name: str) -> dict | None:
    p = METRICS_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def metrics_payload(conn: sqlite3.Connection) -> dict:
    sel = [dict(r) for r in conn.execute(
        "SELECT as_of_date, component, champion, challenger, decision, dm_p_value, scores FROM dp_model_selection "
        "ORDER BY created_at DESC LIMIT 6")]
    for s in sel:
        s["scores"] = json.loads(s["scores"])
    narr = conn.execute("SELECT COUNT(*), SUM(gate_passed), SUM(fallback_used = 0) FROM dp_narration").fetchone()
    live = conn.execute("SELECT COUNT(*), SUM(clamp_status = 'clamped'), SUM(clamp_bound = 'ceiling'), SUM(clamp_bound = 'floor'), "
                        "SUM(clamp_bound = 'max_daily_movement'), SUM(clamp_bound = 'max_weekly_movement'), "
                        "SUM(approval_status = 'pending_approval') FROM dp_price_decision WHERE is_live = 1").fetchone()
    pending = conn.execute("SELECT COUNT(*) FROM dp_price_decision WHERE approval_status = 'pending_approval'").fetchone()[0]
    starter = {
        # organiser starter queries 1, 2, 5 and 6, recomputed on the live database
        "events_by_month": [dict(r) for r in conn.execute(
            "SELECT substr(occurred_at,1,7) AS month, SUM(event_type='search') AS searches, SUM(event_type='booking') AS bookings, "
            "SUM(event_type='cancellation') AS cancellations FROM pricing_events GROUP BY month ORDER BY month")],
        "conversion_by_lead_time": [dict(r) for r in conn.execute(
            "SELECT CASE WHEN lead_time_days <= 3 THEN '0-3' WHEN lead_time_days <= 7 THEN '4-7' WHEN lead_time_days <= 14 "
            "THEN '8-14' WHEN lead_time_days <= 30 THEN '15-30' WHEN lead_time_days <= 60 THEN '31-60' ELSE '60+' END AS lead, "
            "SUM(event_type='search') AS searches, SUM(event_type='booking') AS bookings FROM pricing_events GROUP BY lead")],
        "clamp_rate_price_history": [dict(r) for r in conn.execute(
            "SELECT CASE WHEN computed_at < '2026-08-18' THEN 'provided' ELSE 'pixelminds' END AS source, COUNT(*) AS rows, "
            "SUM(bound_clamped) AS clamped FROM price_history GROUP BY source")],
    }
    return {
        "backtest": _load("backtest.json"), "ai_evals": _load("ai_evals.json"), "model_selection": sel,
        "narration_gate": {"total": narr[0] or 0, "passed": narr[1] or 0, "llm_written": narr[2] or 0},
        "live_prices": {"total": live[0], "clamped": live[1] or 0, "ceiling": live[2] or 0, "floor": live[3] or 0,
                        "daily": live[4] or 0, "weekly": live[5] or 0, "pending_approval": pending},
        "starter_queries": starter,
    }

"""AI evals (offline by default; live when LLM_PROVIDER=anthropic and a key is set).

    python -m scripts.run_evals            → prints and writes docs/metrics/ai_evals.json

A3: impact_tag precision/recall on 30 hand-labelled feed rows (target precision >= 0.8).
A4: accepted prompts must match the expected config (target >= 18/20); malformed prompts must ALL be rejected.
A2: every template/LLM narration for the demo room's live decisions passes the numeric gate (target 100%).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import scripts  # noqa: F401
from app.ai.event_extractor.extractor import classify, feed_rows
from app.ai.llm import provider
from app.ai.whatif.parser import parse

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 8, 31)


def _match(expected: dict, got: dict) -> bool:
    for k, v in expected.items():
        if k == "factor_bounds":
            for f, b in v.items():
                gb = (got.get("factor_bounds") or {}).get(f)
                if gb is None or any(gb[kk] != vv for kk, vv in b.items()):
                    return False
        elif k == "disable_factors":
            if sorted(v) != sorted(got.get(k) or []):
                return False
        elif str(got.get(k)) != str(v):
            return False
    return True


def eval_whatif() -> dict:
    rows = [json.loads(line) for line in (ROOT / "ai/evals/whatif_prompts.jsonl").read_text(encoding="utf-8").splitlines()]
    ok_valid = ok_reject = 0
    fails = []
    for r in rows:
        out = parse(r["prompt"], TODAY)
        if r["expect"] == "accept":
            good = out["accepted"] and _match(r["config"], out["config"])
            ok_valid += good
        else:
            good = not out["accepted"]
            ok_reject += good
        if not good:
            fails.append({"prompt": r["prompt"], "expect": r["expect"], "got": out["config"], "errors": out["errors"]})
    n_valid = sum(r["expect"] == "accept" for r in rows)
    n_bad = len(rows) - n_valid
    return {"valid_parsed": ok_valid, "valid_total": n_valid, "malformed_rejected": ok_reject, "malformed_total": n_bad,
            "pass": ok_valid >= 18 and ok_reject == n_bad, "failures": fails}


def eval_events() -> dict:
    labels = {json.loads(line)["feed_id"]: json.loads(line)["impact_tag"]
              for line in (ROOT / "ai/evals/event_labels.jsonl").read_text(encoding="utf-8").splitlines()}
    per = {t: {"tp": 0, "fp": 0, "fn": 0} for t in ("minor", "moderate", "major")}
    correct = 0
    for row in feed_rows():
        pred, _ = classify(row)
        want = labels[row["feed_id"]]
        correct += pred.impact_tag == want
        if pred.impact_tag == want:
            per[want]["tp"] += 1
        else:
            per[pred.impact_tag]["fp"] += 1
            per[want]["fn"] += 1
    tp = sum(v["tp"] for v in per.values())
    fp = sum(v["fp"] for v in per.values())
    precision = tp / (tp + fp) if tp + fp else 0.0
    return {"accuracy": correct / len(labels), "micro_precision": precision,
            "per_class": {k: {"precision": v["tp"] / (v["tp"] + v["fp"]) if v["tp"] + v["fp"] else None,
                              "recall": v["tp"] / (v["tp"] + v["fn"]) if v["tp"] + v["fn"] else None} for k, v in per.items()},
            "rows": len(labels), "pass": precision >= 0.8}


def main() -> int:
    mode = "live:" + provider.MODEL_SMART if provider.available() else "offline (rules)"
    res = {"mode": mode, "whatif": eval_whatif(), "events": eval_events()}
    out = ROOT / "docs" / "metrics"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ai_evals.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({k: (v if k == "mode" else {kk: vv for kk, vv in v.items() if kk != "failures"}) for k, v in res.items()}, indent=2))
    return 0 if res["whatif"]["pass"] and res["events"]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

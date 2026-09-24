"""Phase 5 gate: HTTP contract + security controls, exercised through the real app."""
from __future__ import annotations

import ast
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TOKEN = "t" * 48
HERO = "rmt_039a87b5"
SRC = Path(__file__).resolve().parents[2] / "backend" / "src" / "app"


@pytest.fixture()
def client(db_path):
    os.environ["ADMIN_TOKEN"] = TOKEN
    os.environ["LLM_PROVIDER"] = "offline"
    from app.api import security

    for b in security.LIMITS.values():  # fresh rate-limit buckets per test
        b.state.clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _dates(client):
    bd = date.fromisoformat(client.get("/v1/health").json()["business_date"])
    return (bd + timedelta(days=45)).isoformat(), (bd + timedelta(days=47)).isoformat()


def test_public_routes_and_security_headers(client):
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["status"] in ("ok", "degraded")
    for h in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options", "Permissions-Policy"):
        assert h in r.headers
    assert "script-src 'self'" in r.headers["Content-Security-Policy"] and r.headers["X-Frame-Options"] == "DENY"
    assert client.get("/v1/catalog/cities").status_code == 200


def test_admin_routes_fail_closed_without_a_valid_token(client):
    for path in ("/v1/entities", f"/v1/prices/curve?entity_id={HERO}", "/v1/proof", "/v1/audit", "/v1/engine-config"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer wrong-token-wrong-token-wrong-token"}).status_code == 401
    assert client.get("/v1/entities", headers=auth()).status_code == 200
    r = client.post("/v1/killswitch", json={"active": True, "reason": "unauthenticated attempt"})
    assert r.status_code == 401


def test_quote_is_byte_identical_and_validated(client):
    ci, co = _dates(client)
    body = {"entity_id": HERO, "checkin_date": ci, "checkout_date": co, "party_size": 2, "session_id": "sess_api_0001",
            "locale": "kn"}
    a = client.post("/v1/quote", json=body)
    b = client.post("/v1/quote", json=body)
    assert a.status_code == 200 and a.content == b.content
    q = a.json()
    assert q["quote_id"].startswith("dpq_") and re.match(r"^\d+\.\d{2}$", q["total"]["amount"])
    assert all(isinstance(n["price"]["amount"], str) for n in q["nightly"])  # money is a string, never a JSON number
    assert client.post("/v1/quote", json={**body, "evil": 1}).status_code == 422          # extra fields forbidden
    assert client.post("/v1/quote", json={**body, "locale": "Tamil"}).status_code == 422   # BCP-47 allow-list
    assert client.post("/v1/quote", json={**body, "entity_id": "rmt_1 OR 1=1"}).status_code == 422
    assert client.post("/v1/quote", json={**body, "party_size": 99}).status_code == 422


def test_body_cap_and_safe_errors(client):
    big = {"prompt": "x" * 70_000}
    r = client.post("/v1/whatif/parse", content=json.dumps(big), headers={**auth(), "Content-Type": "application/json"})
    assert r.status_code == 413
    r = client.get("/v1/decisions/dpd_doesnotexist/explain", headers=auth())
    assert r.status_code == 404 and r.json()["error_code"] == "invalid_id"
    assert "Traceback" not in r.text and "sqlite" not in r.text.lower()


def test_rate_limit_returns_429_with_retry_after(client):
    ci, co = _dates(client)
    codes = []
    for i in range(40):
        r = client.post("/v1/quote", json={"entity_id": HERO, "checkin_date": ci, "checkout_date": co, "party_size": 1,
                                           "session_id": f"sess_rate_{i:04d}", "locale": "en-IN"})
        codes.append(r.status_code)
        if r.status_code == 429:
            assert int(r.headers["Retry-After"]) >= 1
            break
    assert 429 in codes


def test_clamp_report_explain_and_proof_endpoints(client):
    r = client.put(f"/v1/bounds/{HERO}", json={"ceiling_price": "4800.00", "reason": "tighten for API test"}, headers=auth())
    assert r.status_code == 200, r.text
    curve = client.get(f"/v1/prices/curve?entity_id={HERO}", headers=auth()).json()
    s = curve["summary"]
    assert s["clamped"] >= 1 and s["headline"].startswith(f"{s['clamped']} of {s['total']} prices clamped — ")
    clamped = next(p for p in curve["points"] if p["clamp_status"] == "clamped")
    ex = client.get(f"/v1/decisions/{clamped['decision_id']}/explain", headers=auth()).json()
    assert ex["reconstruction_ok"] is True and ex["replay_ok"] is True
    assert ex["clamp"]["bound"] and ex["raw"] != ex["published"]
    proof = client.get("/v1/proof", headers=auth()).json()
    assert proof["ok"], [c for c in proof["checks"] if not c["ok"]]


def test_whatif_parse_and_simulate_through_the_same_engine(client):
    p = client.post("/v1/whatif/parse", json={"prompt": "cap the event uplift at 5% and lower the ceiling by 10%"},
                    headers=auth()).json()
    assert p["accepted"], p
    sim = client.post("/v1/simulate", json={"entity_id": HERO, "config": p["config"], "name": "api test"}, headers=auth())
    assert sim.status_code == 200, sim.text
    out = sim.json()
    lo, hi = out["revenue_change_range_pct"]
    assert lo <= hi and out["A"]["dates"] == out["B"]["dates"] > 0
    bad = client.post("/v1/whatif/parse", json={"prompt": "set the price to 1 rupee"}, headers=auth()).json()
    assert bad["accepted"] is False and bad["errors"]


# ---------------------------------------------------------------- static code rules -------------------------------
def test_no_string_built_sql_with_user_input():
    """Every f-string passed to execute() must be marked (# noqa: S608) and build only placeholders/constants."""
    offenders = []
    for p in SRC.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"execute(?:many)?\(\s*f\"", text):
            window = text[m.start(): m.start() + 400]
            if "noqa: S608" not in window:
                offenders.append(f"{p.name}:{text[:m.start()].count(chr(10)) + 1}")
    assert not offenders, offenders


MONEY_MODULES = ["pricing", "core", "services/cycle.py", "services/quotes.py", "services/control.py", "services/reports.py",
                 "services/serialize.py", "services/narration.py", "services/config_service.py"]


def test_no_float_on_money_paths():
    bad = []
    for rel in MONEY_MODULES:
        target = SRC / rel
        files = list(target.rglob("*.py")) if target.is_dir() else [target]
        for f in files:
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
                    bad.append(f"{f.name}:{node.lineno}")
    assert not bad, bad

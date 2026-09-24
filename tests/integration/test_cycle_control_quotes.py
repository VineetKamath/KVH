"""Phase 4 gate: invariants I2, I4, I5, I6, controls, and organiser conformance after cycles and quotes."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import date, timedelta
from decimal import Decimal

from app.config import VALIDATOR
from app.core.clock import iso_in
from app.db.conn import connect
from app.services import audit, config_service, control, cycle, quotes, reports

HERO = "rmt_039a87b5"  # Udaipur, INR, daily cap 5%


def _validator_pass(db) -> bool:
    out = subprocess.run([sys.executable, str(VALIDATOR), str(db)], capture_output=True, text=True, encoding="utf-8",
                         env={"PYTHONIOENCODING": "utf-8", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")},
                         check=False)
    return out.returncode == 0 and out.stdout.strip().endswith("PASS")


def _stay(conn, offset=40):
    bd = date.fromisoformat(conn.execute("SELECT business_date FROM dp_clock").fetchone()[0])
    return bd + timedelta(days=offset), bd + timedelta(days=offset + 2)


def test_validator_passes_after_cycles_quotes_and_confirm(conn, db_path):
    out = cycle.advance_day(conn, "test", "advance for test")
    assert out["decisions"] > 0
    ci, co = _stay(conn)
    body = json.loads(quotes.get_or_create(conn, HERO, ci, co, 2, "sess_testvalidate", "en-IN"))
    assert quotes.confirm(conn, body["quote_id"])["status"] == "confirmed"
    assert _validator_pass(db_path)


def test_i2_concurrent_identical_searches_are_byte_identical_even_across_a_bounds_change(db_path):
    c0 = connect(db_path)
    ci, co = _stay(c0)
    results: list[str] = []
    errors: list[Exception] = []

    def search():
        c = connect(db_path)
        try:
            results.append(quotes.get_or_create(c, HERO, ci, co, 2, "sess_concurrent01", "hi"))
        except Exception as e:  # noqa: BLE001
            errors.append(e)
        finally:
            c.close()

    threads = [threading.Thread(target=search) for _ in range(20)]
    for i, t in enumerate(threads):
        t.start()
        if i == 10:  # the manager lowers the ceiling mid-flight: live quotes are honoured until expiry
            control.update_bounds(c0, HERO, {"ceiling_price": "5000.00"}, "test", "tighten ceiling mid-search")
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(results) == 20 and len(set(results)) == 1
    n_active = c0.execute("SELECT COUNT(*) FROM dp_quote WHERE status = 'active' AND session_id = 'sess_concurrent01'").fetchone()[0]
    assert n_active == 1
    # a repeat after the change is still the same quote (same id, same price)
    assert quotes.get_or_create(c0, HERO, ci, co, 2, "sess_concurrent01", "hi") == results[0]


def test_i4_every_stored_engine_decision_replays_exactly(conn):
    rows = conn.execute("SELECT * FROM dp_price_decision WHERE source = 'engine' AND factors NOT LIKE '%\"compact\":true%' "
                        "ORDER BY random() LIMIT 300").fetchall()
    assert rows
    for r in rows:
        again = reports.replay(conn, r)
        assert str(again.published) == r["published_price"], r["decision_id"]
        assert str(again.raw_price) == r["raw_price"]


def test_i3_sql_sweep_every_decision_reconstructs(conn):
    for r in conn.execute("SELECT baseline_price, published_price, factors FROM dp_price_decision"):
        wf = json.loads(r["factors"])["waterfall"]
        assert sum(Decimal(w["contribution"]) for w in wf) == Decimal(r["published_price"]) - Decimal(r["baseline_price"])


def test_i5_unapproved_signal_changes_no_price(conn):
    params = config_service.engine_params(conn)
    bd = date.fromisoformat(conn.execute("SELECT business_date FROM dp_clock").fetchone()[0])
    city = conn.execute("SELECT city_id FROM dp_catalog_link WHERE room_type_id = ?", (HERO,)).fetchone()[0]
    before, _ = cycle.price_all(conn, bd, "reprice", params, entities=[HERO])
    conn.execute("INSERT INTO dp_event_signal (signal_id, city_id, title, start_date, end_date, impact_tag, radius_km, "
                 "confidence_band, justification, source_ref, extracted_by, status, created_at, updated_at) VALUES "
                 "('dps_unapproved', ?, 'Test Mega Festival', ?, ?, 'major', '50.00', 'high', 'x', 'test', 'test', 'active', "
                 "'2026-09-24T12:00:00+05:30', '2026-09-24T12:00:00+05:30')",
                 (city, (bd + timedelta(days=1)).isoformat(), (bd + timedelta(days=60)).isoformat()))
    after, _ = cycle.price_all(conn, bd, "reprice", params, entities=[HERO])
    assert [p.decision.published for p in before] == [p.decision.published for p in after]
    control.approve_signal(conn, "dps_unapproved", "test", "approve for contrast")
    approved, _ = cycle.price_all(conn, bd, "reprice", params, entities=[HERO])
    assert any(a.decision.raw_price > b.decision.raw_price for a, b in zip(approved, before))


def test_i6_clamp_report_is_consistent(conn):
    control.update_bounds(conn, HERO, {"ceiling_price": "4800.00"}, "test", "force ceiling clamps")
    s = reports.clamp_summary(conn, HERO)
    rows = conn.execute("SELECT clamp_status, clamp_bound, source, published_price, bound_value FROM dp_price_decision "
                        "WHERE entity_id = ? AND is_live = 1", (HERO,)).fetchall()
    assert s["total"] == len(rows)
    assert s["clamped"] == sum(r["clamp_status"] == "clamped" for r in rows) > 0
    assert s["by_bound"]["ceiling"] >= 1
    assert sum(s["by_bound"].values()) == s["clamped"]
    assert s["headline"].startswith(f"{s['clamped']} of {s['total']} prices clamped — ")
    for r in rows:
        if r["clamp_bound"] == "ceiling":
            assert Decimal(r["published_price"]) <= Decimal("4800.00") and r["bound_value"] == "4800.00"
    ph = dict(conn.execute("SELECT effective_date, bound_clamped FROM price_history WHERE entity_id = ? "
                           "AND effective_date > '2026-08-31'", (HERO,)).fetchall())
    live = dict(conn.execute("SELECT for_date, clamp_status = 'clamped' FROM dp_price_decision WHERE entity_id = ? "
                             "AND is_live = 1", (HERO,)).fetchall())
    for d, clamped in live.items():
        assert ph[d] == clamped


def test_kill_switch_reverts_to_baseline_and_is_never_counted(conn):
    control.set_kill_switch(conn, True, "test", "emergency revert")
    rows = conn.execute("SELECT published_price, baseline_price, source, clamp_status FROM dp_price_decision "
                        "WHERE is_live = 1").fetchall()
    assert all(r["source"] == "kill_switch" and r["clamp_status"] == "not_applicable" for r in rows)
    assert all(r["published_price"] == r["baseline_price"] for r in rows)
    assert reports.clamp_summary(conn, HERO)["clamped"] == 0
    control.set_kill_switch(conn, False, "test", "resume")
    assert conn.execute("SELECT COUNT(*) FROM dp_price_decision WHERE is_live = 1 AND source = 'kill_switch'").fetchone()[0] == 0


def test_override_inside_bounds_applies_and_outside_is_rejected(conn):
    import pytest

    from app.services.errors import AppError

    ci, _ = _stay(conn, 20)
    b = config_service.bounds_for(conn, "room_type", HERO)
    with pytest.raises(AppError) as e:
        control.create_override(conn, HERO, ci, ci, b.ceiling + 1, "too high for bounds", iso_in(3600), "test")
    assert e.value.error_code == "constraint_infeasible"
    out = control.create_override(conn, HERO, ci, ci, Decimal("5555.00"), "VIP group block", iso_in(3600), "test")
    live = conn.execute("SELECT published_price, source, clamp_status FROM dp_price_decision WHERE entity_id = ? "
                        "AND for_date = ? AND is_live = 1", (HERO, ci.isoformat())).fetchone()
    assert live["published_price"] == "5555.00" and live["source"] == "override" and live["clamp_status"] == "not_applicable"
    assert conn.execute("SELECT override_active FROM price_bounds WHERE entity_id = ?", (HERO,)).fetchone()[0] == 1
    control.revoke_override(conn, out["override_id"], "test", "block released")
    assert conn.execute("SELECT override_active FROM price_bounds WHERE entity_id = ?", (HERO,)).fetchone()[0] == 0


def test_approval_queue_holds_large_moves_until_a_human_decides(conn):
    control.update_engine(conn, "test", "tiny auto band to force approvals", None, "0.10")
    cycle.advance_day(conn, "test", "day with moves")
    pending = conn.execute("SELECT decision_id, entity_id, for_date, published_price FROM dp_price_decision "
                           "WHERE approval_status = 'pending_approval' LIMIT 1").fetchone()
    assert pending is not None
    control.decide_approval(conn, pending["decision_id"], "approve", "checked, fine", "test")
    live = conn.execute("SELECT decision_id FROM dp_price_decision WHERE entity_id = ? AND for_date = ? AND is_live = 1",
                        (pending["entity_id"], pending["for_date"])).fetchone()
    assert live["decision_id"] == pending["decision_id"]


def test_audit_chain_verifies_and_is_append_only(conn):
    import pytest

    control.set_kill_switch(conn, True, "test", "chain test")
    assert audit.verify(conn)["ok"]
    with pytest.raises(Exception):
        conn.execute("DELETE FROM dp_audit_log")
    with pytest.raises(Exception):
        conn.execute("UPDATE dp_audit_log SET actor = 'mallory'")


def test_quote_rules_sold_out_and_expiry(conn):
    import pytest

    from app.services.errors import AppError

    ci, co = _stay(conn, 30)
    conn.execute("UPDATE inventory_calendar SET booked_units = total_units - held_units WHERE entity_id = ? AND for_date = ?",
                 (HERO, ci.isoformat()))
    with pytest.raises(AppError) as e:
        quotes.get_or_create(conn, HERO, ci, co, 2, "sess_soldout01", "en-IN")
    assert e.value.error_code == "sold_out"
    ci2, co2 = _stay(conn, 50)
    body = json.loads(quotes.get_or_create(conn, HERO, ci2, co2, 2, "sess_expire01", "en-IN"))
    conn.execute("UPDATE dp_quote SET expires_at = '2000-01-01T00:00:00+05:30' WHERE quote_id = ?", (body["quote_id"],))
    with pytest.raises(AppError) as e2:
        quotes.confirm(conn, body["quote_id"])
    assert e2.value.error_code == "hold_expired"

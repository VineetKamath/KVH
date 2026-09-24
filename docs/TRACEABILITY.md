# Traceability: requirement → code → test → demo click

Paths are relative to `Solution/`. Backend code is under `backend/src/app/` and frontend code under
`frontend/src/`. Revenue Desk screens are named as in the left rail.

| # | Requirement | Code | Test / evidence | Where to see it |
|---|---|---|---|---|
| R01 | Prices respond to demand, forecasts and events | `pricing/factors.py`, `pricing/engine.py`, `services/cycle.py` | `tests/hard_proof/test_guardrail_chain.py`, `test_price_one_reconstructs_to_the_paisa` | Curve & clamps → click a night → waterfall |
| R02 | Every price stays inside the hotel's floor and ceiling | `pricing/guardrails.py` (`effective_bounds`, `apply_chain`) | `test_i1_published_always_within_floor_and_ceiling` (Hypothesis, corrupted inputs), `test_operating_band_only_narrows_hotel_bounds` | Proof → I1 |
| R03 | Daily and weekly movement limits | `pricing/guardrails.py` | `test_daily_movement_clamp`, `test_weekly_movement_clamp`, `test_daily_cap_respected_when_compatible_with_hard_bounds` | Curve & clamps → ◆ stamps after an approved event |
| R04 | Guardrail Clamp Report (mandatory) | `services/reports.py` (`clamp_summary`, `curve`), `charts/ClampCurve.tsx`, `pages/admin/ClampReport.tsx` | `test_i6_clamp_report_is_consistent`, `test_clamp_report_explain_and_proof_endpoints` | Curve & clamps headline and stamps |
| R05 | Explain every price (raw → published → bound) | `services/reports.py` (`explain`), `pricing/attribution.py`, `charts/Waterfall.tsx` | `test_i3_sql_sweep_every_decision_reconstructs`, `test_i4_every_stored_engine_decision_replays_exactly` | Curve & clamps → decision record |
| R06 | Demand forecasting with uncertainty | `forecast/pickup.py`, `forecast/conformal.py`, `forecast/selection.py`, `forecast/hierarchy.py` | `test_backtest_gate_matches_architecture`, `test_no_leakage_features_ignore_the_future`; `docs/METRICS.md` | Curve & clamps forecast fan; Metrics |
| R07 | Accuracy that generalises, not tuned to the dataset | `forecast/defaults.py` (all constants), `forecast/reference_rate.py`, `forecast/backtest.py` (hindsight oracle) | `test_no_fitted_literals_outside_defaults`, `test_persistent_multi_night_premium_is_kept` | Metrics → "How close to the best possible?" |
| R08 | Stable, noise-free price curve | `forecast/reference_rate.py`, `services/seeding.py` | `test_independent_jitter_is_removed_and_weekday_profile_recovered` | Curve & clamps curve (smooth weekday and weekend runs) |
| R09 | Genuine, working AI feature | `ai/narrator/`, `ai/whatif/parser.py`, `ai/event_extractor/`, `ai/anomaly_summary.py` | `python -m scripts.run_evals` → `docs/metrics/ai_evals.json`; `test_whatif_parse_and_simulate_through_the_same_engine` | What-if; Curve & clamps drawer → narrate |
| R10 | At least one Indian language | `i18n/hi.json`, `i18n/kn.json`, `lib/money.ts` (native digits), `services/narration.py` | Vitest `money.test.ts` (digits change, value doesn't) | Traveller header → EN / हि / ಕ |
| R11 | English as the primary language | `i18n/index.ts` (`lng: "en-IN"`), `lib/locale.ts` | screenshot `01-home.png` (EN selected on first load) | open `/` in a fresh browser |
| R12 | Coherent travel portal | `pages/traveller/*` | screenshots 01–06 | `/` → search → results → Price Pass |
| R13 | Stable quotes (the same search gives the same price) | `services/quotes.py` | `test_i2_concurrent_identical_searches_are_byte_identical_even_across_a_bounds_change`, `test_quote_is_byte_identical_and_validated` | Price Pass → "Open in a new tab" shows the same pass no. |
| R14 | Sold-out, expiry, min-stay rules | `services/quotes.py` | `test_quote_rules_sold_out_and_expiry` | Price Pass countdown |
| R15 | Manager controls: bounds, overrides, kill switch | `services/control.py`, `services/config_service.py`, `pages/admin/Controls.tsx` | `test_override_inside_bounds_applies_and_outside_is_rejected`, `test_kill_switch_reverts_to_baseline_and_is_never_counted` | Controls |
| R16 | Operating band (realistic floor and ceiling) | `pricing/params.py`, `pricing/engine.py` (`operating_band`), `contracts/models.py` (`EngineUpdate`) | `test_operating_band_only_narrows_hotel_bounds` | Controls → Engine settings → Max % below/above ref. |
| R17 | Approval of large or unusual moves | `pricing/anomaly.py`, `services/cycle.py` (gate), `pages/admin/Approvals.tsx` | `test_approval_queue_holds_large_moves_until_a_human_decides` | Approvals |
| R18 | Events only affect prices after human approval | `services/cycle.py` (`_approved_signals`), `pages/admin/Signals.tsx` | `test_i5_unapproved_signal_changes_no_price` | Event signals → Approve → Curve & clamps reprices |
| R19 | What-if before shipping | `services/simulator.py`, `ai/whatif/parser.py` | `test_whatif_parse_and_simulate_through_the_same_engine`; A4 eval 20/20, 8/8 rejected | What-if |
| R20 | Audit trail | `services/audit.py`, `dp_audit_log` triggers | `test_audit_chain_verifies_and_is_append_only` | Audit (chain verified) |
| R21 | Canonical data untouched; validator passes | `db/conn.py` (`connect_readonly`), `services/proof.py`, `services/tier2.py` | `test_organiser_files_match_sha256sums`, `test_validator_passes_after_cycles_quotes_and_confirm` | Proof |
| R22 | Money never touches a float | `core/money.py`, `lib/money.ts` | `test_no_float_on_money_paths`, `test_dec_never_goes_through_float_arithmetic`, `test_largest_remainder_always_sums_exactly` | — |
| R23 | Business clock, deterministic replay | `core/clock.py`, `dp_clock` | `test_pure_modules_do_no_io_and_read_no_clock` | Desk rail → Business date → Advance day |
| R24 | Security (auth, limits, headers, no injection) | `api/security.py`, `main.py` | `test_admin_routes_fail_closed_without_a_valid_token`, `test_rate_limit_returns_429_with_retry_after`, `test_body_cap_and_safe_errors`, `test_public_routes_and_security_headers`, `test_no_string_built_sql_with_user_input` | `docs/SECURITY.md` |

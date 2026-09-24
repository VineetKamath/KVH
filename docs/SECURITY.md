# Security

**Scope:** a single-process web app (FastAPI + a built React bundle on one origin) over one SQLite file.
There are two trust levels:

- **Public:** traveller catalog, quotes and booking confirmation.
- **Admin:** the Revenue Desk, authenticated by one bearer token (`ADMIN_TOKEN` in `.env`).

## STRIDE threat model

| Threat | Where | Control | Evidence (test / check) |
|---|---|---|---|
| **S**poofing an admin | every `/v1/*` admin route | Bearer token compared with `hmac.compare_digest`. A missing or short token (< 32 chars) refuses every admin call (fail closed). The token lives only in tab memory, never in `localStorage` or cookies. | `test_admin_routes_fail_closed_without_a_valid_token` |
| **T**ampering with prices | pricing core | Prices come only from `price_one`. No LLM output can set a price. The hotel's bounds are enforced in the engine and re-checked over every live row. | `test_i1_published_always_within_floor_and_ceiling` (Hypothesis, corrupted inputs); Proof I1 |
| **T**ampering with history | `dp_audit_log` | Append-only: triggers reject UPDATE and DELETE. Each row carries the SHA-256 of the previous row, and `/v1/audit/verify` walks the chain. | `test_audit_chain_verifies_and_is_append_only`; Proof |
| **T**ampering with organiser data | `DynamicPricing/` | Opened read-only (`mode=ro`), never written, and verified against `SHA256SUMS.txt` (29 files). | `test_organiser_files_match_sha256sums`; Proof |
| **T**ampering via SQL injection | all queries | Parameterised SQL only. IN-lists go through `json_each(?)`. No string-built SQL. | `test_no_string_built_sql_with_user_input` (AST scan) |
| **R**epudiation | admin actions | Every bounds, engine, override, kill-switch, approval and signal change records actor, reason (required, 5–300 chars), before and after. | `test_audit_chain_verifies_and_is_append_only`; Audit |
| **I**nformation disclosure | errors, headers | Errors are `{error_code, message, request_id}`; details go to the server log only. `Cache-Control: no-store`, `Referrer-Policy: no-referrer`. `.env` is git-ignored. | `test_body_cap_and_safe_errors`; `test_public_routes_and_security_headers` |
| **I**nformation disclosure via the UI | browser | Strict CSP (`default-src 'self'`, no inline script, `frame-ancestors 'none'`, `object-src 'none'`), `X-Frame-Options: DENY`, `nosniff`, COOP same-origin. React escapes all text, and i18n interpolation never injects HTML. | `test_public_routes_and_security_headers` |
| **D**enial of service | quotes, LLM routes | Per-IP token-bucket limits (tighter on quotes and LLM-backed routes) → 429 with `Retry-After`. 64 KB body cap. LLM calls time out and fall back to templates. | `test_rate_limit_returns_429_with_retry_after`; `test_body_cap_and_safe_errors` |
| **E**levation via AI | A3 / A4 | A3 signals are inert until a person approves them. A4 output must validate against a strict `WhatIfConfig`, and unknown fields or out-of-range values are rejected, never coerced. | `test_i5_unapproved_signal_changes_no_price`; A4 eval 8/8 malformed rejected; `test_whatif_parse_and_simulate_through_the_same_engine` |
| **E**levation via money bugs | money paths | Decimal end to end with banker's rounding. No float arithmetic on prices (AST scan). | `test_no_float_on_money_paths`; `test_dec_never_goes_through_float_arithmetic` |

## Scan outputs (run on this build)

**bandit** (`python -m bandit -r backend/src -q`):
```
Total issues (by severity):  Undefined: 0  Low: 2  Medium: 0  High: 0
>> B404 subprocess import            backend/src/app/services/proof.py:7
>> B603 subprocess without shell     backend/src/app/services/proof.py:73
```
Both low findings are the fixed-argument call that runs the organiser's own `validate_conformance.py` on
the Proof page. There's no shell, and no user input reaches the arguments.

**pip-audit** (`backend/requirements.txt` and `backend/requirements-dev.txt`):
```
No known vulnerabilities found
No known vulnerabilities found
```
python-dotenv was upgraded to 1.2.2 and pytest to 9.0.3 during the build to clear earlier advisories.

**npm audit** (`npm audit --audit-level=high`, `frontend/`):
```
found 0 vulnerabilities
```

## Operational notes

- Rotate the admin token by editing `ADMIN_TOKEN` in `.env` and restarting. A new seed writes a fresh one.
- The server binds to `127.0.0.1` by default. For a network deployment, put it behind TLS and set
  `WEB_ORIGIN` for CORS (only `GET`/`POST`/`PUT` with `Authorization` and `Content-Type` are allowed).
- The LLM provider is off unless `LLM_PROVIDER=anthropic` and a key are set. Prompts contain only
  decision numbers and factor names, never personal data.

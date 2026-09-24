# Architecture note: Rate Ledger (PixelMinds, APS-02)

*Two pages. The full design is in `ARCHITECTURE.md`; the decisions taken during the build are in
`DECISIONS.md`.*

## Shape
One process on one port. FastAPI serves the JSON API (`/v1/*`) and the built React bundle from the same
origin. State is one SQLite file (`var/pricing.db`, WAL mode). It is a byte-for-byte copy of the
organiser's `APS-02.db` plus 16 `dp_` tables. The organiser file is opened read-only and verified by
SHA-256. There is no Docker, no queue and no external service. The LLM is optional and off by default.

```
Browser (traveller portal · Revenue Desk)
        │  same origin, JSON, bearer token for /desk (tab memory only)
FastAPI ── security middleware (CSP, rate limits, 64 KB cap, safe errors)
   ├─ services/  cycle · quotes · control · reports · simulator · proof · audit
   ├─ pricing/   pure: factors → guardrails → attribution   (Decimal only, no I/O, no clock)
   ├─ forecast/  pure: panel → reference rate → pickup → conformal → selection → credibility
   └─ ai/        provider (offline | anthropic) · narrator + numeric gate · extractor · what-if parser
SQLite: 13 canonical tables (unchanged schema) + 16 dp_ tables (versions, decisions, audit chain …)
```

## The pricing cycle (once per business day, or on any control change)
1. **Forecast state** for the business date. It is fitted at most weekly and cached. The model selection
   is recorded.
2. For every room × night (117 rooms × 90 nights = 10,530 prices):
   - **reference rate** × 8 bounded factors → **raw price**;
   - guardrails in a fixed order: weekly move → daily move → floor/ceiling (the hotel's bounds ∩ the
     operating band) → round inward → **published**.
3. **Approval gate.** Moves beyond the auto-apply band, or robust-z anomalies, wait for a person, and the
   old price stays live.
4. **Atomic publish** in one `BEGIN IMMEDIATE` transaction: decisions (inputs, factors, clamp chain,
   waterfall), features, forecasts, canonical write-back (`inventory_calendar.price`, `price_history`),
   and an audit row.

A quote reads published prices only (no forecast or LLM on the traveller's path), holds them for 15
minutes, and is byte-identical for identical searches.

## Why prices are stable and realistic
- **Reference rate (D-17).** The organiser's nightly rate has about ±7% of independent jitter per night. We
  keep the room level, a weekday profile shrunk toward the portfolio, and a 29-night trend. Night-specific
  deviations are kept in proportion to their measured persistence (ρ = 0.0 here). Night-to-night movement
  within a weekday or weekend run fell from about 11% to 1.3%.
- **Operating band (D-18).** The provided bounds are 0.75×–1.85× of base for every room. The engine may
  move at most −20% / +35% from the night's reference. The band only narrows the hotel's bounds, and it is
  versioned and editable.
- **Credibility.** The forecast moves a price only as far as its evidence allows: Bühlmann pooling
  city → region → national, and an uncertainty damper.

## Forecasting
Pickup P50 (bookings on the books plus expected late bookings from the learned lead-time curve), with a
split-conformal P10–P90 band. Champion and challengers (pickup, LightGBM quantile, naive) are compared by
Poisson deviance with a Diebold–Mariano test, and naive is the fallback. Every constant lives in
`forecast/defaults.py`, and a test forbids fitted literals anywhere else. Results
(`docs/METRICS.md`, held-out June–July 2026):
- national weekly accuracy is 88.5%, against a hindsight oracle's 90.4%;
- national daily accuracy is 63.7%, above the oracle's 55.7% because the model also uses bookings on the
  books;
- 95.7% of city-weeks are within ±1 booking;
- the band covers 81.0% against an 80% target.

## Explainability and proof
- **I1:** every live price is inside its bounds.
- **I2:** quotes are byte-identical.
- **I3:** the waterfall sums to the paisa.
- **I4:** stored decisions replay exactly.
- **I5:** unapproved signals change nothing.
- **I6:** the Clamp Report agrees with `price_history.bound_clamped`.
- The organiser validator (Tier 1) and our Tier-2 checker pass, the audit hash chain is intact, and the
  organiser files match their checksums.

These are tested in `pytest` (80 tests, including Hypothesis property tests) and re-run live on the
Proof page.

## AI, gated
| Feature | Gate |
|---|---|
| A2 narrator (en-IN / hi / kn) | numeric gate on every digit, else a template |
| A3 event extractor | signals inert until approved |
| A4 what-if parser | strict schema; unknown input rejected (20/20 parsed, 8/8 malformed rejected) |
| A5 anomaly one-liner | flags from a statistical test, not the LLM |

No model ever sets a price.

## Security
Constant-time bearer auth that fails closed, per-IP rate limits, a body cap, strict CSP and security
headers, parameterised SQL only, Decimal money end to end, and an append-only audit chain.
`bandit`: 0 high/medium. `pip-audit` and `npm audit`: clean. See `SECURITY.md`.

## Cut, deliberately
Flight pricing (one calendar row per fare), a revenue optimiser (no measurable price response in the
data), a Postgres runtime (documented path only), and live A/B splits.

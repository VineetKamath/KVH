# Solution write-up: Rate Ledger

*PixelMinds · APS-02 Real-Time Dynamic Pricing & Demand Forecasting. The sections follow the Solution
Submission Template, so each one can be pasted into the matching field.*

## 1. Team
PixelMinds: Siddhant Patil, Vineet R Kamath, Manoj Kumar N, Srijan Vachadmath, Manohara Salmani.

## 2. Problem
Hotels need prices that respond to demand, but managers don't trust a black box. Automated prices jump
around, cross limits the hotel cares about, and can't be explained to a guest or an auditor. Travellers
see prices change between two tabs and assume they are being played.

## 3. What we built
**Rate Ledger**, a transparent dynamic-pricing system for hotels with two surfaces on one product:
- **Traveller portal.** Search, live prices with a 90-night trail, and a **Price Pass**: a held,
  byte-stable quote with a plain-language "Why this price?" in English, हिन्दी or ಕನ್ನಡ.
- **Revenue Desk.** The price curve with the allowed range per night, the **Guardrail Clamp Report**, a
  decision record for every price (reference → raw → published, limits, exact waterfall), approvals,
  controls (bounds, operating band, overrides, kill switch), event signals, a what-if simulator, metrics,
  a hash-chained audit log, and a live proof page.

## 4. How it works
1. The **reference rate** is the hotel's rate card with night-to-night noise removed. The weekday profile
   and slow trend are kept, and date-specific pricing is kept only when it persists.
2. **Demand forecast.** Pickup (bookings on the books plus expected late bookings from the lead-time
   curve), a conformal P10–P90 band, and automatic champion/challenger selection. It is pooled
   city → region → national by credibility, so thin data moves prices less.
3. **Eight bounded factors:** seasonality, demand, booking pace, lead time, approved events, competitor
   parity (simulated), cancellation risk, and an uncertainty damper.
4. **Guardrails:** weekly and daily move caps, then the hotel's floor and ceiling narrowed by the operating
   band, then rounding inward. Hotel limits always win.
5. **Approval gate** for large or anomalous moves. **Ledger:** every decision reconstructs to the paisa
   and replays exactly, and the audit log is append-only and hash-chained.

## 5. AI features and how we know they work
| Feature | Evidence |
|---|---|
| Forecaster | held-out backtest through production code: national weekly accuracy 88.5% (naive 87.0%, a hindsight oracle that sees the future 90.4%); 95.7% of city-weeks within ±1 booking; band coverage 81.0% vs 80% target |
| Narrator (Claude Haiku 4.5, or a template offline) | numeric gate: every digit must exist in the decision, with Devanagari and Kannada digits normalised |
| What-if parser (Claude Sonnet 5, or rules offline) | 20/20 prompts parsed; 8/8 malformed prompts rejected |
| Event extractor | signals are inert until a person approves them; 30 labelled rows (offline rules share authors with the labels, as disclosed) |

## 6. Use of the provided data model
- The 13 canonical tables keep their schema unchanged. We add 16 `dp_` tables and write back only what a
  live system would (`inventory_calendar` price and holds, `price_history`, booking events).
- The organiser's validator passes on the live database, our Tier-2 checker covers the tables it skips,
  and R1–R8 are enforced by tests.
- The organiser folder is never modified and is SHA-256 verified.

## 7. What we found in the data and how we responded
| Finding | Response |
|---|---|
| The nightly rate has ±7% independent jitter; neighbouring nights swung 11% | Reference rate. Moves within a weekday or weekend run are now 1.3%. |
| Every room's ceiling is exactly 2.467× its floor (0.75×–1.85× base) | Operating band of −20% / +35% around the reference: editable, audited, only ever narrower |
| Bookings are a constant-rate Poisson process of about 0.08 per city-night | Credibility pooling. Accuracy reported against a hindsight oracle and with small-count measures instead of a misleading headline. |
| No measurable price response (elasticity about 0) | No optimiser claim. The simulator uses a stated prior with a range. |

## 8. Scope cut, and why
- **Flight pricing:** the data has one calendar row per fare.
- **Revenue optimiser:** no price-response signal in the data to optimise against.
- **Postgres runtime:** documented, but SQLite fits one writer at about 10k rows per cycle.
- **Live A/B split:** replaced by the what-if simulator on the same engine.

## 9. Quality
- 80 backend tests, including property tests over corrupted inputs, and 5 frontend tests.
- Live proof page, all green.
- `bandit`: 0 high/medium. `pip-audit` and `npm audit`: 0 vulnerabilities.
- Decimal money end to end, and no string-built SQL.

## 10. Run it
`scripts/start.ps1` (Windows) or `sh scripts/start.sh` (macOS/Linux), then open http://127.0.0.1:8000.
The admin token is in `.env`.

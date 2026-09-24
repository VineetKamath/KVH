# Decisions made during the build

Each entry says what we decided, why, and what backs it. Numbers come from the organiser data (read-only)
or from `docs/metrics/*.json`. `ARCHITECTURE.md` stays the design of record; its Appendix C lists these
deviations.

## D-01 stdlib `sqlite3` instead of SQLAlchemy Core
A single SQLite file, hand-written SQL that must match the organiser's canonical DDL exactly, and
transactions we control (`BEGIN IMMEDIATE`, WAL). An ORM or query builder added a layer without removing
any risk. Every statement is parameterised, and a test (`test_no_string_built_sql_with_user_input`) fails
the build on string-built SQL.

## D-02 Symmetric uncertainty damper, bounds 0.94–1.06
The damper pulls the price back toward the reference in proportion to forecast width:
`multiplier = (product of the other factors) ** −s`, with `s = s_max · w / (w + 1)`. A one-sided damper
(0.94–1.00) would only soften mark-ups and silently bias prices down when data is thin. The symmetric form
also softens markdowns, so uncertainty means "move less" in both directions.

## D-03 Rounding after the hard clamp, inward to the allowed interval
Rounding to the hotel's step (e.g. ₹10) happens last, toward the inside of the interval that satisfies
every guardrail. Rounding can therefore never push a price outside the floor, the ceiling or a movement
cap, and on its own it is never counted as a clamp (`test_rounding_alone_is_not_a_clamp_and_never_breaches`).

## D-04 Hard bounds beat movement caps
When a manager lowers a ceiling below yesterday's price, the ceiling wins even if that means a larger move
than the daily cap. A limit the hotel set explicitly outranks a smoothing rule
(`test_ceiling_beats_daily_when_ceiling_dropped_below_daily_window`).

## D-05 Exact attribution with largest-remainder rounding
The waterfall telescopes multiplicatively, and the rounded contributions are adjusted by
largest-remainder so they sum exactly to published − reference, to the paisa, for every decision
(invariant I3, swept in SQL over all live rows).

## D-06 Money is a decimal string end to end
Python uses `Decimal` with banker's rounding. The API carries `{"amount": "5200.00", "currency": "INR"}`.
The UI formats the string with `Intl` and never does float arithmetic on a price. An AST test rejects
`float(` on money paths.

## D-07 Approval gate after all moves are known
Anomalies are judged against the room's own move distribution in the same cycle (robust z-score), so the
gate runs after every price is computed. The previous price stays live until a person decides.

## D-08 Compact storage for early warm-up days
The 15-day warm-up replay initially produced a 756 MB database. For early warm-up days, decisions keep
their inputs, price, clamp and waterfall, but per-day feature and forecast rows are not stored. The seeded
database is now about 390 MB. Compact decisions are marked, and replay (I4) is proven on the full ones.

## D-09 Events are stamped on the business clock
Everything the engine writes is dated by the business clock (`dp_clock`), not the wall clock, so replays
and demos are deterministic. The wall clock is used only for `created_at`/`updated_at` audit stamps and
quote expiry.

## D-10 Hierarchical Bühlmann credibility, κ from over-time variance
The first estimator (method of moments across cities at one point in time) gave κ = ∞: all cross-city
spread looked like noise, so demand was ignored completely. City-level jitter also caused about 80% daily
clamps. κ is now estimated per level from the over-time signal variance of each series (city κ ≈ 4,
region ≈ 14, national ∞), and cities shrink toward their region, which shrinks toward the nation.

## D-11 Champion/challenger selection at the 7-day grain
The demand factor uses a centred 7-day window, so models are compared on 7-day sums (Poisson deviance,
Diebold–Mariano test). A challenger must beat the champion significantly, and if every model loses to
naive, naive is used. The decision is recorded in `dp_model_selection` at every fit.

## D-12 Custom SVG for the clamp curve
Each clamped night needs its own marker shape, a ghost dot at the raw price, a whisker to the published
price, and a per-night allowed-range band. General chart libraries don't draw that per-point geometry
cleanly. Recharts is still used for the forecast fan and bar charts.

## D-13 Seasonality detrended by ratio-to-moving-average
The data ramps up from August 2025, and a plain month index read that ramp as seasonality. Each month is
now compared with the average of its neighbours, and a month without both neighbours contributes no
evidence. On this data every index shrinks to 1.0. If a deployment has real seasonality, the indices grow
automatically.

## D-14 Hand-built UI primitives instead of shadcn; React 19 / Vite 8; Tailwind 4
The "Rate Ledger" identity (stamps, perforation, ledger rules, mono numerals) is a small set of components
on design tokens. A component library would have brought a generic look and a larger bundle. React 19 and
Vite 8 were current at build time. `npm audit` shows 0 vulnerabilities.

## D-15 anthropic SDK 1.8.0 with structured output; offline by default
All LLM calls go through `ai/llm/provider.py` and `messages.parse(output_format=…)` into strict Pydantic
models, with a timeout and a recorded prompt version. `LLM_PROVIDER=offline` is the default, so the system
runs fully without a key, using templates and rules.

## D-16 Small behaviours worth recording
- **IN-lists use `json_each`**, so there is never string-built SQL, even for lists of ids.
- **Releasing the kill switch counts as manager approval** for the moves it releases. Otherwise the
  approval queue floods with hundreds of moves back from the base rate.
- **A live quote is honoured until it expires**, even if prices or bounds change mid-hold. Two identical
  searches in the window return byte-identical responses (I2).
- **The conformal band beat LightGBM quantile** on this data (coverage 81.0% vs 88.3%, interval score
  2.198 vs 2.276). Selection is automatic, so a deployment where LightGBM wins will use it.

## D-17 Price baseline = reference rate, not the raw nightly rate

**Problem.** Reviewers saw the price curve zig-zag between neighbouring nights. Measured on the hero room
and on all 117 rooms, consecutive nights differed by 11.4% on average (up to 35%). We traced every source:

| Source of night-to-night movement | Mean \|log change\| between nights |
|---|---|
| Provided nightly rate (`inventory_calendar.price`), used as baseline | 11.8% |
| All 8 pricing factors together | 1.4% |

So the engine was not bouncing. It passed the rate card's jitter straight through. The provided rate is a
weekday/weekend profile (Fri–Sun about 22% above Mon–Thu) plus independent noise of about 7% per night.
That noise is unrelated to occupancy (correlation 0.005) and doesn't persist: after removing the weekday
effect, the lag-1 autocorrelation of the residual is 0.0.

**Decision.** The baseline is a *reference rate* per room and night (`app/forecast/reference_rate.py`):
room level × weekday profile (per room, shrunk toward the all-room profile by empirical Bayes) × a 29-night
centred trend. On top of that, the night-specific residual is kept with weight ρ, the pooled lag-1
autocorrelation of residuals.

**Why this generalises.** Nothing is tuned to APS-02.db.
- ρ is measured from whatever calendar is supplied. Deliberate date pricing that lasts several nights (a
  festival week) is autocorrelated, so ρ rises and the reference keeps it. `tests/unit/test_reference_rate.py`
  checks this on a synthetic calendar: the festival price is kept to within 10%.
- Independent jitter has ρ ≈ 0 and is dropped. The same test checks the jitter is removed and the weekday
  profile is recovered.
- Events a hotel wants priced still enter explicitly, through approved event signals.

**Result** (reseeded DB, all rooms, business date 2026-08-31): within a weekday run or a weekend run, the
published price now moves 1.3% per night on average (p90 2.6%), against about 11% before. The only large
steps left are the hotel's own weekend premium. The seed audit row records ρ, the weekday profile and the
before/after jitter.

## D-18 Operating band around the reference rate

**Problem.** The provided `price_bounds` are the same shape for every one of the 1,500 rows: the ceiling is
2.467× the floor, which is 0.75× to 1.85× of the room's base. For the hero room that is ₹3,682 to ₹9,083
around a ₹5,200 weekday rate. No hotel moves a published rate over that range, so the floor and ceiling
never meant anything on the curve.

**Decision.** An *operating band* is set in the engine configuration:
- the engine may publish at most 20% below or 35% above the night's reference rate;
- the band only **narrows** the hotel's bounds, never widens them (`guardrails.effective_bounds`);
- a clamp at the band is still recorded as `floor`/`ceiling` (the canonical enum), with
  `basis: "operating_band"` in the clamp chain, so the drawer says which limit applied.

This is a stated business policy, like the factor bounds. It isn't fitted to the data. It is versioned,
audited and editable in Controls (`PUT /v1/engine-config` with `band_below_pct`/`band_above_pct`).
Configs written before D-18 have no band, so their decisions still replay byte-for-byte (invariant I4).

**Precedence.** Hotel bounds ∩ band are hard: they win over the daily and weekly movement caps. This is
the same rule that already applies when a manager lowers a ceiling.
`tests/hard_proof/test_bounds_invariant.py::test_operating_band_only_narrows_hotel_bounds` checks the band
on 200 generated cases, including corrupted inputs.

## D-19 Forecast accuracy is reported against a hindsight oracle

**Problem.** "63.7% daily accuracy" reads as poor with no reference point. The provided bookings are a
constant-rate random process: about 3.3 per day nationally, flat by month, with variance equal to the mean
(dispersion 1.04, i.e. Poisson). Part of the error is therefore randomness that no model can remove.

**Decision.** The backtest also scores a *hindsight oracle* at every level and grain. The oracle cheats: it
predicts each day with the realised average of the surrounding 29 days. It is a benchmark only and never
used for pricing. Results (`docs/METRICS.md`):
- our model is within 2 points of the oracle at national × week (88.5% vs 90.4%);
- it beats the oracle at national × day (63.7% vs 55.7%) and region × week (63.5% vs 62.7%), because it
  also uses bookings already on the books.

At city level even the oracle scores about 0% (0.4 bookings per city per week), which is why the demand
signal pools city → region → national by credibility. We didn't push the headline number up by tuning to
this dataset. The only headroom left is the gap to a model that sees the future.

## D-20 English is the primary language; the UI explains the product
The app opens in English. हिन्दी and ಕನ್ನಡ are one click away, with native digits and identical values.
Older stored language choices are ignored (the storage key changed to `rl.locale.v2`). The traveller home
page now states what the product is ("Hotel prices that explain themselves") and shows how a price is made:
reference rate → demand → forecast → event → hotel limit → published. A breakdown on the home page is
clearly labelled as an illustration, and every other number on screen is live. The Revenue Desk is laid
out as a control room: a dark navigation rail grouped Pricing / Analysis / Record, a context bar, and a
pricing-state strip above the curve.

## D-21 Model selection is recorded even when a fit comes from the disk cache
Fitted forecast states are cached in `var/models/`, and that cache survives a reseed. A fit loaded from
disk used to skip writing `dp_model_selection`, so a freshly seeded database showed no champion/challenger
history. Loading from disk now records the selection if the database doesn't have it for that date.

## D-22 No simulated number moves a live price: the competitor factor is off by default
The dataset has no competitor rates, so the competitor index could only ever be simulated. It moved live
prices by up to ±6%. It is now disabled by default (`DEFAULT_OFF` in `pricing/params.py`): the factor stays
neutral (×1.000), is shown as OFF in Controls, and can be enabled, versioned and audited once a real rate
feed exists. Every live price now comes only from organiser data plus stated business policy (see
`DATA_USAGE.md`). The Revenue Desk also replaced the "§n" section markers with named, icon-labelled
sections.

# What data trains the model, and what is not organiser data

**Short answer:** every forecast and every price is computed from the organiser's `APS-02.db` and nothing
else. We never generate bookings, searches or prices. Where the dataset has no data for something a
real pricing system needs, we say so below. Those stand-ins either don't touch a price, or are switched
off by default.

The organisers describe `APS-02.db` itself as *fully synthetic* ("no real people, no personal data"). We
use all of it that belongs to hotel pricing.

## Organiser data used

| Table | Rows in APS-02.db | Used | How |
|---|---|---|---|
| `pricing_events`, hotel rows (`room_type`) | **14,234 of 20,000** | **All** | Trains the demand forecast. The history runs 13 months (Aug 2025 – Aug 2026): 1,332 bookings, 728 cancellations, 8,749 searches, 2,554 views, 871 abandons. It gives the booking rate, the lead-time pickup curve, cancellation rates, booking pace, and the features for the LightGBM challenger. The backtest in `docs/METRICS.md` runs on this table. |
| `inventory_calendar`, hotel rows | **10,530 of 15,030** | **All** | 117 rooms × 90 nights. `price` builds the reference rate (the de-noised rate card, D-17). `total/booked/held_units`, `closed_to_arrival` and `min_stay_nights` drive sold-out and stay rules in quotes. Published prices are written back here. |
| `price_bounds`, hotel rows | **1,200 of 1,500** | **All** | The hotel's floor, ceiling, daily and weekly move limits and rounding step, enforced on every price. |
| `price_history` | 5,950 | Checked and written | This is the organiser's earlier engine output, not demand, so it doesn't train the forecast. It sets the demand-factor range (its `demand_index` p5–p95), is checked by the Tier-2 conformance checker, and receives our decisions as new rows. |
| `cities`, `hotels`, `currencies`, `languages`, `countries` | 60 / 300 / 25 / 26 / 30 | Yes | City → region hierarchy for credibility pooling, hotel names and star ratings in the portal, currency symbols and minor units, language tags. |

## Organiser data deliberately not used

| Data | Rows | Why |
|---|---|---|
| `pricing_events`, flight rows | 5,766 | Flight pricing is cut: `flight_fares` has only one calendar row per fare, so there is no fare curve to price. |
| `inventory_calendar` and `price_bounds`, flight rows | 4,500 / 300 | Same reason. |
| `flights`, `flight_fares`, `airports`, `airlines` | 4,000 / 8,002 / 80 / 30 | Same reason. |

## Not from the organiser data (all disclosed in the UI)

| Item | Why it exists | Effect on prices |
|---|---|---|
| **Competitor index** | The dataset has no competitor rates. | **None by default.** The competitor factor is **switched off** (`DEFAULT_OFF` in `pricing/params.py`). A manager can enable it in Controls once real competitor rates are connected, and that change is versioned and audited. The index is always labelled "simulated". |
| **Room names and room → hotel links** | The organisers' platform has a `hotel_room_types` table, but this dataset doesn't include it. Room types appear only as ids. | None. Display only: each city-resolvable room is linked to a same-city hotel and given a readable name. Links are stored with `link_source = 'synthetic'`. |
| **Event signals** (`data-model/seed/event_signals.csv`, `event_feed.csv`) | The dataset has no events calendar. | Only after a person approves a signal. The rows are hand-curated from public calendars (Government of India gazetted holidays 2026, state tourism calendars), and each carries its source. Unapproved signals change no price (invariant I5). |
| **Operating band** (−20% / +35% around the reference rate) | The provided bounds are 0.75×–1.85× of base for every room, far wider than any real hotel would move a rate. | A stated business policy, not data: it only ever narrows the hotel's bounds, and it is editable in Controls. |
| **Elasticity prior** (what-if simulator only) | The data shows no measurable price response. | None on live prices. It is used only to give the simulator's revenue estimate as a range. |

## How to check this yourself
- Row counts: `sqlite3 DynamicPricing/data/APS-02.db "select entity_type, count(*) from pricing_events group by 1"`.
- What the forecaster reads: `backend/src/app/services/data.py` (`load_events`: `pricing_events` joined to
  `cities`, hotel rows only).
- That the organiser files are untouched: the Proof page, or `sha256sum -c SHA256SUMS.txt` in
  `DynamicPricing/`.

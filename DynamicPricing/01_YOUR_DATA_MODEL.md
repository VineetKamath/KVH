# APS-02 — your data model

**Real-Time Dynamic Pricing & Demand Forecasting**  
Kognivera Hackathon 2026 · Travel & Tourism · data model v1.1.0-rc1

> **The problem statement itself, the 24-hour MVP scope and the XR device requirement live in the hackathon application**, on your statement's page. This document is the data you have been given to build it with: every table, every field, and what each one is for.

---

You have **55,033 rows across 13 tables**. 10 of them are the tables this statement is built on; the remaining 3 are reference tables the others point at, included so the database works on its own.

All of it is in the `data/` folder beside this document: as `APS-02.db` (SQLite, indexed, ready to query), as CSV, and as DDL for Postgres and SQLite.

## What the data gives you

20,000 pricing events across **13 months** with visible seasonality and lead-time structure, 1,500 sets of price guardrails, and 5,950 rows of computed price history with the driving factors recorded alongside each one.

## Watch out for this one

About 1% of room rates are deliberate outliers. A forecast that lets them drag the curve is a forecast that has not been defended — handle them, do not assume they are a mistake in the data.

## The tables this statement is built on

| Table | Rows | What you use it for |
|---|---|---|
| `cities` | 60 | The geographic anchor of the whole model. 60 cities; every hotel, POI, package, advisory and weather row hangs off one. |
| `countries` | 30 | ISO country reference. Every city, currency default and calling code resolves here. |
| `currencies` | 25 | carries the true minor-unit exponent so JPY/KWD display correctly even though storage is always DECIMAL(12,2). |
| `flights` | 4,000 | Schedule instances across the search window, so a date search returns results rather than blanks. |
| `hotels` | 300 | Fewer, richer properties. Depth (reviews, room types, media) matters more than catalogue size —. |
| `inventory_calendar` | 15,030 | Entity x date availability with a database-level no-oversell CHECK. Deliberately scarce units so APS-05's load test has something to defend. |
| `flight_fares` | 8,002 | The bookable unit for flights, and the second entity_type in inventory_calendar. |
| `price_bounds` | 1,500 | The guardrails APS-02 must respect. A dynamic price outside these is a failing demo, not a clever one. |
| `price_history` | 5,950 | Computed price over time with the driving factors alongside — the shape APS-02's explainability requirement has to produce. |
| `pricing_events` | 20,000 | 13 months of search / booking / cancellation signal with visible seasonality — otherwise APS-02's forecast is a straight line and the price curve has nothing to explain. |

## Reference tables, included so the database is valid

You will mostly join through these rather than think about them.

| Table | Rows | What it is |
|---|---|---|
| `languages` | 26 | Rule R6: BCP-47 is the only legal way to say 'language' anywhere in the model. |
| `airlines` | 30 | Carrier reference for flight schedule instances. |
| `airports` | 80 | So flights join airport-to-airport rather than city-to-city. |

## How they fit together

Open `02_DATA_MODEL_DIAGRAM.html` in a browser for the clickable version — it shows these tables and nothing else. Download it first; it will not render inside SharePoint.

Some tables point at "any bookable thing" using an `(entity_type, entity_id)` pair rather than a typed foreign key. That is deliberate: it is what lets one feature refer to a hotel, a flight, a point of interest or a package without a separate join table for each. The legal values of `entity_type` are in `data/enums.json`.

---

## Every field, table by table

Columns marked **PK** are the primary key. **FK** shows what a column points at. Enum columns list their legal values — anything else is rejected by the conformance check.

### `currencies`

*Reference & geography · 25 rows · IDs start `cur_`*

carries the true minor-unit exponent so JPY/KWD display correctly even though storage is always DECIMAL(12,2).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `currency_id` | text | **PK** | cur_ prefixed. |
| `iso4217` | char(3) | UNIQUE · NOT NULL | e.g. INR. |
| `name` | text | NOT NULL |  |
| `symbol` | text | NOT NULL |  |
| `minor_unit_exponent` | smallint | NOT NULL | 0 for JPY/KRW, 2 default, 3 for KWD/BHD. |
| `display_locale` | text | NOT NULL | BCP-47 locale used for formatting. |
| `updated_at` | timestamptz | NOT NULL |  |

### `inventory_calendar`

*Availability & pricing · 15,030 rows · IDs start `inv_`*

Entity x date availability with a database-level no-oversell CHECK. Deliberately scarce units so APS-05's load test has something to defend.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `inventory_id` | text | **PK** | inv_ prefixed. |
| `entity_type` | text | NOT NULL · one of `room_type`, `flight_fare`, `guide`, `poi` |  |
| `entity_id` | text | NOT NULL | room_type_id or fare_id. |
| `for_date` | date | NOT NULL |  |
| `total_units` | int | NOT NULL |  |
| `booked_units` | int | NOT NULL |  |
| `held_units` | int | NOT NULL |  |
| `price` | decimal(12,2) | NOT NULL | the price for that date. |
| `currency` | char(3) | FK → `currencies.iso4217` · NOT NULL |  |
| `min_stay_nights` | smallint | NOT NULL |  |
| `closed_to_arrival` | bool | NOT NULL |  |
| `updated_at` | timestamptz | NOT NULL |  |

*Unique together:* `(entity_type, entity_id, for_date)`

*Enforced by the database:* `booked_units + held_units <= total_units`

### `languages`

*Reference & geography · 26 rows · IDs start `lng_` · reference table*

Rule R6: BCP-47 is the only legal way to say 'language' anywhere in the model.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `language_id` | text | **PK** | lng_ prefixed. |
| `bcp47` | text | UNIQUE · NOT NULL | e.g. ta, hi, en-IN — never 'Tamil'. |
| `english_name` | text | NOT NULL |  |
| `native_name` | text | NOT NULL |  |
| `script` | text | NOT NULL | ISO-15924, e.g. Taml, Deva, Latn. |
| `rtl` | bool | NOT NULL | Right-to-left rendering flag. |
| `tts_supported` | bool | NOT NULL | Relevant to PS-13 voice output. |
| `updated_at` | timestamptz | NOT NULL |  |

### `price_bounds`

*Availability & pricing · 1,500 rows · IDs start `pbd_`*

The guardrails APS-02 must respect. A dynamic price outside these is a failing demo, not a clever one.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `bound_id` | text | **PK** | pbd_ prefixed. |
| `entity_type` | text | NOT NULL · one of `room_type`, `flight_fare`, `guide`, `poi` |  |
| `entity_id` | text | UNIQUE · NOT NULL |  |
| `floor_price` | decimal(12,2) | NOT NULL | D3. |
| `ceiling_price` | decimal(12,2) | NOT NULL |  |
| `currency` | char(3) | FK → `currencies.iso4217` · NOT NULL |  |
| `max_daily_move_pct` | decimal(5,2) | NOT NULL | Cap on day-over-day movement. |
| `max_weekly_move_pct` | decimal(5,2) | NOT NULL |  |
| `rounding_step` | decimal(12,2) | NOT NULL | Prices are rounded to this step for display. |
| `override_active` | bool | NOT NULL | Manual admin override in force. |
| `updated_at` | timestamptz | NOT NULL |  |

### `price_history`

*Availability & pricing · 5,950 rows · IDs start `phs_`*

Computed price over time with the driving factors alongside — the shape APS-02's explainability requirement has to produce.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `history_id` | text | **PK** | phs_ prefixed. |
| `entity_type` | text | NOT NULL · one of `room_type`, `flight_fare`, `guide`, `poi` |  |
| `entity_id` | text | NOT NULL |  |
| `effective_date` | date | NOT NULL |  |
| `price` | decimal(12,2) | NOT NULL | D3. |
| `currency` | char(3) | FK → `currencies.iso4217` · NOT NULL |  |
| `baseline_price` | decimal(12,2) | NOT NULL |  |
| `demand_index` | decimal(6,3) | NOT NULL | Forecast output that drove the move. |
| `occupancy_pct` | decimal(5,2) | NOT NULL |  |
| `lead_time_factor` | decimal(6,3) | NOT NULL |  |
| `seasonality_factor` | decimal(6,3) | NOT NULL |  |
| `event_factor` | decimal(6,3) | NOT NULL | Uplift from a festival in events_festivals. |
| `competitor_factor` | decimal(6,3) | NOT NULL |  |
| `bound_clamped` | bool | NOT NULL | True where price_bounds clipped the computed price. |
| `explanation` | text | NOT NULL | Human-readable factor summary. |
| `computed_at` | timestamptz | NOT NULL |  |

*Unique together:* `(entity_type, entity_id, effective_date)`

### `countries`

*Reference & geography · 30 rows · IDs start `cnt_`*

ISO country reference. Every city, currency default and calling code resolves here.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `country_id` | text | **PK** | Canonical ID, cnt_ prefixed. |
| `iso2` | char(2) | UNIQUE · NOT NULL | ISO-3166-1 alpha-2, e.g. IN. |
| `iso3` | char(3) | UNIQUE · NOT NULL | ISO-3166-1 alpha-3, e.g. IND. |
| `name` | text | NOT NULL | English short name. |
| `default_currency` | char(3) | FK → `currencies.iso4217` · NOT NULL | ISO-4217 code. |
| `calling_code` | text | NOT NULL | E.164 country calling code, e.g. +91. |
| `region` | text | NOT NULL | UN sub-region grouping. |
| `updated_at` | timestamptz | NOT NULL | Rule R4: UTC, ISO-8601 with offset. |

### `airlines`

*Reference & geography · 30 rows · IDs start `arl_` · reference table*

Carrier reference for flight schedule instances.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `airline_id` | text | **PK** | arl_ prefixed. |
| `iata` | char(2) | UNIQUE · NOT NULL | Carrier code, e.g. 6E. |
| `name` | text | NOT NULL |  |
| `alliance` | text |  | star_alliance | oneworld | skyteam | none. |
| `country_id` | text | FK → `countries.country_id` · NOT NULL |  |
| `low_cost` | bool | NOT NULL | Drives fare banding. |
| `updated_at` | timestamptz | NOT NULL |  |

### `cities`

*Reference & geography · 60 rows · IDs start `cty_`*

The geographic anchor of the whole model. 60 cities; every hotel, POI, package, advisory and weather row hangs off one.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `city_id` | text | **PK** | cty_ prefixed. |
| `name` | text | NOT NULL | City name. |
| `state` | text |  | State / province, nullable for city-states. |
| `country_id` | text | FK → `countries.country_id` · NOT NULL |  |
| `country_code` | char(2) | NOT NULL | Denormalised ISO2 for convenient joins. |
| `lat` | decimal(9,6) | NOT NULL | Rule R7: WGS-84, 6dp. |
| `lng` | decimal(9,6) | NOT NULL | Rule R7: WGS-84, 6dp. |
| `timezone` | text | NOT NULL | IANA zone, e.g. Asia/Kolkata. |
| `region` | text | NOT NULL | Domestic region grouping, e.g. South India. |
| `population` | int |  | Approximate, for demand weighting. |
| `season_profile` | text | NOT NULL · one of `winter`, `summer`, `monsoon`, `post_monsoon`, `spring`, `autumn` | Dominant season at the peak travel window. |
| `peak_months` | text | NOT NULL | Comma-separated month numbers, e.g. 10,11,12. |
| `primary_language` | text | FK → `languages.bcp47` · NOT NULL | Rule R6: BCP-47 tag. |
| `description` | text |  | One-paragraph orientation blurb, used by PS-13. |
| `status` | text | NOT NULL · one of `active`, `inactive`, `archived`, `draft` |  |
| `updated_at` | timestamptz | NOT NULL |  |

### `hotels`

*Supply & catalogue · 300 rows · IDs start `htl_`*

Fewer, richer properties. Depth (reviews, room types, media) matters more than catalogue size —.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `hotel_id` | text | **PK** | htl_ prefixed. |
| `city_id` | text | FK → `cities.city_id` · NOT NULL |  |
| `name` | text | NOT NULL | ~3% near-duplicate names injected deliberately. |
| `property_type` | text | NOT NULL · one of `hotel`, `resort`, `homestay`, `hostel`, `apartment`, `boutique`, `heritage`, `guesthouse` |  |
| `star_rating` | smallint | NOT NULL | 1–5, CHECK constrained. |
| `guest_score` | decimal(2,1) |  | 0.0–10.0; null for a handful of new properties. |
| `review_count` | int | NOT NULL | Denormalised count, must agree with hotel_reviews. |
| `address_line` | text | NOT NULL |  |
| `lat` | decimal(9,6) | NOT NULL |  |
| `lng` | decimal(9,6) | NOT NULL |  |
| `distance_to_centre_km` | decimal(6,2) | NOT NULL | PS-02 filter: distance to a landmark. |
| `description` | text | NOT NULL | Plausible prose, embeddable. |
| `base_currency` | char(3) | FK → `currencies.iso4217` · NOT NULL |  |
| `checkin_time` | text | NOT NULL | Local HH:MM at the property. |
| `checkout_time` | text | NOT NULL |  |
| `chain_code` | text |  | Null for independents. |
| `has_xr_scene` | bool | NOT NULL | PS-05 / APS-07 — does an immersive preview exist. |
| `status` | text | NOT NULL · one of `active`, `inactive`, `archived`, `draft` |  |
| `created_at` | timestamptz | NOT NULL |  |
| `updated_at` | timestamptz | NOT NULL |  |

### `pricing_events`

*Availability & pricing · 20,000 rows · IDs start `pev_`*

13 months of search / booking / cancellation signal with visible seasonality — otherwise APS-02's forecast is a straight line and the price curve has nothing to explain.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `event_id` | text | **PK** | pev_ prefixed. |
| `entity_type` | text | NOT NULL · one of `room_type`, `flight_fare`, `guide`, `poi` |  |
| `entity_id` | text | NOT NULL |  |
| `city_id` | text | FK → `cities.city_id` · NOT NULL | Denormalised for fast grouping. |
| `event_type` | text | NOT NULL · one of `search`, `view`, `booking`, `cancellation`, `abandon` |  |
| `occurred_at` | timestamptz | NOT NULL | R4. |
| `for_date` | date | NOT NULL | The stay/travel date being searched or booked. |
| `lead_time_days` | int | NOT NULL | for_date minus occurred_at date — a key forecast feature. |
| `channel` | text | NOT NULL · one of `web`, `mobile_app`, `partner`, `call_centre`, `agent` |  |
| `party_size` | smallint | NOT NULL |  |
| `quoted_price` | decimal(12,2) |  | null for pure searches. |
| `currency` | char(3) | FK → `currencies.iso4217` |  |
| `converted` | bool | NOT NULL | Did this search become a booking. |
| `session_id` | text | NOT NULL | Opaque session grouping key. |

### `airports`

*Reference & geography · 80 rows · IDs start `apt_` · reference table*

So flights join airport-to-airport rather than city-to-city.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `airport_id` | text | **PK** | apt_ prefixed. |
| `iata` | char(3) | UNIQUE · NOT NULL | IATA code. |
| `icao` | char(4) |  | ICAO code. |
| `name` | text | NOT NULL |  |
| `city_id` | text | FK → `cities.city_id` · NOT NULL |  |
| `lat` | decimal(9,6) | NOT NULL |  |
| `lng` | decimal(9,6) | NOT NULL |  |
| `timezone` | text | NOT NULL | IANA. |
| `is_international` | bool | NOT NULL |  |
| `updated_at` | timestamptz | NOT NULL |  |

### `flights`

*Supply & catalogue · 4,000 rows · IDs start `flt_`*

Schedule instances across the search window, so a date search returns results rather than blanks.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `flight_id` | text | **PK** | flt_ prefixed. |
| `airline_id` | text | FK → `airlines.airline_id` · NOT NULL |  |
| `flight_number` | text | NOT NULL | e.g. 6E-2043. |
| `origin_airport_id` | text | FK → `airports.airport_id` · NOT NULL |  |
| `dest_airport_id` | text | FK → `airports.airport_id` · NOT NULL |  |
| `departs_at` | timestamptz | NOT NULL | Rule R4: carries offset. |
| `arrives_at` | timestamptz | NOT NULL |  |
| `duration_minutes` | int | NOT NULL |  |
| `stops` | smallint | NOT NULL |  |
| `aircraft_type` | text |  |  |
| `cabin_classes` | text | NOT NULL | Comma-separated cabin_class values available. |
| `carbon_kg` | decimal(8,3) | NOT NULL | Per-seat estimate — APS-09 reads this. |
| `status` | text | NOT NULL · one of `active`, `inactive`, `archived`, `draft` |  |
| `updated_at` | timestamptz | NOT NULL |  |

### `flight_fares`

*Supply & catalogue · 8,002 rows · IDs start `far_`*

The bookable unit for flights, and the second entity_type in inventory_calendar.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `fare_id` | text | **PK** | far_ prefixed. |
| `flight_id` | text | FK → `flights.flight_id` · NOT NULL |  |
| `cabin_class` | text | NOT NULL · one of `economy`, `premium_economy`, `business`, `first` |  |
| `fare_class` | text | NOT NULL · one of `saver`, `flex`, `standard`, `corporate`, `promo` |  |
| `base_fare` | decimal(12,2) | NOT NULL | D3. |
| `taxes` | decimal(12,2) | NOT NULL |  |
| `currency` | char(3) | FK → `currencies.iso4217` · NOT NULL |  |
| `baggage_kg` | smallint | NOT NULL |  |
| `cabin_baggage_kg` | smallint | NOT NULL |  |
| `changeable` | bool | NOT NULL |  |
| `change_fee` | decimal(12,2) |  |  |
| `refundable` | bool | NOT NULL |  |
| `seats_total` | int | NOT NULL |  |
| `status` | text | NOT NULL · one of `active`, `inactive`, `archived`, `draft` |  |
| `updated_at` | timestamptz | NOT NULL |  |

---

## The rules that apply to these fields

| # | Rule |
|---|---|
| R1 | **Additive only.** Add columns, tables and stores freely. Never rename, drop or repurpose a field that came with the data. |
| R2 | **IDs are opaque prefixed strings** — `htl_a91f3c`. Never integers, never parsed for meaning. |
| R3 | **Money is a pair**: a 2-place decimal plus an ISO-4217 currency code. Never a float. |
| R4 | **Time is ISO-8601 with an offset.** `_at` fields carry an offset; `_date` fields have no zone. |
| R5 | **Enums are lowercase snake_case** and the legal values are in `data/enums.json`. |
| R6 | **Language is a BCP-47 tag** — `ta`, not "Tamil". |
| R7 | **Geography is WGS-84** to 6 decimal places, `lat` and `lng` together or not at all. |
| R8 | **Nothing is hard-deleted.** Rows carry `status` and `updated_at`. |

Add whatever you like beside these fields — new columns, new tables, your own vector store, your own services. That is the point of R1. What you must not do is rename or re-key the fields that came with the data, because that is what would stop sixteen independent builds being put together afterwards.

`data/WORKING_WITH_THE_DATA.md` has the loading instructions, including how to read money without corrupting it. `tools/validate_conformance.py` tells you in thirty seconds whether you are still conformant.

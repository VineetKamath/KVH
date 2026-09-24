-- KV Hackathon 2026 · travel data model v1.1.0-rc1
-- Only the 13 tables this problem statement needs.

-- SQLite has no DECIMAL type, and NUMERIC affinity would turn '8500.00' into the
-- float 8500.0. Money columns are therefore TEXT so the exact value survives.
PRAGMA foreign_keys = ON;

-- currencies  (Reference & geography)
CREATE TABLE currencies (
  currency_id                  TEXT PRIMARY KEY,
  iso4217                      TEXT NOT NULL UNIQUE,
  name                         TEXT NOT NULL,
  symbol                       TEXT NOT NULL,
  minor_unit_exponent          INTEGER NOT NULL,
  display_locale               TEXT NOT NULL,
  updated_at                   TEXT NOT NULL
);

-- inventory_calendar  (Availability & pricing)
CREATE TABLE inventory_calendar (
  inventory_id                 TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL,
  entity_id                    TEXT NOT NULL,
  for_date                     TEXT NOT NULL,
  total_units                  INTEGER NOT NULL,
  booked_units                 INTEGER NOT NULL,
  held_units                   INTEGER NOT NULL,
  price                        TEXT NOT NULL,
  currency                     TEXT NOT NULL,
  min_stay_nights              INTEGER NOT NULL,
  closed_to_arrival            INTEGER NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (currency) REFERENCES currencies(iso4217),
  UNIQUE (entity_type, entity_id, for_date),
  CHECK (booked_units + held_units <= total_units)
);

-- languages  (Reference & geography)
CREATE TABLE languages (
  language_id                  TEXT PRIMARY KEY,
  bcp47                        TEXT NOT NULL UNIQUE,
  english_name                 TEXT NOT NULL,
  native_name                  TEXT NOT NULL,
  script                       TEXT NOT NULL,
  rtl                          INTEGER NOT NULL,
  tts_supported                INTEGER NOT NULL,
  updated_at                   TEXT NOT NULL
);

-- price_bounds  (Availability & pricing)
CREATE TABLE price_bounds (
  bound_id                     TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL,
  entity_id                    TEXT NOT NULL UNIQUE,
  floor_price                  TEXT NOT NULL,
  ceiling_price                TEXT NOT NULL,
  currency                     TEXT NOT NULL,
  max_daily_move_pct           NUMERIC(5,2) NOT NULL,
  max_weekly_move_pct          NUMERIC(5,2) NOT NULL,
  rounding_step                TEXT NOT NULL,
  override_active              INTEGER NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (currency) REFERENCES currencies(iso4217)
);

-- price_history  (Availability & pricing)
CREATE TABLE price_history (
  history_id                   TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL,
  entity_id                    TEXT NOT NULL,
  effective_date               TEXT NOT NULL,
  price                        TEXT NOT NULL,
  currency                     TEXT NOT NULL,
  baseline_price               TEXT NOT NULL,
  demand_index                 NUMERIC(6,3) NOT NULL,
  occupancy_pct                NUMERIC(5,2) NOT NULL,
  lead_time_factor             NUMERIC(6,3) NOT NULL,
  seasonality_factor           NUMERIC(6,3) NOT NULL,
  event_factor                 NUMERIC(6,3) NOT NULL,
  competitor_factor            NUMERIC(6,3) NOT NULL,
  bound_clamped                INTEGER NOT NULL,
  explanation                  TEXT NOT NULL,
  computed_at                  TEXT NOT NULL,
  FOREIGN KEY (currency) REFERENCES currencies(iso4217),
  UNIQUE (entity_type, entity_id, effective_date)
);

-- countries  (Reference & geography)
CREATE TABLE countries (
  country_id                   TEXT PRIMARY KEY,
  iso2                         TEXT NOT NULL UNIQUE,
  iso3                         TEXT NOT NULL UNIQUE,
  name                         TEXT NOT NULL,
  default_currency             TEXT NOT NULL,
  calling_code                 TEXT NOT NULL,
  region                       TEXT NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (default_currency) REFERENCES currencies(iso4217)
);

-- airlines  (Reference & geography)
CREATE TABLE airlines (
  airline_id                   TEXT PRIMARY KEY,
  iata                         TEXT NOT NULL UNIQUE,
  name                         TEXT NOT NULL,
  alliance                     TEXT,
  country_id                   TEXT NOT NULL,
  low_cost                     INTEGER NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (country_id) REFERENCES countries(country_id)
);

-- cities  (Reference & geography)
CREATE TABLE cities (
  city_id                      TEXT PRIMARY KEY,
  name                         TEXT NOT NULL,
  state                        TEXT,
  country_id                   TEXT NOT NULL,
  country_code                 TEXT NOT NULL,
  lat                          NUMERIC(9,6) NOT NULL,
  lng                          NUMERIC(9,6) NOT NULL,
  timezone                     TEXT NOT NULL,
  region                       TEXT NOT NULL,
  population                   INTEGER,
  season_profile               TEXT NOT NULL,
  peak_months                  TEXT NOT NULL,
  primary_language             TEXT NOT NULL,
  description                  TEXT,
  status                       TEXT NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (country_id) REFERENCES countries(country_id),
  FOREIGN KEY (primary_language) REFERENCES languages(bcp47)
);

-- hotels  (Supply & catalogue)
CREATE TABLE hotels (
  hotel_id                     TEXT PRIMARY KEY,
  city_id                      TEXT NOT NULL,
  name                         TEXT NOT NULL,
  property_type                TEXT NOT NULL,
  star_rating                  INTEGER NOT NULL,
  guest_score                  NUMERIC(2,1),
  review_count                 INTEGER NOT NULL,
  address_line                 TEXT NOT NULL,
  lat                          NUMERIC(9,6) NOT NULL,
  lng                          NUMERIC(9,6) NOT NULL,
  distance_to_centre_km        NUMERIC(6,2) NOT NULL,
  description                  TEXT NOT NULL,
  base_currency                TEXT NOT NULL,
  checkin_time                 TEXT NOT NULL,
  checkout_time                TEXT NOT NULL,
  chain_code                   TEXT,
  has_xr_scene                 INTEGER NOT NULL,
  status                       TEXT NOT NULL,
  created_at                   TEXT NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (city_id) REFERENCES cities(city_id),
  FOREIGN KEY (base_currency) REFERENCES currencies(iso4217)
);

-- pricing_events  (Availability & pricing)
CREATE TABLE pricing_events (
  event_id                     TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL,
  entity_id                    TEXT NOT NULL,
  city_id                      TEXT NOT NULL,
  event_type                   TEXT NOT NULL,
  occurred_at                  TEXT NOT NULL,
  for_date                     TEXT NOT NULL,
  lead_time_days               INTEGER NOT NULL,
  channel                      TEXT NOT NULL,
  party_size                   INTEGER NOT NULL,
  quoted_price                 TEXT,
  currency                     TEXT,
  converted                    INTEGER NOT NULL,
  session_id                   TEXT NOT NULL,
  FOREIGN KEY (city_id) REFERENCES cities(city_id),
  FOREIGN KEY (currency) REFERENCES currencies(iso4217)
);

-- airports  (Reference & geography)
CREATE TABLE airports (
  airport_id                   TEXT PRIMARY KEY,
  iata                         TEXT NOT NULL UNIQUE,
  icao                         TEXT,
  name                         TEXT NOT NULL,
  city_id                      TEXT NOT NULL,
  lat                          NUMERIC(9,6) NOT NULL,
  lng                          NUMERIC(9,6) NOT NULL,
  timezone                     TEXT NOT NULL,
  is_international             INTEGER NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (city_id) REFERENCES cities(city_id)
);

-- flights  (Supply & catalogue)
CREATE TABLE flights (
  flight_id                    TEXT PRIMARY KEY,
  airline_id                   TEXT NOT NULL,
  flight_number                TEXT NOT NULL,
  origin_airport_id            TEXT NOT NULL,
  dest_airport_id              TEXT NOT NULL,
  departs_at                   TEXT NOT NULL,
  arrives_at                   TEXT NOT NULL,
  duration_minutes             INTEGER NOT NULL,
  stops                        INTEGER NOT NULL,
  aircraft_type                TEXT,
  cabin_classes                TEXT NOT NULL,
  carbon_kg                    NUMERIC(8,3) NOT NULL,
  status                       TEXT NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (airline_id) REFERENCES airlines(airline_id),
  FOREIGN KEY (origin_airport_id) REFERENCES airports(airport_id),
  FOREIGN KEY (dest_airport_id) REFERENCES airports(airport_id)
);

-- flight_fares  (Supply & catalogue)
CREATE TABLE flight_fares (
  fare_id                      TEXT PRIMARY KEY,
  flight_id                    TEXT NOT NULL,
  cabin_class                  TEXT NOT NULL,
  fare_class                   TEXT NOT NULL,
  base_fare                    TEXT NOT NULL,
  taxes                        TEXT NOT NULL,
  currency                     TEXT NOT NULL,
  baggage_kg                   INTEGER NOT NULL,
  cabin_baggage_kg             INTEGER NOT NULL,
  changeable                   INTEGER NOT NULL,
  change_fee                   TEXT,
  refundable                   INTEGER NOT NULL,
  seats_total                  INTEGER NOT NULL,
  status                       TEXT NOT NULL,
  updated_at                   TEXT NOT NULL,
  FOREIGN KEY (flight_id) REFERENCES flights(flight_id),
  FOREIGN KEY (currency) REFERENCES currencies(iso4217)
);

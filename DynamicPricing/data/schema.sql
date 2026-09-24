-- KV Hackathon 2026 · travel data model v1.1.0-rc1
-- Only the 13 tables this problem statement needs.

CREATE EXTENSION IF NOT EXISTS vector;   -- optional, for embedding search

-- currencies  (Reference & geography)
CREATE TABLE currencies (
  currency_id                  TEXT PRIMARY KEY,
  iso4217                      CHAR(3) NOT NULL UNIQUE,
  name                         TEXT NOT NULL,
  symbol                       TEXT NOT NULL,
  minor_unit_exponent          SMALLINT NOT NULL,
  display_locale               TEXT NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- inventory_calendar  (Availability & pricing)
CREATE TABLE inventory_calendar (
  inventory_id                 TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL CHECK (entity_type IN ('room_type', 'flight_fare', 'guide', 'poi')),
  entity_id                    TEXT NOT NULL,
  for_date                     DATE NOT NULL,
  total_units                  INTEGER NOT NULL,
  booked_units                 INTEGER NOT NULL,
  held_units                   INTEGER NOT NULL,
  price                        NUMERIC(12,2) NOT NULL,
  currency                     CHAR(3) NOT NULL,
  min_stay_nights              SMALLINT NOT NULL,
  closed_to_arrival            BOOLEAN NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL,
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
  rtl                          BOOLEAN NOT NULL,
  tts_supported                BOOLEAN NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- price_bounds  (Availability & pricing)
CREATE TABLE price_bounds (
  bound_id                     TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL CHECK (entity_type IN ('room_type', 'flight_fare', 'guide', 'poi')),
  entity_id                    TEXT NOT NULL UNIQUE,
  floor_price                  NUMERIC(12,2) NOT NULL,
  ceiling_price                NUMERIC(12,2) NOT NULL,
  currency                     CHAR(3) NOT NULL,
  max_daily_move_pct           NUMERIC(5,2) NOT NULL,
  max_weekly_move_pct          NUMERIC(5,2) NOT NULL,
  rounding_step                NUMERIC(12,2) NOT NULL,
  override_active              BOOLEAN NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- price_history  (Availability & pricing)
CREATE TABLE price_history (
  history_id                   TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL CHECK (entity_type IN ('room_type', 'flight_fare', 'guide', 'poi')),
  entity_id                    TEXT NOT NULL,
  effective_date               DATE NOT NULL,
  price                        NUMERIC(12,2) NOT NULL,
  currency                     CHAR(3) NOT NULL,
  baseline_price               NUMERIC(12,2) NOT NULL,
  demand_index                 NUMERIC(6,3) NOT NULL,
  occupancy_pct                NUMERIC(5,2) NOT NULL,
  lead_time_factor             NUMERIC(6,3) NOT NULL,
  seasonality_factor           NUMERIC(6,3) NOT NULL,
  event_factor                 NUMERIC(6,3) NOT NULL,
  competitor_factor            NUMERIC(6,3) NOT NULL,
  bound_clamped                BOOLEAN NOT NULL,
  explanation                  TEXT NOT NULL,
  computed_at                  TIMESTAMPTZ NOT NULL,
  UNIQUE (entity_type, entity_id, effective_date)
);

-- countries  (Reference & geography)
CREATE TABLE countries (
  country_id                   TEXT PRIMARY KEY,
  iso2                         CHAR(2) NOT NULL UNIQUE,
  iso3                         CHAR(3) NOT NULL UNIQUE,
  name                         TEXT NOT NULL,
  default_currency             CHAR(3) NOT NULL,
  calling_code                 TEXT NOT NULL,
  region                       TEXT NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- airlines  (Reference & geography)
CREATE TABLE airlines (
  airline_id                   TEXT PRIMARY KEY,
  iata                         CHAR(2) NOT NULL UNIQUE,
  name                         TEXT NOT NULL,
  alliance                     TEXT,
  country_id                   TEXT NOT NULL,
  low_cost                     BOOLEAN NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- cities  (Reference & geography)
CREATE TABLE cities (
  city_id                      TEXT PRIMARY KEY,
  name                         TEXT NOT NULL,
  state                        TEXT,
  country_id                   TEXT NOT NULL,
  country_code                 CHAR(2) NOT NULL,
  lat                          NUMERIC(9,6) NOT NULL,
  lng                          NUMERIC(9,6) NOT NULL,
  timezone                     TEXT NOT NULL,
  region                       TEXT NOT NULL,
  population                   INTEGER,
  season_profile               TEXT NOT NULL CHECK (season_profile IN ('winter', 'summer', 'monsoon', 'post_monsoon', 'spring', 'autumn')),
  peak_months                  TEXT NOT NULL,
  primary_language             TEXT NOT NULL,
  description                  TEXT,
  status                       TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'archived', 'draft')),
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- hotels  (Supply & catalogue)
CREATE TABLE hotels (
  hotel_id                     TEXT PRIMARY KEY,
  city_id                      TEXT NOT NULL,
  name                         TEXT NOT NULL,
  property_type                TEXT NOT NULL CHECK (property_type IN ('hotel', 'resort', 'homestay', 'hostel', 'apartment', 'boutique', 'heritage', 'guesthouse')),
  star_rating                  SMALLINT NOT NULL,
  guest_score                  NUMERIC(2,1),
  review_count                 INTEGER NOT NULL,
  address_line                 TEXT NOT NULL,
  lat                          NUMERIC(9,6) NOT NULL,
  lng                          NUMERIC(9,6) NOT NULL,
  distance_to_centre_km        NUMERIC(6,2) NOT NULL,
  description                  TEXT NOT NULL,
  base_currency                CHAR(3) NOT NULL,
  checkin_time                 TEXT NOT NULL,
  checkout_time                TEXT NOT NULL,
  chain_code                   TEXT,
  has_xr_scene                 BOOLEAN NOT NULL,
  status                       TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'archived', 'draft')),
  created_at                   TIMESTAMPTZ NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- pricing_events  (Availability & pricing)
CREATE TABLE pricing_events (
  event_id                     TEXT PRIMARY KEY,
  entity_type                  TEXT NOT NULL CHECK (entity_type IN ('room_type', 'flight_fare', 'guide', 'poi')),
  entity_id                    TEXT NOT NULL,
  city_id                      TEXT NOT NULL,
  event_type                   TEXT NOT NULL CHECK (event_type IN ('search', 'view', 'booking', 'cancellation', 'abandon')),
  occurred_at                  TIMESTAMPTZ NOT NULL,
  for_date                     DATE NOT NULL,
  lead_time_days               INTEGER NOT NULL,
  channel                      TEXT NOT NULL CHECK (channel IN ('web', 'mobile_app', 'partner', 'call_centre', 'agent')),
  party_size                   SMALLINT NOT NULL,
  quoted_price                 NUMERIC(12,2),
  currency                     CHAR(3),
  converted                    BOOLEAN NOT NULL,
  session_id                   TEXT NOT NULL
);

-- airports  (Reference & geography)
CREATE TABLE airports (
  airport_id                   TEXT PRIMARY KEY,
  iata                         CHAR(3) NOT NULL UNIQUE,
  icao                         CHAR(4),
  name                         TEXT NOT NULL,
  city_id                      TEXT NOT NULL,
  lat                          NUMERIC(9,6) NOT NULL,
  lng                          NUMERIC(9,6) NOT NULL,
  timezone                     TEXT NOT NULL,
  is_international             BOOLEAN NOT NULL,
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- flights  (Supply & catalogue)
CREATE TABLE flights (
  flight_id                    TEXT PRIMARY KEY,
  airline_id                   TEXT NOT NULL,
  flight_number                TEXT NOT NULL,
  origin_airport_id            TEXT NOT NULL,
  dest_airport_id              TEXT NOT NULL,
  departs_at                   TIMESTAMPTZ NOT NULL,
  arrives_at                   TIMESTAMPTZ NOT NULL,
  duration_minutes             INTEGER NOT NULL,
  stops                        SMALLINT NOT NULL,
  aircraft_type                TEXT,
  cabin_classes                TEXT NOT NULL,
  carbon_kg                    NUMERIC(8,3) NOT NULL,
  status                       TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'archived', 'draft')),
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- flight_fares  (Supply & catalogue)
CREATE TABLE flight_fares (
  fare_id                      TEXT PRIMARY KEY,
  flight_id                    TEXT NOT NULL,
  cabin_class                  TEXT NOT NULL CHECK (cabin_class IN ('economy', 'premium_economy', 'business', 'first')),
  fare_class                   TEXT NOT NULL CHECK (fare_class IN ('saver', 'flex', 'standard', 'corporate', 'promo')),
  base_fare                    NUMERIC(12,2) NOT NULL,
  taxes                        NUMERIC(12,2) NOT NULL,
  currency                     CHAR(3) NOT NULL,
  baggage_kg                   SMALLINT NOT NULL,
  cabin_baggage_kg             SMALLINT NOT NULL,
  changeable                   BOOLEAN NOT NULL,
  change_fee                   NUMERIC(12,2),
  refundable                   BOOLEAN NOT NULL,
  seats_total                  INTEGER NOT NULL,
  status                       TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'archived', 'draft')),
  updated_at                   TIMESTAMPTZ NOT NULL
);

-- foreign keys
ALTER TABLE inventory_calendar ADD CONSTRAINT fk_inventory_calendar_currency FOREIGN KEY (currency) REFERENCES currencies(iso4217);
ALTER TABLE price_bounds ADD CONSTRAINT fk_price_bounds_currency FOREIGN KEY (currency) REFERENCES currencies(iso4217);
ALTER TABLE price_history ADD CONSTRAINT fk_price_history_currency FOREIGN KEY (currency) REFERENCES currencies(iso4217);
ALTER TABLE countries ADD CONSTRAINT fk_countries_default_currency FOREIGN KEY (default_currency) REFERENCES currencies(iso4217);
ALTER TABLE airlines ADD CONSTRAINT fk_airlines_country_id FOREIGN KEY (country_id) REFERENCES countries(country_id);
ALTER TABLE cities ADD CONSTRAINT fk_cities_country_id FOREIGN KEY (country_id) REFERENCES countries(country_id);
ALTER TABLE cities ADD CONSTRAINT fk_cities_primary_language FOREIGN KEY (primary_language) REFERENCES languages(bcp47);
ALTER TABLE hotels ADD CONSTRAINT fk_hotels_city_id FOREIGN KEY (city_id) REFERENCES cities(city_id);
ALTER TABLE hotels ADD CONSTRAINT fk_hotels_base_currency FOREIGN KEY (base_currency) REFERENCES currencies(iso4217);
ALTER TABLE pricing_events ADD CONSTRAINT fk_pricing_events_city_id FOREIGN KEY (city_id) REFERENCES cities(city_id);
ALTER TABLE pricing_events ADD CONSTRAINT fk_pricing_events_currency FOREIGN KEY (currency) REFERENCES currencies(iso4217);
ALTER TABLE airports ADD CONSTRAINT fk_airports_city_id FOREIGN KEY (city_id) REFERENCES cities(city_id);
ALTER TABLE flights ADD CONSTRAINT fk_flights_airline_id FOREIGN KEY (airline_id) REFERENCES airlines(airline_id);
ALTER TABLE flights ADD CONSTRAINT fk_flights_origin_airport_id FOREIGN KEY (origin_airport_id) REFERENCES airports(airport_id);
ALTER TABLE flights ADD CONSTRAINT fk_flights_dest_airport_id FOREIGN KEY (dest_airport_id) REFERENCES airports(airport_id);
ALTER TABLE flight_fares ADD CONSTRAINT fk_flight_fares_flight_id FOREIGN KEY (flight_id) REFERENCES flights(flight_id);
ALTER TABLE flight_fares ADD CONSTRAINT fk_flight_fares_currency FOREIGN KEY (currency) REFERENCES currencies(iso4217);

-- indexes
CREATE INDEX idx_inventory_calendar_currency ON inventory_calendar(currency);
CREATE INDEX idx_price_bounds_currency ON price_bounds(currency);
CREATE INDEX idx_price_history_currency ON price_history(currency);
CREATE INDEX idx_countries_default_currency ON countries(default_currency);
CREATE INDEX idx_airlines_country_id ON airlines(country_id);
CREATE INDEX idx_cities_country_id ON cities(country_id);
CREATE INDEX idx_cities_primary_language ON cities(primary_language);
CREATE INDEX idx_hotels_city_id ON hotels(city_id);
CREATE INDEX idx_hotels_base_currency ON hotels(base_currency);
CREATE INDEX idx_pricing_events_city_id ON pricing_events(city_id);
CREATE INDEX idx_pricing_events_currency ON pricing_events(currency);
CREATE INDEX idx_airports_city_id ON airports(city_id);
CREATE INDEX idx_flights_airline_id ON flights(airline_id);
CREATE INDEX idx_flights_origin_airport_id ON flights(origin_airport_id);
CREATE INDEX idx_flights_dest_airport_id ON flights(dest_airport_id);
CREATE INDEX idx_flight_fares_flight_id ON flight_fares(flight_id);
CREATE INDEX idx_flight_fares_currency ON flight_fares(currency);
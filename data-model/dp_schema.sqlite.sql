-- PixelMinds dp_ tables (SQLite). Source of truth: docs/ARCHITECTURE.md section 5.2.
-- Conventions follow DynamicPricing/data/schema.sqlite.sql: money TEXT, _at ISO-8601 TEXT with offset, bool INTEGER 0/1.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- the clock and the cycle ------------------------------------------------------
CREATE TABLE dp_clock (
  clock_id        TEXT PRIMARY KEY,                    -- 'dpck_main'
  business_date   TEXT NOT NULL CHECK (length(business_date) = 10),
  status          TEXT NOT NULL DEFAULT 'active',
  updated_at      TEXT NOT NULL);

CREATE TABLE dp_cycle (
  cycle_id        TEXT PRIMARY KEY,                    -- dpy_
  kind            TEXT NOT NULL CHECK (kind IN ('warmup','advance','reprice','simulation')),
  business_date   TEXT NOT NULL,
  engine_config_version INTEGER NOT NULL,
  model_version   TEXT NOT NULL,
  n_decisions     INTEGER, n_clamped INTEGER,
  status          TEXT NOT NULL CHECK (status IN ('running','completed','failed','degraded')),
  started_at      TEXT NOT NULL, finished_at TEXT, updated_at TEXT NOT NULL);

-- configuration (append-only versions) -------------------------------------------
CREATE TABLE dp_engine_config (
  config_id       TEXT PRIMARY KEY,                    -- dpc_
  version         INTEGER NOT NULL UNIQUE,
  factor_bounds   TEXT NOT NULL CHECK (json_valid(factor_bounds)),  -- {"demand":{"lo":"0.70","hi":"1.30","enabled":true},…}
  auto_band_pct   TEXT NOT NULL,
  anomaly_z       TEXT NOT NULL DEFAULT '2.50',
  anomaly_move_pct TEXT NOT NULL DEFAULT '12.00',
  kill_switch_active INTEGER NOT NULL DEFAULT 0 CHECK (kill_switch_active IN (0,1)),
  actor           TEXT NOT NULL, reason TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('active','inactive','archived','draft')),
  effective_from_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE dp_bounds_version (
  bounds_version_id TEXT PRIMARY KEY,                  -- dpv_
  bound_id        TEXT NOT NULL REFERENCES price_bounds(bound_id),
  version         INTEGER NOT NULL,
  floor_price     TEXT NOT NULL, ceiling_price TEXT NOT NULL,
  currency        TEXT NOT NULL REFERENCES currencies(iso4217),
  max_daily_move_pct TEXT NOT NULL, max_weekly_move_pct TEXT NOT NULL,
  rounding_step   TEXT NOT NULL, override_active INTEGER NOT NULL CHECK (override_active IN (0,1)),
  actor           TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE (bound_id, version));
-- version 1 of every bound = a snapshot of the provided price_bounds row at seed time

CREATE TABLE dp_baseline (
  baseline_id     TEXT PRIMARY KEY,                    -- dpbl_
  entity_type     TEXT NOT NULL CHECK (entity_type IN ('room_type','flight_fare','guide','poi')),
  entity_id       TEXT NOT NULL, for_date TEXT NOT NULL,
  baseline_price  TEXT NOT NULL CHECK (baseline_price GLOB '*[0-9].[0-9][0-9]'),
  currency        TEXT NOT NULL REFERENCES currencies(iso4217),
  source          TEXT NOT NULL DEFAULT 'inventory_calendar_snapshot', created_at TEXT NOT NULL,
  UNIQUE (entity_type, entity_id, for_date));

-- intelligence ---------------------------------------------------------------------
CREATE TABLE dp_feature (
  feature_id      TEXT PRIMARY KEY,                    -- dpx_
  entity_type     TEXT NOT NULL, entity_id TEXT NOT NULL,
  city_id         TEXT REFERENCES cities(city_id),     -- NULL for the 86 city-less room types
  for_date        TEXT NOT NULL, as_of_date TEXT NOT NULL,
  lead_time_days  INTEGER NOT NULL, occupancy_pct TEXT NOT NULL,
  otb_bookings INTEGER NOT NULL, otb_cancellations INTEGER NOT NULL,
  otb_searches INTEGER NOT NULL, otb_views INTEGER NOT NULL,
  pace_ratio TEXT, cxl_rate_28d TEXT, comp_index TEXT, event_score TEXT,
  created_at      TEXT NOT NULL,
  UNIQUE (entity_type, entity_id, for_date, as_of_date));

CREATE TABLE dp_forecast (
  forecast_id     TEXT PRIMARY KEY,                    -- dpf_
  level           TEXT NOT NULL CHECK (level IN ('city','region','national')),
  level_key       TEXT NOT NULL,                       -- city_id | region name | 'all'
  for_date TEXT NOT NULL, as_of_date TEXT NOT NULL,
  p10 TEXT NOT NULL, p50 TEXT NOT NULL, p90 TEXT NOT NULL,
  normal_level    TEXT NOT NULL,                       -- demand-index denominator
  credibility     TEXT NOT NULL,                       -- z in [0,1] (section 7.4)
  confidence_band TEXT NOT NULL CHECK (confidence_band IN ('high','medium','low')),   -- enums.json
  method          TEXT NOT NULL CHECK (method IN ('pickup_lgbmq','pickup_conformal','lgbm','trailing_naive')),
  model_version   TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE (level, level_key, for_date, as_of_date, model_version));

CREATE TABLE dp_model_selection (           -- G1: which model won, on which data, by how much
  selection_id    TEXT PRIMARY KEY,                    -- dpms_
  as_of_date      TEXT NOT NULL, window_from_date TEXT NOT NULL, window_to_date TEXT NOT NULL,
  component       TEXT NOT NULL CHECK (component IN ('p50','interval')),
  champion        TEXT NOT NULL, challenger TEXT,
  scores          TEXT NOT NULL CHECK (json_valid(scores)),   -- {"naive":{"dev":"0.487","mae":"0.144"},"pickup":{…},…}
  dm_p_value      TEXT, decision TEXT NOT NULL CHECK (decision IN ('keep','switch','fallback_naive')),
  params          TEXT NOT NULL CHECK (json_valid(params)),   -- estimated k, κ, windows, ACI alpha
  created_at      TEXT NOT NULL);

-- THE decision record: one row per entity x stay date x cycle -------------------------
CREATE TABLE dp_price_decision (
  decision_id     TEXT PRIMARY KEY,                    -- dpd_
  cycle_id        TEXT NOT NULL REFERENCES dp_cycle(cycle_id),
  business_date   TEXT NOT NULL,
  entity_type     TEXT NOT NULL, entity_id TEXT NOT NULL, for_date TEXT NOT NULL,
  currency        TEXT NOT NULL REFERENCES currencies(iso4217),
  baseline_price TEXT NOT NULL, raw_price TEXT NOT NULL,
  published_price TEXT NOT NULL, live_price_before TEXT NOT NULL,
  clamp_status    TEXT NOT NULL CHECK (clamp_status IN ('accepted','clamped','not_applicable')),
  clamp_bound     TEXT CHECK (clamp_bound IN ('floor','ceiling','max_daily_movement','max_weekly_movement')),
  bound_value     TEXT,
  clamp_chain     TEXT NOT NULL CHECK (json_valid(clamp_chain)),   -- [{"guardrail":"max_daily_movement","before":"6840.00","after":"6511.50"}]
  daily_anchor_price TEXT NOT NULL, weekly_anchor_price TEXT NOT NULL,
  factors         TEXT NOT NULL CHECK (json_valid(factors)),       -- [{"name":"demand","value":"1.184","lo":"0.70","hi":"1.30","evidence":{…},"contribution":"512.40"}]
  forecast_id     TEXT REFERENCES dp_forecast(forecast_id),
  feature_id      TEXT REFERENCES dp_feature(feature_id),
  bounds_version  INTEGER NOT NULL, engine_config_version INTEGER NOT NULL, model_version TEXT NOT NULL,
  source          TEXT NOT NULL CHECK (source IN ('engine','override','kill_switch')),
  approval_status TEXT NOT NULL CHECK (approval_status IN ('auto_applied','pending_approval','approved','rejected','superseded')),
  approval_reason TEXT CHECK (approval_reason IN ('outside_auto_band','anomaly_flagged')),
  decided_by TEXT, decision_note TEXT,
  anomaly_flag    INTEGER NOT NULL DEFAULT 0 CHECK (anomaly_flag IN (0,1)),
  is_live         INTEGER NOT NULL CHECK (is_live IN (0,1)),
  status          TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE (cycle_id, entity_type, entity_id, for_date),
  CHECK (clamp_status <> 'clamped' OR (clamp_bound IS NOT NULL AND bound_value IS NOT NULL)),
  CHECK (source = 'engine' OR clamp_status = 'not_applicable'));        -- overrides/kill never counted
CREATE INDEX dp_decision_lookup ON dp_price_decision (entity_type, entity_id, for_date, business_date);
CREATE UNIQUE INDEX dp_decision_live_one ON dp_price_decision (entity_type, entity_id, for_date) WHERE is_live = 1;

-- quotes (maps onto the platform's `holds`: key_hash = idempotency_key, status = hold_status) --------
CREATE TABLE dp_quote (
  quote_id        TEXT PRIMARY KEY,                    -- dpq_
  key_hash        TEXT NOT NULL, session_id TEXT NOT NULL,
  entity_type     TEXT NOT NULL, entity_id TEXT NOT NULL,
  checkin_date TEXT NOT NULL, checkout_date TEXT NOT NULL, party_size INTEGER NOT NULL,
  nightly         TEXT NOT NULL CHECK (json_valid(nightly)),     -- [{"for_date":"2026-10-12","price":"5200.00","decision_id":"dpd_…"}]
  total_price     TEXT NOT NULL, currency TEXT NOT NULL REFERENCES currencies(iso4217),
  locale          TEXT NOT NULL REFERENCES languages(bcp47),
  response_json   TEXT NOT NULL CHECK (json_valid(response_json)),   -- the exact body returned: byte-identical replays
  engine_config_version INTEGER NOT NULL, bounds_versions TEXT NOT NULL, business_date TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('active','confirmed','released','expired')),   -- hold_status
  expires_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX dp_quote_active_key ON dp_quote (key_hash) WHERE status = 'active';

-- control plane --------------------------------------------------------------------
CREATE TABLE dp_override (
  override_id     TEXT PRIMARY KEY,                    -- dpo_
  entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  from_date TEXT NOT NULL, to_date TEXT NOT NULL,
  price TEXT NOT NULL, currency TEXT NOT NULL REFERENCES currencies(iso4217),
  reason          TEXT NOT NULL CHECK (length(trim(reason)) >= 5),
  expires_at      TEXT NOT NULL,
  created_by      TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('active','expired','revoked')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE dp_event_signal (
  signal_id       TEXT PRIMARY KEY,                    -- dps_
  city_id         TEXT NOT NULL REFERENCES cities(city_id),
  title TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  impact_tag      TEXT NOT NULL CHECK (impact_tag IN ('minor','moderate','major')),
  radius_km       TEXT NOT NULL,
  confidence_band TEXT NOT NULL CHECK (confidence_band IN ('high','medium','low')),
  justification TEXT NOT NULL, source_ref TEXT NOT NULL, extracted_by TEXT NOT NULL,
  approved_by TEXT, approved_at TEXT,                  -- NULL ⇒ inert by construction
  status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE dp_narration (
  narration_id    TEXT PRIMARY KEY,                    -- dpn_
  decision_id     TEXT NOT NULL REFERENCES dp_price_decision(decision_id),
  locale          TEXT NOT NULL REFERENCES languages(bcp47),
  text TEXT NOT NULL,
  gate_passed INTEGER NOT NULL CHECK (gate_passed IN (0,1)),
  fallback_used INTEGER NOT NULL CHECK (fallback_used IN (0,1)),
  attempts INTEGER NOT NULL, model_version TEXT NOT NULL, prompt_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (decision_id, locale));

CREATE TABLE dp_experiment (
  experiment_id   TEXT PRIMARY KEY,                    -- dpe_
  name TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('what_if','ab_split')),
  config_a TEXT NOT NULL CHECK (json_valid(config_a)), config_b TEXT NOT NULL CHECK (json_valid(config_b)),
  split_pct TEXT, window_from_date TEXT NOT NULL, window_to_date TEXT NOT NULL,
  prompt_text TEXT, metrics TEXT CHECK (metrics IS NULL OR json_valid(metrics)),
  assumptions TEXT NOT NULL CHECK (json_valid(assumptions)),
  status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE dp_catalog_link (                         -- future view onto hotel_room_types(room_type_id, hotel_id)
  link_id         TEXT PRIMARY KEY,                    -- dpk_
  room_type_id    TEXT NOT NULL UNIQUE,
  hotel_id        TEXT NOT NULL REFERENCES hotels(hotel_id),
  city_id         TEXT NOT NULL REFERENCES cities(city_id),
  room_name       TEXT NOT NULL,                       -- display label, e.g. 'Deluxe King' (synthetic, deterministic)
  link_source     TEXT NOT NULL CHECK (link_source IN ('provided','synthetic')),
  status TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE dp_audit_log (
  audit_id        TEXT PRIMARY KEY,                    -- dpl_
  seq             INTEGER NOT NULL UNIQUE,             -- chain order
  actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
  before_json TEXT, after_json TEXT, reason TEXT,
  prev_hash TEXT, row_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER dp_audit_no_update BEFORE UPDATE ON dp_audit_log
  BEGIN SELECT RAISE(ABORT, 'dp_audit_log is append-only'); END;
CREATE TRIGGER dp_audit_no_delete BEFORE DELETE ON dp_audit_log
  BEGIN SELECT RAISE(ABORT, 'dp_audit_log is append-only'); END;

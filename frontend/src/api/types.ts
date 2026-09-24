/** Response shapes of the PixelMinds API (request bodies are typed from docs/openapi.json via `npm run gen:api`). */
import type { Money } from "../lib/money";

export type Bound = "ceiling" | "floor" | "max_daily_movement" | "max_weekly_movement";

export interface City { city_id: string; name: string; state: string | null; primary_language: string; region: string; rooms: number }
export interface CatalogCities { business_date: string; bookable_from: string; bookable_to: string; cities: City[] }
export interface Room {
  room_type_id: string; room_name: string; hotel_id: string; hotel_name: string; star_rating: number; guest_score: number | null;
  review_count: number; property_type: string; distance_to_centre_km: string; address_line: string; currency: string;
  from_price: string; sparkline: { d: string; p: string }[]; checkin_time: string; checkout_time: string;
}
export interface Quote {
  quote_id: string; status: string; entity_id: string; checkin_date: string; checkout_date: string; party_size: number;
  nightly: { for_date: string; price: Money; decision_id: string }[]; total: Money; expires_at: string; locale: string;
  reasons: { text: string; locale: string; source: "llm" | "template" }[]; confidence_band: string; warnings: string[];
}

export interface ClampSummary {
  entity_id: string; total: number; clamped: number; headline: string; controlled: number;
  by_bound: Record<Bound, number>; business_date: string; cycle_id: string;
}
export interface CurvePoint {
  for_date: string; decision_id: string; baseline: string; raw: string; published: string; floor: string; ceiling: string;
  /** effective floor/ceiling for this night: hotel bounds narrowed by the operating band around the reference rate */
  floor_used?: string; ceiling_used?: string;
  currency: string; clamp_status: "accepted" | "clamped" | "not_applicable"; clamp_bound: Bound | null; bound_value: string | null;
  source: "engine" | "override" | "kill_switch"; approval_status: string; anomaly: boolean;
  pending: { decision_id: string; price: string; reason: string } | null;
  forecast: { p10: string; p50: string; p90: string; band: string } | null;
}
export interface Curve {
  entity_id: string; currency: string; floor: string; ceiling: string; points: CurvePoint[]; summary: ClampSummary;
  room: { room_name: string; hotel_name: string | null; city_name: string | null; star_rating?: number; link_source?: string };
}
export interface WaterfallStep { step: string; multiplier: string | null; contribution: string }
export interface FactorItem { name: string; value: string; unclamped: string; lo: string; hi: string; evidence: Record<string, unknown>; contribution: string }
export interface Explain {
  decision_id: string; entity_id: string; for_date: string; business_date: string; currency: string;
  baseline: string; raw: string; published: string; live_before: string; source: string;
  clamp: { status: string; bound: Bound | null; bound_value: string | null; chain: { guardrail: string; before: string; after: string; basis?: "hotel_bound" | "operating_band" }[] };
  limits?: { hotel_floor: string; hotel_ceiling: string; floor_used: string; ceiling_used: string;
    band: { below: string; above: string } | null; max_daily_move_pct: string; max_weekly_move_pct: string };
  anchors: { daily: string; weekly: string }; waterfall: WaterfallStep[]; factors: FactorItem[]; top_drivers: string[];
  inputs: Record<string, unknown>;
  forecast: { p10: string; p50: string; p90: string; normal: string; band: string; method: string; level: string; credibility: string } | null;
  approval: { status: string; reason: string | null; decided_by: string | null; note: string | null; anomaly: boolean };
  versions: { bounds: number; engine_config: number; model: string }; reconstruction_ok: boolean; replay_ok: boolean | null;
}
export interface Entity { entity_id: string; room_name: string; hotel_name: string; city_name: string; city_id: string; currency: string }
export interface Pending {
  decision_id: string; entity_id: string; for_date: string; live_price_before: string; published_price: string; currency: string;
  approval_reason: string; anomaly_flag: number; clamp_bound: string | null; room_name: string | null; hotel_name: string | null; summary: string;
}
export interface Signal {
  signal_id: string; city_id: string; city_name: string; title: string; start_date: string; end_date: string; impact_tag: string;
  radius_km: string; confidence_band: string; justification: string; source_ref: string; extracted_by: string;
  approved_by: string | null; approved_at: string | null;
}
export interface ProofCheck { check: string; ok: boolean; detail: string; ms: number }
export interface Proof { ok: boolean; checks: ProofCheck[]; note: string }
export interface AuditEntry { audit_id: string; seq: number; actor: string; action: string; target: string; reason: string | null; created_at: string; row_hash: string }
export interface CycleSummary { cycle_id: string; kind: string; business_date: string; decisions: number; clamped_live: number; pending_approval: number }
export interface WhatIfParse { accepted: boolean; config: Record<string, unknown> | null; errors: string[]; source: string }
export interface SimResult {
  experiment_id: string; entity_id: string; window: [string, string];
  A: SimSide; B: SimSide; revenue_change_pct: Record<string, number>; revenue_change_range_pct: [number, number];
  demand_change_pct: Record<string, number>;
  per_date: { for_date: string; a: string; b: string; a_bound: string | null; b_bound: string | null }[];
  assumptions: { elasticity: { elasticity: number; interval80: [number, number]; data_slope: number | null; cells: number; method: string } };
}
export interface SimSide { dates: number; avg_price: string; clamps: Record<Bound, number>; clamped: number; approvals_needed: number }

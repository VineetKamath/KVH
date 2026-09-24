-- APS-02 — Real-Time Dynamic Pricing & Demand Forecasting
-- Starter queries. Every one runs as-is against data/APS-02.db.
--
-- CAST(x AS REAL) appears below only for sorting and rough exploration.
-- Never use it for a value you will show someone or add to another value.

-- ==========================================================================
-- 1. Thirteen months of signal, by month — the seasonality is visible
-- If your forecast is a straight line, look here first.
-- ==========================================================================
SELECT substr(occurred_at,1,7) AS month, event_type, COUNT(*) AS events
     FROM pricing_events GROUP BY month, event_type ORDER BY month, event_type;

-- ==========================================================================
-- 2. Search-to-booking conversion by lead time
-- lead_time_days is the strongest single feature in this dataset.
-- ==========================================================================
SELECT lead_time_days,
          SUM(CASE WHEN event_type='search'  THEN 1 ELSE 0 END) AS searches,
          SUM(CASE WHEN event_type='booking' THEN 1 ELSE 0 END) AS bookings
     FROM pricing_events GROUP BY lead_time_days ORDER BY lead_time_days;

-- ==========================================================================
-- 3. The guardrails your price must respect
-- A dynamic price outside these is a failing demo, not a clever one.
-- ==========================================================================
SELECT b.entity_type, b.floor_price, b.ceiling_price, b.currency,
          b.max_daily_move_pct, b.max_weekly_move_pct, b.rounding_step, b.override_active
     FROM price_bounds b ORDER BY b.override_active DESC LIMIT 15;

-- ==========================================================================
-- 4. A worked price curve with its driving factors
-- This is the explainability shape the admin dashboard has to produce.
-- ==========================================================================
SELECT effective_date, price, baseline_price, demand_index, occupancy_pct,
          lead_time_factor, seasonality_factor, event_factor, competitor_factor,
          bound_clamped, explanation
     FROM price_history
    WHERE entity_id = (SELECT entity_id FROM price_history ORDER BY entity_id LIMIT 1)
    ORDER BY effective_date;

-- ==========================================================================
-- 5. Where the bounds actually bit
-- Clamped rows are the interesting ones — they are where rules beat the model.
-- ==========================================================================
SELECT COUNT(*) AS clamped_rows,
          ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM price_history),2) AS pct
     FROM price_history WHERE bound_clamped = 1;

-- ==========================================================================
-- 6. Cancellations, which a naive forecast will ignore
-- Demand net of cancellation is not the same series as demand.
-- ==========================================================================
SELECT substr(occurred_at,1,7) AS month,
          SUM(CASE WHEN event_type='booking' THEN 1 ELSE 0 END) AS bookings,
          SUM(CASE WHEN event_type='cancellation' THEN 1 ELSE 0 END) AS cancellations
     FROM pricing_events GROUP BY month ORDER BY month;

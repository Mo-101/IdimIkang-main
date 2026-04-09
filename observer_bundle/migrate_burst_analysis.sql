-- Idim Ikang migration: signal_family column + analysis views
-- Safe to run multiple times (IF NOT EXISTS / OR REPLACE).

-- 1. Add signal_family column to signals table
ALTER TABLE signals ADD COLUMN IF NOT EXISTS signal_family TEXT DEFAULT 'none';

-- 2. Backfill from reason_trace where available
UPDATE signals
SET signal_family = reason_trace->>'signal_family'
WHERE signal_family IS NULL OR signal_family = 'none'
  AND reason_trace->>'signal_family' IS NOT NULL
  AND reason_trace->>'signal_family' != 'none';

-- 3. Index
CREATE INDEX IF NOT EXISTS idx_signals_signal_family_ts
    ON signals (signal_family, ts DESC);

-- 4. Enhanced calibration view (now includes signal_family)
DROP VIEW IF EXISTS signal_context_calibration;
CREATE OR REPLACE VIEW signal_context_calibration AS
WITH base AS (
    SELECT
        COALESCE(policy_version, 'legacy') AS policy_version,
        COALESCE(market_regime, regime) AS market_regime,
        side,
        signal_hour_utc,
        COALESCE(btc_regime, NULLIF(reason_trace->>'btc_regime', ''), 'UNKNOWN') AS btc_regime,
        COALESCE(phase2_gate, NULLIF(reason_trace->>'phase2_gate', ''), 'allowed') AS phase2_gate,
        COALESCE(phase2_allowed, (reason_trace->>'phase2_allowed')::boolean, TRUE) AS phase2_allowed,
        COALESCE(signal_family, reason_trace->>'signal_family', 'none') AS signal_family,
        outcome,
        r_multiple
    FROM signals
    WHERE outcome IS NOT NULL
)
SELECT
    policy_version,
    market_regime,
    side,
    signal_hour_utc,
    btc_regime,
    phase2_gate,
    phase2_allowed,
    signal_family,
    COUNT(*) AS trades,
    SUM(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN 1 ELSE 0 END) AS losses,
    ROUND((AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
    ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
    ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN r_multiple END)::numeric, 4) AS avg_win_r,
    ROUND(ABS(AVG(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN r_multiple END))::numeric, 4) AS avg_loss_r_abs,
    ROUND((
        COALESCE(AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN r_multiple END), 0)
        * AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)
        -
        COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN r_multiple END)), 0)
        * (1 - AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END))
    )::numeric, 4) AS expectancy_r
FROM base
GROUP BY policy_version, market_regime, side, signal_hour_utc, btc_regime, phase2_gate, phase2_allowed, signal_family;

-- 5. Burst vs strict cohort comparison
CREATE OR REPLACE VIEW burst_vs_strict_comparison AS
WITH cohort AS (
    SELECT
        CASE
            WHEN policy_version = 'phase2_data_burst_v1' THEN 'burst'
            ELSE 'strict'
        END AS cohort,
        COALESCE(market_regime, regime) AS market_regime,
        side,
        COALESCE(signal_family, reason_trace->>'signal_family', 'none') AS signal_family,
        outcome,
        r_multiple
    FROM signals
    WHERE outcome IS NOT NULL
)
SELECT
    cohort,
    market_regime,
    side,
    signal_family,
    COUNT(*) AS trades,
    SUM(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN 1 ELSE 0 END) AS losses,
    ROUND((AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
    ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
    ROUND((
        COALESCE(AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN r_multiple END), 0)
        * AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)
        -
        COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN r_multiple END)), 0)
        * (1 - AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END))
    )::numeric, 4) AS expectancy_r
FROM cohort
GROUP BY cohort, market_regime, side, signal_family
ORDER BY cohort, expectancy_r DESC;

-- 6. Burst hour performance for tightening decisions
CREATE OR REPLACE VIEW burst_hour_performance AS
WITH burst AS (
    SELECT
        signal_hour_utc,
        COALESCE(market_regime, regime) AS market_regime,
        side,
        outcome,
        r_multiple
    FROM signals
    WHERE outcome IS NOT NULL
      AND policy_version = 'phase2_data_burst_v1'
)
SELECT
    signal_hour_utc,
    market_regime,
    side,
    COUNT(*) AS trades,
    ROUND((AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
    ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
    ROUND((
        COALESCE(AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN r_multiple END), 0)
        * AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)
        -
        COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN r_multiple END)), 0)
        * (1 - AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END))
    )::numeric, 4) AS expectancy_r
FROM burst
GROUP BY signal_hour_utc, market_regime, side
ORDER BY expectancy_r DESC;

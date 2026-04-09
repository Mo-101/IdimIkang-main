-- bootstrap.sql
-- Run this while connected to the target PostgreSQL database.
-- Database creation and psql meta-commands are omitted so the script also works
-- in managed PostgreSQL runners such as Neon migrations and web SQL editors.

-- =========================
-- Utility: updated_at trigger
-- =========================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================
-- signals
-- =========================
CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    signal_id UUID NOT NULL UNIQUE,

    exchange TEXT NOT NULL DEFAULT 'BINANCE',
    pair TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,

    side TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),

    entry NUMERIC NOT NULL CHECK (entry > 0),
    stop_loss NUMERIC NOT NULL CHECK (stop_loss > 0),
    take_profit NUMERIC NOT NULL CHECK (take_profit > 0),

    score NUMERIC NOT NULL CHECK (score >= 0),
    regime TEXT NOT NULL,
    market_regime TEXT,
    btc_regime TEXT,
    signal_hour_utc INT,
    phase2_gate TEXT,
    phase2_allowed BOOLEAN,
    phase2_score_multiplier NUMERIC,
    setup_score NUMERIC,
    execution_score NUMERIC,
    policy_version TEXT,
    policy_activated_at TIMESTAMPTZ,
    signal_family TEXT DEFAULT 'none',

    reason_trace JSONB NOT NULL DEFAULT '{}'::jsonb,

    logic_version TEXT NOT NULL,
    config_version TEXT NOT NULL,

    outcome TEXT NULL CHECK (
        outcome IN (
            'WIN',
            'LOSS',
            'EXPIRED',
            'PARTIAL_WIN',
            'ARCHIVED_V1',
            'LIVE_WIN',
            'LIVE_LOSS',
            'LIVE_PARTIAL'
        )
    ),

    r_multiple NUMERIC NULL,
    source TEXT NOT NULL DEFAULT 'observer_live',

    execution_id TEXT NULL,
    execution_source TEXT NOT NULL DEFAULT 'simulated'
        CHECK (execution_source IN ('simulated', 'live')),

    fill_price NUMERIC NULL CHECK (fill_price IS NULL OR fill_price > 0),
    exchange_status TEXT NULL,

    execution_logs JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    is_partial BOOLEAN NOT NULL DEFAULT FALSE,
    trailing_sl NUMERIC NULL CHECK (trailing_sl IS NULL OR trailing_sl > 0),
    adverse_excursion NUMERIC NULL CHECK (adverse_excursion IS NULL OR adverse_excursion >= 0),

    lesson TEXT NULL,

    -- Basic directional consistency
    CONSTRAINT chk_signal_price_structure CHECK (
        (side = 'LONG'  AND stop_loss < entry AND take_profit > entry)
        OR
        (side = 'SHORT' AND stop_loss > entry AND take_profit < entry)
    ),

    -- If partial, outcome should match a partial-style state when present
    CONSTRAINT chk_partial_consistency CHECK (
        NOT is_partial
        OR outcome IS NULL
        OR outcome IN ('PARTIAL_WIN', 'LIVE_PARTIAL')
    )
);

DROP TRIGGER IF EXISTS trg_signals_set_updated_at ON signals;
CREATE TRIGGER trg_signals_set_updated_at
BEFORE UPDATE ON signals
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_pair_ts
    ON signals (pair, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_exchange_pair_ts
    ON signals (exchange, pair, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_ts
    ON signals (ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_outcome
    ON signals (outcome);

-- Better index for "open positions" queries
CREATE INDEX IF NOT EXISTS idx_signals_open_ts
    ON signals (ts DESC)
    WHERE outcome IS NULL;

CREATE INDEX IF NOT EXISTS idx_signals_execution_source
    ON signals (execution_source);

CREATE INDEX IF NOT EXISTS idx_signals_exchange_status
    ON signals (exchange_status);

CREATE INDEX IF NOT EXISTS idx_signals_source_ts
    ON signals (source, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_signal_id
    ON signals (signal_id);

CREATE INDEX IF NOT EXISTS idx_signals_policy_version_ts
    ON signals (policy_version, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_market_context
    ON signals (market_regime, side, signal_hour_utc, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_btc_regime_ts
    ON signals (btc_regime, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_signal_family_ts
    ON signals (signal_family, ts DESC);

-- Optional: useful for truth ladder reconciliation
CREATE INDEX IF NOT EXISTS idx_signals_execution_id
    ON signals (execution_id)
    WHERE execution_id IS NOT NULL;

-- =========================
-- system_logs
-- =========================
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    level TEXT NOT NULL CHECK (
        level IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL')
    ),

    component TEXT NOT NULL,
    event TEXT NOT NULL,

    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_system_logs_ts
    ON system_logs (ts DESC);

CREATE INDEX IF NOT EXISTS idx_system_logs_component_ts
    ON system_logs (component, ts DESC);

CREATE INDEX IF NOT EXISTS idx_system_logs_event_ts
    ON system_logs (event, ts DESC);

-- =========================
-- training_candidates (v1.0)
-- =========================
-- Labeled dataset for gating model training.
-- Records both rejected and passed candidates with market state snapshot.
CREATE TABLE IF NOT EXISTS training_candidates (
    id                      BIGSERIAL PRIMARY KEY,
    ts                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Identity
    symbol                  TEXT NOT NULL,
    side                    TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    scan_profile            TEXT NOT NULL,      -- "sim_loose_v1", "live_strict_v1"
    feature_version         TEXT NOT NULL,      -- "v1.0" — bump when indicators change
    signal_family           TEXT,               -- "trend", "volatility", "mean_reversion", "momentum", "none"
    gate_profile            JSONB,              -- JSON snapshot of active thresholds
    family_indicators       JSONB,              -- family-specific feature snapshot
    trace_data              JSONB,              -- raw sovereign trace / Phase 2 metadata

    -- Gate audit
    rejection_gate          TEXT,               -- NULL = passed all gates
    would_have_passed_live  BOOLEAN,            -- did it meet live thresholds?

    -- Market state snapshot
    regime                  TEXT,
    btc_regime              TEXT,
    close_price             NUMERIC,
    adx14                   NUMERIC,
    rsi14                   NUMERIC,
    atr_stretch             NUMERIC,            -- distance from EMA in ATRs
    squeeze_on              BOOLEAN,
    squeeze_fired           BOOLEAN,
    vol_ratio               NUMERIC,
    funding_rate            NUMERIC,
    ls_ratio                NUMERIC,
    score                   NUMERIC,

    -- Outcomes (filled later by outcome_tracker)
    outcome_label           TEXT,               -- WIN / LOSS / NEUTRAL
    outcome_pct             NUMERIC,
    mae_pct                 NUMERIC,            -- max adverse excursion
    mfe_pct                 NUMERIC,            -- max favorable excursion
    horizon_bars            INT,                -- bars until outcome resolved

    -- Metadata
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for training data queries
CREATE INDEX IF NOT EXISTS idx_training_candidates_symbol_ts
    ON training_candidates (symbol, ts DESC);

CREATE INDEX IF NOT EXISTS idx_training_candidates_scan_profile
    ON training_candidates (scan_profile, ts DESC);

CREATE INDEX IF NOT EXISTS idx_training_candidates_signal_family
    ON training_candidates (signal_family, ts DESC);

CREATE INDEX IF NOT EXISTS idx_training_candidates_rejection_gate
    ON training_candidates (rejection_gate, ts DESC)
    WHERE rejection_gate IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_training_candidates_outcome_label
    ON training_candidates (outcome_label, ts DESC)
    WHERE outcome_label IS NOT NULL;

-- =========================
-- signal_context_calibration
-- =========================
-- Cohort view for expectancy-based calibration by policy + market context.
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

-- =========================
-- burst_vs_strict_comparison
-- =========================
-- Direct cohort comparison: burst period vs strict period.
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

-- =========================
-- burst_hour_performance
-- =========================
-- Hour-of-day expectancy during burst for tightening decisions.
CREATE OR REPLACE VIEW burst_hour_performance AS
SELECT
    signal_hour_utc,
    COALESCE(market_regime, regime) AS market_regime,
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
FROM signals
WHERE outcome IS NOT NULL
  AND policy_version = 'phase2_data_burst_v1'
GROUP BY signal_hour_utc, market_regime, side
ORDER BY expectancy_r DESC;

CREATE INDEX IF NOT EXISTS idx_training_candidates_would_have_passed_live
    ON training_candidates (would_have_passed_live, scan_profile, ts DESC);
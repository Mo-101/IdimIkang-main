CREATE DATABASE idim_ikang;

\connect idim_ikang;

CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    signal_id UUID NOT NULL UNIQUE,
    pair TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    entry NUMERIC NOT NULL,
    stop_loss NUMERIC NOT NULL,
    take_profit NUMERIC NOT NULL,
    score NUMERIC NOT NULL,
    regime TEXT NOT NULL,
    reason_trace JSONB NOT NULL,
    logic_version TEXT NOT NULL,
    config_version TEXT NOT NULL,
    outcome TEXT NULL CHECK (outcome IN ('WIN', 'LOSS', 'EXPIRED')),
    r_multiple NUMERIC NULL,
    source TEXT NOT NULL DEFAULT 'observer_live',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_pair_ts ON signals(pair, ts DESC);
CREATE INDEX IF NOT EXISTS idx_signals_outcome_null ON signals(outcome) WHERE outcome IS NULL;

CREATE TABLE IF NOT EXISTS system_logs (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    event TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_system_logs_ts ON system_logs(ts DESC);

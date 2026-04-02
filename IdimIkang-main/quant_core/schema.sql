CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    regime VARCHAR(50) NOT NULL,
    score NUMERIC NOT NULL,
    entry_range JSONB NOT NULL,
    stop_loss NUMERIC NOT NULL,
    take_profit JSONB NOT NULL,
    reason_trace JSONB NOT NULL,
    logic_version VARCHAR(50) NOT NULL,
    config_version VARCHAR(50) NOT NULL,
    alert_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

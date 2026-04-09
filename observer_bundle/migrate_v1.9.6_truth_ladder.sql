-- Idim Ikang v1.9.6 Truth Ladder Migration
-- Adds fields to distinguish between simulated and exchange-verified outcomes

-- 1. Execution Tracking
ALTER TABLE signals ADD COLUMN IF NOT EXISTS execution_id TEXT; -- Exchange Order ID (PostgreSQL syntax)
ALTER TABLE signals ADD COLUMN IF NOT EXISTS execution_source TEXT DEFAULT 'simulated';
ALTER TABLE signals ADD COLUMN IF NOT EXISTS fill_price NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS exchange_status TEXT; -- 'open', 'closed', 'canceled', 'expired'

ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_execution_source_check;
ALTER TABLE signals
ADD CONSTRAINT signals_execution_source_check
CHECK (execution_source IN ('simulated', 'live'));

-- 2. Audit Trail
ALTER TABLE signals ADD COLUMN IF NOT EXISTS execution_logs JSONB DEFAULT '[]'::jsonb;

-- 3. Update outcome check for more granular states
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_outcome_check;
ALTER TABLE signals ADD CONSTRAINT signals_outcome_check CHECK (
  outcome IN ('WIN', 'LOSS', 'EXPIRED', 'PARTIAL_WIN', 'ARCHIVED_V1', 'LIVE_WIN', 'LIVE_LOSS', 'LIVE_PARTIAL')
);

-- 4. Backfill execution truth for existing rows
UPDATE signals
SET execution_source = 'simulated'
WHERE execution_source IS NULL;

UPDATE signals
SET exchange_status = CASE
    WHEN outcome = 'EXPIRED' THEN 'expired'
    WHEN outcome IS NOT NULL AND execution_source = 'live' THEN 'closed'
    WHEN outcome IS NULL AND execution_source = 'live' THEN 'open'
    ELSE exchange_status
END
WHERE exchange_status IS NULL;

-- 5. Performance indexes for truth and freshness queries (PostgreSQL/Neon)
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts DESC);
CREATE INDEX IF NOT EXISTS idx_signals_outcome ON signals(outcome);
CREATE INDEX IF NOT EXISTS idx_signals_execution_source ON signals(execution_source);
CREATE INDEX IF NOT EXISTS idx_signals_exchange_status ON signals(exchange_status);
CREATE INDEX IF NOT EXISTS idx_signals_source_ts ON signals(source, ts DESC);

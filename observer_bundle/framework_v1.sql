-- IDIM IKANG MULTI-LAYERED ANALYSIS FRAMEWORK v1
-- Implementation of table structures, indexes, and join views for Funding, OI, and L/S ratios.

-- 1. Create assumption tables (collectors)
CREATE TABLE IF NOT EXISTS funding_rates (
  exchange text,
  pair text,
  ts timestamptz,
  funding_rate numeric,
  PRIMARY KEY (exchange, pair, ts)
);

CREATE TABLE IF NOT EXISTS open_interest_snapshots (
  exchange text,
  pair text,
  ts timestamptz,
  open_interest numeric,
  PRIMARY KEY (exchange, pair, ts)
);

CREATE TABLE IF NOT EXISTS long_short_ratios (
  exchange text,
  pair text,
  ts timestamptz,
  ls_ratio numeric,
  PRIMARY KEY (exchange, pair, ts)
);

-- 2. Create recommended indexes
CREATE INDEX IF NOT EXISTS idx_signals_pair_ts ON signals(exchange, pair, ts);
CREATE INDEX IF NOT EXISTS idx_funding_pair_ts ON funding_rates(exchange, pair, ts DESC);
CREATE INDEX IF NOT EXISTS idx_oi_pair_ts ON open_interest_snapshots(exchange, pair, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ls_pair_ts ON long_short_ratios(exchange, pair, ts DESC);

-- 3. Build the feature join view
-- For each signal, join the most recent prior funding rate, open interest, and long/short ratio.
CREATE OR REPLACE VIEW signal_feature_snapshot AS
SELECT
    s.signal_id,
    s.exchange,
    s.pair,
    s.ts,
    s.side,
    s.score,
    s.regime,
    s.outcome,
    s.r_multiple,

    fr.ts  AS funding_ts,
    fr.funding_rate,

    oi.ts  AS oi_ts,
    oi.open_interest,

    ls.ts  AS ls_ts,
    ls.ls_ratio

FROM signals s

LEFT JOIN LATERAL (
    SELECT f.ts, f.funding_rate
    FROM funding_rates f
    WHERE f.exchange = s.exchange
      AND f.pair = s.pair
      AND f.ts <= s.ts
    ORDER BY f.ts DESC
    LIMIT 1
) fr ON TRUE

LEFT JOIN LATERAL (
    SELECT o.ts, o.open_interest
    FROM open_interest_snapshots o
    WHERE o.exchange = s.exchange
      AND o.pair = s.pair
      AND o.ts <= s.ts
    ORDER BY o.ts DESC
    LIMIT 1
) oi ON TRUE

LEFT JOIN LATERAL (
    SELECT l.ts, l.ls_ratio
    FROM long_short_ratios l
    WHERE l.exchange = s.exchange
      AND l.pair = s.pair
      AND l.ts <= s.ts
    ORDER BY l.ts DESC
    LIMIT 1
) ls ON TRUE

WHERE s.outcome IN ('WIN','LOSS');

-- 4. Optional freshness guard
CREATE OR REPLACE VIEW signal_feature_snapshot_fresh AS
SELECT *
FROM signal_feature_snapshot
WHERE (funding_ts IS NULL OR ts - funding_ts <= interval '12 hours')
  AND (oi_ts      IS NULL OR ts - oi_ts      <= interval '2 hours')
  AND (ls_ts      IS NULL OR ts - ls_ts      <= interval '2 hours');

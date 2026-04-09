-- Task 2: Check logic version distribution
SELECT logic_version, COUNT(*) 
FROM signals 
GROUP BY logic_version 
ORDER BY logic_version;

-- Task 3A: Regime distribution over observation window
SELECT regime, COUNT(*) as signal_count,
       MIN(ts) as first_signal,
       MAX(ts) as last_signal
FROM signals
WHERE logic_version = 'v1.3-ranked-observer'
GROUP BY regime
ORDER BY signal_count DESC;

-- Task 3B: Pair distribution within STRONG_UPTREND cell
SELECT pair, regime, CAST(score AS int) / 5 * 5 as score_bucket, 
       COUNT(*) as signals
FROM signals
WHERE logic_version = 'v1.3-ranked-observer'
  AND regime = 'STRONG_UPTREND'
GROUP BY pair, regime, score_bucket
ORDER BY signals DESC;

-- Task 4A: Stuck signals older than 24h with NULL outcome
SELECT COUNT(*) as stuck_signals
FROM signals
WHERE outcome IS NULL
  AND ts < NOW() - INTERVAL '24 hours';
-- Task 4B: Recent outcome tracker resolution activity
SELECT outcome, COUNT(*) as count, 
       MAX(ts) as most_recent
FROM signals 
WHERE logic_version = 'v1.3-ranked-observer'
GROUP BY outcome
ORDER BY outcome;

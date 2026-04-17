-- Sunday Review Queries for IDIM IKANG
-- Execute these queries one by one and paste results

-- Query 2: Core row counts
SELECT (SELECT COUNT(*) FROM signals) as signals, 
       (SELECT COUNT(*) FROM funding_rates) as funding, 
       (SELECT COUNT(*) FROM open_interest) as oi, 
       (SELECT COUNT(*) FROM ls_ratios) as ls;

-- Query 3: Outcome distribution
SELECT COALESCE(outcome, 'UNRESOLVED') as outcome, COUNT(*) 
FROM signals 
GROUP BY COALESCE(outcome, 'UNRESOLVED') 
ORDER BY outcome;

-- Query 4: Current WR / PF
SELECT COUNT(*) AS resolved_signals, 
       SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) AS wins, 
       SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses, 
       ROUND(100.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(SUM(CASE WHEN outcome IN ('WIN','LOSS') THEN 1 ELSE 0 END),0), 4) AS win_rate_pct, 
       ROUND(3.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END),0), 4) AS profit_factor 
FROM signals 
WHERE outcome IN ('WIN','LOSS');

-- Query 5: Density by pair
SELECT pair, COUNT(*) 
FROM signals 
GROUP BY pair 
ORDER BY COUNT(*) DESC, pair;

-- Query 6: Density by Wolfram cell
SELECT regime, ROUND(score)::int AS score_bucket, COUNT(*) 
FROM signals 
GROUP BY regime, ROUND(score)::int 
ORDER BY COUNT(*) DESC, regime, score_bucket;

-- Query 7: Recent anomalies
SELECT ts, level, component, event 
FROM system_logs 
WHERE level IN ('WARN','ERROR') 
ORDER BY ts DESC 
LIMIT 50;

-- Query 8: Freshness check
SELECT (SELECT MAX(ts) FROM signals) AS last_signal_ts, 
       (SELECT MAX(ts) FROM funding_rates) AS last_funding_ts, 
       (SELECT MAX(ts) FROM open_interest) AS last_oi_ts, 
       (SELECT MAX(ts) FROM ls_ratios) AS last_ls_ts, 
       (SELECT MAX(ts) FROM system_logs) AS last_log_ts;

-- Task 4: Check what errors the outcome tracker is hitting
SELECT ts, event, details 
FROM system_logs 
WHERE component = 'outcome_tracker' 
  AND event = 'per_signal_error'
ORDER BY ts DESC
LIMIT 10;

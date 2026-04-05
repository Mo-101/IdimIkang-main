SELECT pair, regime, outcome, COUNT(*) as cnt
FROM signals
WHERE logic_version = 'v1.3-ranked-observer'
GROUP BY pair, regime, outcome
ORDER BY pair, regime, outcome;

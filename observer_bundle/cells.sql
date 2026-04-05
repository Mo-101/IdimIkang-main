SELECT regime, (CAST(score AS int) / 5) * 5 as score_bucket, outcome, COUNT(*) 
FROM signals 
WHERE logic_version = 'v1.3-ranked-observer' 
GROUP BY regime, score_bucket, outcome 
ORDER BY regime, score_bucket, outcome;

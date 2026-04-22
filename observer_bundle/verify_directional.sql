SELECT 
    directional_primary_side,
    side AS emitted_side,
    COUNT(*) AS cnt
FROM training_candidates
WHERE created_at > NOW() - INTERVAL '15 minutes'
GROUP BY 1,2
ORDER BY 1,2;

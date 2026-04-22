SELECT 
    side,
    trace_data->'pwin' as pwin,
    trace_data->'prob_score' as prob_score,
    trace_data->'legacy_score' as legacy_score,
    created_at 
FROM training_candidates 
WHERE created_at > NOW() - INTERVAL '5 minutes' 
ORDER BY created_at DESC 
LIMIT 10;

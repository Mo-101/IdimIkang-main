SELECT 
    side,
    regime,
    trace_data->'regime_prior' as prior,
    trace_data->'z_pre_prior' as z_pre,
    trace_data->'z' as z_post,
    ROUND((trace_data->>'prob_score')::numeric, 2) as score,
    created_at 
FROM training_candidates 
WHERE created_at > NOW() - INTERVAL '5 minutes' 
ORDER BY created_at DESC 
LIMIT 10;

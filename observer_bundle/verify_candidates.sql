SELECT 
    directional_primary_side, 
    directional_net, 
    score,
    side,
    would_have_passed_live,
    rejection_gate,
    created_at 
FROM training_candidates 
WHERE created_at > NOW() - INTERVAL '15 minutes' 
ORDER BY created_at DESC 
LIMIT 20;

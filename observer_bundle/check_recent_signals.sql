SELECT 
    ts, 
    pair, 
    side, 
    prob_score, 
    pwin, 
    legacy_score,
    score_mode,
    risk_scale,
    market_regime
FROM signals 
ORDER BY ts DESC 
LIMIT 20;

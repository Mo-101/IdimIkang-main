-- Query 1: Persistence on signals
SELECT
  ts,
  pair,
  side,
  prob_score,
  legacy_score,
  pwin,
  z_score,
  score_mode,
  risk_scale,
  rr_sl_mult,
  rr_tp_mult
FROM signals
ORDER BY ts DESC
LIMIT 20;

-- Query 2: Aggregate sanity check on signals
SELECT
  COUNT(*) AS total,
  COUNT(prob_score) AS prob_score_nonnull,
  COUNT(legacy_score) AS legacy_score_nonnull,
  COUNT(pwin) AS pwin_nonnull,
  COUNT(z_score) AS z_score_nonnull,
  COUNT(score_mode) AS score_mode_nonnull
FROM signals
WHERE ts > NOW() - INTERVAL '24 hours';

-- Query 3: Side split (last 24h)
SELECT side, COUNT(*)
FROM signals
WHERE ts > NOW() - INTERVAL '24 hours'
GROUP BY side;

-- Query 4: Probability distribution (last 24h) from training_candidates
SELECT
  side,
  ROUND(AVG((trace_data->>'prob_score')::numeric), 2) AS avg_prob_score,
  ROUND(MAX((trace_data->>'prob_score')::numeric), 2) AS max_prob_score,
  ROUND(MIN((trace_data->>'prob_score')::numeric), 2) AS min_prob_score,
  COUNT(*) AS rows
FROM training_candidates
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND trace_data ? 'prob_score'
GROUP BY side;

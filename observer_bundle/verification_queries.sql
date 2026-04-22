-- 1. How many post-Sprint-D emitted signals exist?
SELECT COUNT(*) AS post_sprint_d_signals
FROM signals
WHERE ts >= TIMESTAMPTZ '2026-04-18 20:20:00+00';

-- 2. How many of those are resolved?
SELECT COUNT(*) AS post_sprint_d_resolved
FROM signals
WHERE ts >= TIMESTAMPTZ '2026-04-18 20:20:00+00'
  AND outcome IS NOT NULL;

-- 3. Are the new fields actually being populated?
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
  rr_tp_mult,
  outcome
FROM signals
WHERE ts >= TIMESTAMPTZ '2026-04-18 20:20:00+00'
ORDER BY ts DESC
LIMIT 20;

-- 4. Count non-null calibration fields
SELECT
  COUNT(*) AS total,
  COUNT(prob_score) AS prob_score_nonnull,
  COUNT(legacy_score) AS legacy_score_nonnull,
  COUNT(pwin) AS pwin_nonnull,
  COUNT(z_score) AS z_score_nonnull,
  COUNT(risk_scale) AS risk_scale_nonnull
FROM signals
WHERE ts >= TIMESTAMPTZ '2026-04-18 20:20:00+00';

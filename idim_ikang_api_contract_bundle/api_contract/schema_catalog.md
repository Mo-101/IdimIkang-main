# Schema Catalog

## Signal
Represents one observer-emitted signal with doctrine-required evidence fields:
- pair
- side
- entry / stop_loss / take_profit
- score / score_bucket
- regime
- reason_trace
- logic_version / config_version
- outcome / r_multiple when resolved later

## SystemStatus
Current observer state:
- running/stopped/degraded
- uptime
- last scan
- last signal summary
- last system log

## Stats
Aggregate observer metrics:
- wins
- losses
- expired
- win rate
- profit factor
- signals/day

## CellPerformance
Performance by `(regime, score_bucket)` cell.

## ReviewBundle
Review-ready artifact summary:
- metadata
- aggregate metrics
- per-pair metrics
- per-cell metrics
- determinism summary
- config snapshot

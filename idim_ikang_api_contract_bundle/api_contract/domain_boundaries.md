# Domain Boundaries

## Real now — observer routes
- `GET /status`
- `GET /signals`
- `GET /stats`
- `GET /cell-performance`
- `GET /review-bundle`
- `POST /kill`

## Real now — analytics/review domain
- aggregate live stats
- per-cell performance
- review bundle generation from current evidence

## Deferred / disabled
These must not be implemented in the current observer phase:
- order placement
- order cancellation
- broker execution
- exchange account control
- portfolio management
- strategy optimization
- auto-trading controls
- execution streaming without reviewed source

## Rule
The contract must not imply execution readiness before doctrine allows it.

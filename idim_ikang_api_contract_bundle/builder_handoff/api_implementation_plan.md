# API Implementation Plan

| Route | Source | Dependency | Mode | Priority | Notes |
|---|---|---|---|---|---|
| `GET /status` | scanner state + last rows | process state + `system_logs` + `signals` | read-only | high | already close to existing local observer API shape |
| `GET /signals` | `signals` table | PostgreSQL | read-only | high | latest 50 by default |
| `GET /stats` | aggregate query over `signals` | PostgreSQL | read-only | high | derive WR and PF from outcomes |
| `GET /cell-performance` | grouped query over `signals` by regime + score_bucket | PostgreSQL | read-only | medium | requires score_bucket persisted or derived |
| `GET /review-bundle` | artifact builder from signals/logs/config snapshot | PostgreSQL + config snapshot | read-only | medium | bundle for examiner review |
| `POST /kill` | scanner process control | PM2 or process-level control | control | high | already part of local observer concept |
| `GET /stream` | none yet | none | deferred | deferred | do not implement until reviewed |

## Notes
- No execution routes are in current scope.
- No portfolio domain exists in current scope.

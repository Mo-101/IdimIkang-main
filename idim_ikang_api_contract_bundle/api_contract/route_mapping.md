# Route Mapping — trading-sigma-main → Idim Ikang

| Old route | Idim Ikang route | Decision | Reason | Real backend source |
|---|---|---|---|---|
| `POST /generate-signal` | none (replace conceptually with `GET /signals`, `GET /status`) | discard | Idim Ikang does not expose external signal generation as a public trigger | Scanner loop + `signals` table |
| `GET /historical-data` | `GET /review-bundle` | rewrite | Historical evidence exists as observer artifacts, not generic market-history fetch | Review artifact generator / PostgreSQL |
| `GET /portfolio-insights` | `GET /stats`, `GET /cell-performance` | rewrite | No portfolio domain in observer scope; replace with observer analytics | PostgreSQL aggregate queries |
| `POST /optimize-strategy` | none | discard | Strategy tuning is internal research, not live observer API | Deferred internal tooling |

## Notes
- Old routes were generated stubs and are not treated as authoritative product truth.
- New routes map only to doctrine-approved observer, analytics, review, and kill-switch capabilities.

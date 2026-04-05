# Frontend Contract Notes

The dashboard can safely consume:

- `GET /status`
- `GET /signals`
- `GET /stats`
- `GET /cell-performance`

`GET /review-bundle` is suitable for examiner/admin surfaces, not necessarily the default dashboard.

Do not build UI flows that imply:
- trading execution
- portfolio management
- strategy optimization
- live stream support unless `/stream` is explicitly implemented later

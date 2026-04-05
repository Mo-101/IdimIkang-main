# Extraction Manifest

## Source
Extracted from `trading-sigma-main.zip`, specifically:
- `sigma/api/openapi.yaml`
- generated Node backend stubs
- default Vite React frontend scaffold

## What was extracted
The old API shape contained four routes:
- `POST /generate-signal`
- `GET /historical-data`
- `GET /portfolio-insights`
- `POST /optimize-strategy`

## How it was repurposed
The old contract structure was used only as a route skeleton. Each route was tested against Idim Ikang doctrine:

- external generation trigger → removed
- generic market-history fetch → rewritten as observer review bundle
- portfolio routes → removed, replaced by observer analytics
- optimization route → deferred, not public

## Result
A truthful observer API contract that reflects:
- live scanner status
- signal review
- aggregate stats
- cell performance
- kill-switch control

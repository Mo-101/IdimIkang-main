# Canonical Errors

## 400 Bad Request
Malformed query params, invalid limit, invalid date range.

## 404 Not Found
Requested signal or review artifact not found.

## 409 Conflict
Conflicting request state, such as duplicate control request in progress.

## 423 Kill Switch Active
Observer is intentionally halted. No scanner actions should proceed.

## 500 Internal Server Error
Unexpected backend failure.

## 501 Not Implemented
Deferred route exists in contract but is not implemented.

## 503 Observer Disabled
Observer subsystem unavailable or intentionally disabled at process level.

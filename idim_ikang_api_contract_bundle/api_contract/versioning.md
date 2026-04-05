# Versioning

## API version
- OpenAPI contract version: `1.0.0`

## Runtime versions to expose
Every route that returns observer data should expose:
- `logic_version`
- `config_version`

## Backward compatibility
- additive fields may be added in minor updates
- route removals require a major version bump
- deferred routes must remain explicitly marked as not implemented

## Policy
Contract truthfulness is more important than broad compatibility.

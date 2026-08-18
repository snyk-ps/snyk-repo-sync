## Why

After a successful Snyk import, the worker resolves `snykTargetId` via `GET /rest/orgs/{org_id}/targets`. The Snyk Targets API defaults `exclude_empty=true`, which omits targets with no projects. Empty repositories (valid after import) therefore never appear in lookup results, causing repeated `target_resolve_failed` warnings, import_poll retries, and eventual dead-letter (`ImportJobFailed`) even when the target exists in the Snyk UI.

Validated in production and Postman: adding `exclude_empty=false` returns the missing target.

## What Changes

- Pass `exclude_empty=false` on REST Targets list requests used for target id resolution (`SnykClient.find_target_id`).
- Add unit tests asserting the query includes `exclude_empty=false` and that empty-target records are matchable.
- Optional brief troubleshooting note in CONFIGURATION.md.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `snyk-target-sync`: REST target lookup MUST include empty targets (no projects) when resolving target ids after import and before removal.

## Impact

- **Code:** `src/snyk/client.py`, `tests/snyk/test_snyk_client.py`.
- **Docs:** optional note in CONFIGURATION.md troubleshooting.
- **Dependencies:** none.
- **Breaking:** none — fixes lookup for empty targets; non-empty targets unchanged.

## Non-goals

- Operator config for `exclude_empty` (always `false` for this worker's lookup use case).
- Changing deactivate/delete behavior for empty targets beyond successful id resolution.
- Broader Snyk API client refactor.

## Why

Slice 3 normalizes ADO lifecycle events and completes messages without resolving scope-to-Snyk mappings. Operators need a declarative mapping in `config.yaml` (ADO project name / GitHub org login → Snyk org id) before any Snyk API work can land.

The `scope-mapping` capability spec already defines the contract; this change implements the **config and resolution** half only. Snyk integration lookup and import/deactivate actions remain in the next change.

## What Changes

- Extend operator config with a `scopeMapping` section: ADO project entries, GitHub org entries, optional `defaultSnykOrgId`.
- Extend the config loader to parse and validate scope mappings at startup (duplicate keys fail fast).
- Add a scope-mapping resolver: given `source` + scope lookup key (`ado.projectName` or GitHub org login), return `snykOrgId`, or apply `defaultSnykOrgId` when configured.
- Wire ADO normalization path: after normalize, resolve mapping, log outcome (mapped / default / unmapped), complete message — no repository state access, no Snyk API calls.
- GitHub queue messages remain completed without normalization (unchanged from slice 3); GitHub mapping entries are loaded and resolver-ready for when GitHub normalization lands.
- Update `data/config.yaml.example`, **README.md**, **CONFIGURATION.md**, and cross-references in **CONTRIBUTING.md** / **INGESTION.md** where they still say mapping is deferred.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `scope-mapping`: Implement config-based scope → Snyk org resolution and unmapped-scope logging; keep Snyk API integration lookup deferred to the next change.
- `sync-worker`: Replace slice-3 “normalize → complete” with slice-4 “normalize → resolve scope mapping → log → complete” for ADO; no Snyk or sync-state side effects.

## Impact

- **Code:** `src/config/settings.py` (or new `src/config/scope_mapping.py`); `src/worker/handler.py` and/or consumer wiring; unit tests under `tests/config/` and `tests/worker/`.
- **Dependencies:** None expected (stdlib + existing `pyyaml`).
- **Docs:** README, CONFIGURATION, config example; remove “mapping deferred” language where implemented.
- **Breaking:** None for existing deployments — `scopeMapping` is optional; configs without it behave as today (all scopes unmapped, logged, completed).

## Non-goals

- Snyk API client, integration id lookup, import/deactivate/tagging.
- Repository row reads/writes, idempotency enforcement.
- GitHub lifecycle normalization.
- DLQ for unmapped scopes (log and complete per `scope-mapping` spec).
- Env-var overrides for individual scope entries (config file only for mappings in v1).

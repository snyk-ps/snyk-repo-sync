## Why

Slice 2 normalizes ADO lifecycle events and completes messages without touching sync state. Before Snyk actions or idempotency checks can land, the worker needs Azure Table Storage for per-repository state, plus a consistent identity-first connection model for both Table Storage and Service Bus.

Scope-to-Snyk mapping will move to operator config and the Snyk API (`scope-mapping` capability — next change). Table Storage `_meta` rows are no longer used.

Operators should not pre-create the sync-state table unless they want a custom name. Service Bus queues remain pre-provisioned outside this application. Authentication MUST use `DefaultAzureCredential` and RBAC — not connection strings or shared access keys.

## What Changes

- **BREAKING:** Remove Service Bus connection string env vars; authenticate with `DefaultAzureCredential` and RBAC.
- Add unified operator config (`serviceBus` + `syncState`) loaded from `--config` (default `data/config.yaml`); production mounts `/config/config.yaml` via Azure Files.
- Settings MAY be overridden by environment variables; env values take precedence over config file values.
- Add Azure Table Storage client: `create_table_if_not_exists` on startup (repository rows written in a follow-up change).
- Service Bus client: connect to pre-provisioned queue only (no queue/namespace provisioning).
- Replace slice-2 “complete without sync state access” with slice-3 “normalize → complete” (no scope mapping or repository state access yet).
- Add `scope-mapping` capability spec (implementation deferred to next change).
- Update Dockerfile: `ENTRYPOINT ["python", "src/main.py"]`, `CMD ["worker", "run", "--config", "/config/config.yaml"]`.
- Rewrite operator docs (README, CONFIGURATION, INGESTION, CONTRIBUTING) around managed identity, RBAC, config mount, and repository-only table schema; remove all connection-string and `_meta` references.

## Capabilities

### New Capabilities

- `scope-mapping`: Config-based ADO project name / GitHub org name → Snyk org mapping; integration lookup via Snyk API (spec only — implementation deferred).

### Modified Capabilities

- `sync-state`: RBAC auth via `DefaultAzureCredential`; config/env settings; table auto-provisioning; repository-only schema (no `_meta` rows).
- `sync-worker`: `--config` flag; unified startup; slice-3 ADO normalization + table ensure; remove connection-string startup and `_meta` lookup.
- `event-ingestion`: Queue reference via operator config/env; RBAC auth; explicit no queue provisioning and no connection strings.

## Impact

- **Code:** Replace `src/config/service_bus.py` env loader with unified config loader; add `src/sync_state/`; refactor `WorkerConsumer` and worker CLI/handler; remove `_meta` lookup.
- **Dependencies:** `azure-identity`, `azure-data-tables`, `pyyaml` (Snyk Open Source scan before merge).
- **Infra:** Container App managed identity with **Azure Service Bus Data Owner** and **Storage Table Data Contributor** RBAC assignments.
- **Docker:** New ENTRYPOINT/CMD with `--config /config/config.yaml`.
- **Docs:** CONFIGURATION.md repository table schema and RBAC checklist; remove `SERVICEBUS_CONNECTION_STRING` and `_meta` onboarding from all docs.
- **Out of scope:** Snyk import/deactivate/tagging, repository row upserts, idempotency enforcement, ignore-list persistence, GitHub normalization, scope-mapping implementation, Service Bus queue provisioning.

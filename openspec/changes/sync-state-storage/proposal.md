## Why

Slice 2 normalizes ADO lifecycle events and completes messages without touching sync state. Before Snyk actions or idempotency checks can land, the worker needs Azure Table Storage for scope `_meta` and per-repository state, plus a consistent identity-first connection model for both Table Storage and Service Bus.

Operators should not pre-create the sync-state table unless they want a custom name. Service Bus queues remain pre-provisioned outside this application. Authentication MUST use `DefaultAzureCredential` and RBAC — not connection strings or shared access keys.

## What Changes

- **BREAKING:** Remove Service Bus connection string env vars; authenticate with `DefaultAzureCredential` and RBAC.
- Add unified operator config (`serviceBus` + `syncState`) loaded from `--config` (default `data/config.yaml`); production mounts `/config/config.yaml` via Azure Files.
- Settings MAY be overridden by environment variables; env values take precedence over config file values.
- Add Azure Table Storage client: `create_table_if_not_exists` on startup; read `_meta` after ADO normalization.
- Service Bus client: connect to pre-provisioned queue only (no queue/namespace provisioning).
- After ADO normalization, load `_meta`; dead-letter with reason `UnknownScope` and alert when missing or `enabled: false`.
- Replace slice-2 “complete without sync state access” with slice-3 “normalize → load _meta → complete or DLQ”.
- Update Dockerfile: `ENTRYPOINT ["python", "src/main.py"]`, `CMD ["worker", "run", "--config", "/config/config.yaml"]`.
- Rewrite operator docs (README, CONFIGURATION, INGESTION, CONTRIBUTING) around managed identity, RBAC, config mount, and table schema; remove all connection-string references.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-state`: RBAC auth via `DefaultAzureCredential`; config/env settings; table auto-provisioning; entity property types.
- `sync-worker`: `--config` flag; unified startup; slice-3 `_meta` lookup; unknown/disabled scope DLQ + alert; remove connection-string startup.
- `event-ingestion`: Queue reference via operator config/env; RBAC auth; explicit no queue provisioning and no connection strings.

## Impact

- **Code:** Replace `src/config/service_bus.py` env loader with unified config loader; add `src/sync_state/`; refactor `WorkerConsumer` and worker CLI/handler.
- **Dependencies:** `azure-identity`, `azure-data-tables`, `pyyaml` (Snyk Open Source scan before merge).
- **Infra:** Container App managed identity with **Azure Service Bus Data Owner** and **Storage Table Data Contributor** RBAC assignments.
- **Docker:** New ENTRYPOINT/CMD with `--config /config/config.yaml`.
- **Docs:** CONFIGURATION.md table schema and RBAC checklist; remove `SERVICEBUS_CONNECTION_STRING` from all docs and examples.
- **Out of scope:** Snyk import/deactivate/tagging, repository row upserts, idempotency enforcement, ignore-list persistence, GitHub normalization, `_meta` onboarding tooling, Service Bus queue provisioning.

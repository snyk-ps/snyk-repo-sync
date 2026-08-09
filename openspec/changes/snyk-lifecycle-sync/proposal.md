## Why

Slice 4 resolves ADO project → Snyk org from operator config and completes messages without Snyk or sync-state side effects. Operators need the worker to perform repository lifecycle sync: async Snyk import with job polling, configurable target removal (deactivate or delete), idempotent state updates, and resilient retries. Canonical specs describe these outcomes but defer implementation.

## What Changes

- Add a Snyk REST client (`SNYK_TOKEN` from env): integration lookup, import trigger + job status, target deactivate/delete.
- Implement ADO lifecycle sync for mapped scopes: `repo.created`, `repo.renamed`, `repo.deleted`, `repo.default_branch_changed`.
- Extend repository sync-state with `importJobId` and `importStatus` (`pending` | `failed` | `complete`); retain `importJobId` after successful import for audit.
- Treat a repository as **not synced** until `importStatus` is `complete` and `snykTargetId` is set; `tagApplied` remains `false` (project tagging deferred).
- On import initiation or in-progress job: upsert pending state, **complete** the Service Bus message, and **schedule** a follow-up internal message on the **same queue** with exponential backoff (`retryCount` max 5, then DLQ).
- Add operator config: optional `snykIntegrationId` per scope entry; `snyk.targetRemoval` for rename, default branch change, and repo delete (`deactivate` | `delete`, default `deactivate`); `snyk.maxConcurrentPendingImports` (default `100` per worker).
- Replace slice-4 “resolve scope → complete” with full ADO lifecycle processing (minus project tagging).
- Document per-event behavior in spec scenarios.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `snyk-target-sync`: Snyk client, async import job contract, configurable target removal, failure logging; project tagging deferred to follow-up change.
- `scope-mapping`: Optional `snykIntegrationId` in config; implement integration id resolution via Snyk API with process-local cache fallback.
- `sync-state`: Add `importJobId`, `importStatus`; clarify when `snykTargetId` is written; retain job id after success.
- `repo-lifecycle`: Step-by-step sync behavior per event type including import deferral and removal mode; tagging deferred.
- `sync-worker`: Replace slice-4 stub; idempotency, state reads/writes, internal follow-up envelopes, retry/DLQ, pending import concurrency limit.
- `observability`: Structured logs for import pending/failed/complete, limit backpressure, and DLQ after max import retries.

## Impact

- **Code:** `src/snyk/` (new), lifecycle sync module, extend `src/sync_state/`, refactor `src/worker/handler.py` and `consumer.py`, integration resolver, config loader extensions.
- **Dependencies:** HTTP client for Snyk REST (stdlib preferred; Snyk Open Source scan before merge).
- **Config/docs:** `SNYK_TOKEN`, `snyk.*` and optional `snykIntegrationId`, CONFIGURATION.md state schema and lifecycle behavior table.
- **Breaking:** Worker behavior changes for mapped ADO events — messages no longer complete immediately after scope resolution.

## Non-goals

- Project tagging via Projects API (`snyk-project-tagging` follow-up change).
- GitHub lifecycle normalization.
- Ignore-list enforcement and scheduled deactivation job.
- Cross-worker integration id cache (Table Storage / Redis).
- Service Bus queue provisioning changes.

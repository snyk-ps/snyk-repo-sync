## Context

Slice 4 flow: parse → normalize ADO → resolve scope mapping → log → complete. No Snyk client, no repository state reads/writes. Canonical specs in `snyk-target-sync`, `repo-lifecycle`, and `sync-worker` describe import polling, lifecycle actions, and retries but leave them unimplemented.

## Goals / Non-Goals

**Goals:**

- Snyk REST client for integration lookup, import, job status, target deactivate/delete.
- ADO lifecycle sync with async import job deferral via same-queue internal messages.
- Sync-state updates with `importJobId`, `importStatus`; retain job id after success.
- Configurable target removal mode and pending-import concurrency limit.
- Idempotency, structured failure logging, max 5 import poll retries → DLQ.

**Non-Goals:**

- Project tagging (`tagApplied=true`) — deferred to `snyk-project-tagging`.
- GitHub normalization and sync.
- Ignore-list policy and scheduled deactivation.
- Distributed integration id cache across workers.

## Decisions

### 1. Snyk client module

`src/snyk/client.py` — thin REST wrapper authenticated with `SNYK_TOKEN` (env var; never logged):

| Operation | Snyk API | Used for |
| --------- | -------- | -------- |
| List integrations | Org integrations | Resolve ADO/GitHub integration id |
| Start import | Import API | Create/re-import target |
| Get import job | Import job status | Poll pending jobs |
| Deactivate projects | v1 Projects API | Removal mode `deactivate` (all projects under target) |
| Delete target | REST Targets API | Removal mode `delete` |
| Find target | REST Targets API | Resolve `snykTargetId` after import and before removal |
| List projects | REST Projects API | Enumerate projects for deactivation |

Rate limits (429): exponential backoff; counts toward retry budget where applicable.

### 2. Import is async — synced means job complete (no tagging in this slice)

A repository is synced when `importStatus=complete` and `snykTargetId` is set. `tagApplied` remains `false` until the tagging follow-up change.

| Phase | `importJobId` | `importStatus` | `snykTargetId` | Worker action |
| ----- | ------------- | -------------- | -------------- | ------------- |
| Import triggered | set | `pending` | empty | Schedule `import_poll` follow-up |
| Job running | unchanged | `pending` | unchanged | Reschedule follow-up |
| Job succeeded | **retained** | `complete` | set via REST lookup | Complete work; no Projects API tagging |
| Job failed | set | `failed` | unchanged | Retry or DLQ at max retries |

Repository row MUST be upserted when import is initiated (`pending`), not only on success.

### 3. Deferred processing via internal envelope on same queue

Do not block the receive loop polling Snyk for long periods.

1. Process lifecycle event → trigger import or poll existing job from state.
2. If job not complete: upsert state, **complete** current message.
3. **Schedule** follow-up on the same pre-provisioned queue.

**Internal envelope** (distinct from ADO Event Grid / GitHub webhook JSON):

```json
{
  "syncPhase": "import_poll",
  "source": "ado",
  "scopeId": "...",
  "repositoryId": "...",
  "sourceEventId": "...",
  "importJobId": "...",
  "importStatus": "pending",
  "retryCount": 0,
  "occurredAt": "2026-08-09T15:00:00Z"
}
```

Parser routes on top-level `syncPhase`:

| `syncPhase` | Handler |
| ----------- | ------- |
| `import_poll` | Poll import job; finalize state or reschedule |
| `lifecycle_deferred` | Retry lifecycle work when pending-import limit reached |
| absent | Provider parse + normalize + lifecycle |

**Backoff:** `delay = min(base * 2^retryCount, maxDelay)` (e.g. base 30s, max 15m). Increment `retryCount` each schedule. At `retryCount >= 5` → DLQ reason `ImportJobFailed`, alert per `observability`.

**Alternative rejected:** Inline poll until complete — risks message lock expiry and poor throughput.

### 4. Integration id resolution

- Optional `snykIntegrationId` on each scope mapping entry under integration type sections (`azure-repos`, `github-*`) — shared across workers via mounted config.
- When omitted: resolve via Snyk API; cache `(snykOrgId, integrationType) → integrationId` in **process memory** for worker lifetime only.
- On 404/invalid configured id: log, refresh via API once, update in-memory cache.
- Integration ids MUST NOT be persisted in sync-state Table Storage.

### 5. Configurable target removal

```yaml
snyk:
  maxConcurrentPendingImports: 100
  targetRemoval:
    onRename: deactivate
    onDefaultBranchChange: deactivate
    onRepoDelete: deactivate
```

Values: `deactivate` | `delete`. Default `deactivate` when section or key omitted. Invalid values → startup failure.

| Event | `deactivate` | `delete` |
| ----- | ------------ | -------- |
| Rename | Resolve old target → deactivate all projects → import new | Resolve old target → REST delete → import new |
| Default branch change | Resolve old target → deactivate all projects → re-import | Resolve old target → REST delete → re-import |
| Repo deleted | Resolve target → deactivate all projects | Resolve target → REST delete; clear `snykTargetId` |

Import job responses do not reliably include target ids. The worker resolves targets via REST (`GET /rest/orgs/{org_id}/targets`) using ADO project name, repository name, and branch. Re-import flows MUST succeed at removal before starting import.

Issue ignores are not migrated on rename/branch change regardless of mode. Delete is irreversible — document in CONFIGURATION.md.

### 6. Pending import concurrency limit

- Configurable via `snyk.maxConcurrentPendingImports`; default **100 per worker process**.
- Count repository rows with `importStatus=pending` (sync-state as source of truth).
- Effective cluster limit ≈ `replicas × maxConcurrentPendingImports`.
- When at limit: log warning, complete message, schedule `lifecycle_deferred` with backoff — do **not** DLQ for limit alone.

### 7. Per lifecycle event behavior (ADO)

| Event | Behavior |
| ----- | -------- |
| **repo.created** | Resolve import branch (event or ADO REST) → import → poll → state `complete` + `snykTargetId`; skip if ignored (future) / unmapped / duplicate event |
| **repo.renamed** | Resolve old target id → remove per config (must succeed) → resolve import branch → import new name → poll until target id resolved |
| **repo.default_branch_changed** | No action if `previousDefaultBranch` absent; else resolve old target → remove → import on new default branch → poll |
| **repo.deleted** | Resolve target id → remove per config; `status=inactive`; DLQ if removal fails |

**Import branch resolution:** Snyk Import API requires `target.branch`. Use `payload.defaultBranch` when present; otherwise call ADO Git REST API with `ADO_PAT` and configured `ado.organization`. Never infer a hardcoded branch such as `main`. Sync-state `defaultBranch` MUST match the branch sent in the import payload.

**repo.created while import pending:** Do not start second import; poll existing job.

**repo.deleted while import pending:** Stop poll path; remove target if known; mark inactive.

### 8. Idempotency (v1)

- Skip when `lastEventId == eventId`.
- Skip when `desiredStateHash` matches intended outcome.
- Skip duplicate import when `importStatus=pending` for same repository.

## Risks / Trade-offs

| Risk | Mitigation |
| ---- | ---------- |
| Follow-up messages mis-routed | Require `syncPhase` on internal envelopes; unit tests for parser |
| Concurrent deliveries start duplicate imports | State-level pending job + idempotency checks |
| Many replicas × 100 pending imports hit Snyk limits | Document lowering cap or reducing replicas |
| Stale configured integration id | API refresh on 404 |
| Tagging deferred leaves `tagApplied=false` | Follow-up `snyk-project-tagging` change backfills |

## Migration Plan

1. Deploy worker with `SNYK_TOKEN` and optional `scopeMapping` + `snyk` config.
2. Existing empty sync-state table — no migration.
3. Messages in flight during deploy may complete without sync once; subsequent events reconcile.

## Open Questions

_None — resolved during proposal review._

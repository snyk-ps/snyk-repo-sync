## Context

Transport messages use the envelope from `event-ingestion` (`source`, `ingressId`, `receivedAt`, `rawPayload`). For ADO, `rawPayload` is an audit record delivered via Event Grid (`eventType: AzureDevOpsAuditEvent`); the ingress handler strips the Event Grid wrapper and publishes the audit object.

Slice 1 validates envelopes and completes messages without normalization. Real audit payloads confirm org scope fields (`ScopeId`, `ScopeDisplayName`), project fields (`ProjectId`, `ProjectName`), repository fields (`Data.RepoId`, `Data.RepoName`), and branch refs (`Data.DefaultBranch`, `Data.PreviousDefaultBranch`) on default-branch-changed events.

Canonical specs reference normalization in `sync-worker` but leave payload shapes vague. Sync state partitions by `ado:{projectId}` where `projectId` is the ADO project GUID; Snyk mapping is project-scoped (1:1 project → Snyk org via `_meta`).

## Goals / Non-Goals

**Goals:**

- Provider-neutral normalized lifecycle event model shared by ADO and (future) GitHub.
- Explicit capture of ADO org, project, repository, and branch fields needed for downstream Snyk mapping and ADO REST enrichment.
- ADO audit `ActionId` → `eventType` mapping for all four lifecycle actions.
- Normalization as a separate layer between envelope parsing and lifecycle/sync logic.
- Unit tests with fixtures for each ADO action.

**Non-Goals:**

- GitHub webhook normalization implementation (structure only; pass-through in slice 2).
- Sync state reads/writes, Snyk import/deactivate, ignore policy, unknown-scope DLQ alerts.
- Changing the transport envelope or ingress contracts.
- Deriving or requiring ADO org URL slug (optional best-effort parse from `ScopeDisplayName` only if needed later).

## Normalized event model

All supported lifecycle events normalize to:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `source` | `"ado"` \| `"github"` | From transport envelope |
| `eventId` | string | Stable provider event id (`rawPayload.Id` for ADO) |
| `eventType` | enum | `repo.created`, `repo.renamed`, `repo.deleted`, `repo.default_branch_changed` |
| `scopeId` | string | ADO `ProjectId` (sync-state partition key); GitHub org id (future) |
| `repositoryId` | string | ADO `Data.RepoId`; GitHub repo id as string (future) |
| `occurredAt` | datetime UTC | ADO `Timestamp`; GitHub webhook timestamp (future) |
| `ado` | object | Present when `source: "ado"` — org and project context |
| `repository` | object | `name` — repository display name |
| `payload` | object | Event-specific fields (branch, previous name, etc.) |

### ADO scope object (`ado`)

| Field | ADO audit source | Notes |
| ----- | ---------------- | ----- |
| `orgId` | `ScopeId` | Organization GUID |
| `orgDisplayName` | `ScopeDisplayName` | e.g. `torstencannell (Organization)` |
| `projectId` | `ProjectId` | MUST equal top-level `scopeId` |
| `projectName` | `ProjectName` | Prefer top-level; ignore duplicate in `Data.ProjectName` |

### Repository object

| Field | ADO audit source |
| ----- | ---------------- |
| `name` | `Data.RepoName` |

Use `Data.RepoName` as-is (may include `.git` suffix); do not strip in normalization.

### Payload by `eventType`

| `eventType` | Required `payload` fields |
| ----------- | ------------------------- |
| `repo.created` | none required; `defaultBranch` optional if `Data.DefaultBranch` present |
| `repo.renamed` | `previousRepoName` ← `Data.PreviousRepoName` |
| `repo.deleted` | none |
| `repo.default_branch_changed` | `defaultBranch`, `previousDefaultBranch` |

Branch values MUST have the `refs/heads/` prefix stripped.

### Example (from real audit export)

Audit `ActionId: Git.RepositoryDefaultBranchChanged` normalizes to:

```json
{
  "source": "ado",
  "eventId": "acf86b70-4ec3-4052-9e0b-fbcdd5109c1f",
  "eventType": "repo.default_branch_changed",
  "occurredAt": "2026-08-06T17:31:52.3273845Z",
  "scopeId": "da9734d4-a91a-4f03-814b-ecc721fe24d1",
  "repositoryId": "90bd6b5e-0fbd-4edc-a10e-6604fe76027d",
  "ado": {
    "orgId": "c638432a-7f35-450f-984f-372b9d46a376",
    "orgDisplayName": "torstencannell (Organization)",
    "projectId": "da9734d4-a91a-4f03-814b-ecc721fe24d1",
    "projectName": "snykDemoProject"
  },
  "repository": {
    "name": "juice-shop.git"
  },
  "payload": {
    "defaultBranch": "master",
    "previousDefaultBranch": "develop"
  }
}
```

## ADO audit mapping

| Audit `ActionId` | `eventType` | Required audit/`Data` fields |
| ---------------- | ----------- | ----------------------------- |
| `Git.RepositoryCreated` | `repo.created` | `ScopeId`, `ProjectId`, `ProjectName`, `Data.RepoId`, `Data.RepoName` |
| `Git.RepositoryRenamed` | `repo.renamed` | above + `Data.PreviousRepoName` |
| `Git.RepositoryDeleted` | `repo.deleted` | `ScopeId`, `ProjectId`, `ProjectName`, `Data.RepoId`, `Data.RepoName` |
| `Git.RepositoryDefaultBranchChanged` | `repo.default_branch_changed` | above + `Data.DefaultBranch`, `Data.PreviousDefaultBranch` |

Unsupported ADO `ActionId` or missing required fields → `NormalizationError` → dead-letter reason `InvalidNormalization`.

## Decisions

### 1. Keep `scopeId` as ADO project ID

**Decision:** `scopeId` = `ProjectId`, not `ScopeId` (org).

**Rationale:** Matches sync-state partition `ado:{projectId}` and existing worker spec; Snyk mapping is project-scoped via `_meta`. Org context lives in `ado.orgId` / `ado.orgDisplayName`.

**Alternatives considered:**
- Org as `scopeId` — rejected; breaks sync-state and snyk-target-sync contracts.

### 2. Nested `ado` object for provider-specific scope

**Decision:** Top-level fields stay provider-neutral; ADO org/project live under `ado`.

**Rationale:** GitHub follow-up can add `github: { orgId, orgLogin, ... }` without reshaping the model.

### 3. Normalization module separate from envelope parsing

**Decision:** `src/worker/normalize.py` with `normalize_ado_lifecycle_event(envelope) -> NormalizedEvent`.

**Rationale:** Matches slice-1 layering; GitHub mapper adds a branch without changing envelope or consumer code.

### 4. Slice-2 handler: normalize ADO, pass-through GitHub

**Decision:** After envelope validation, if `source == "ado"`, normalize and log structured fields; if `source == "github"`, log deferred normalization and complete without side effects.

**Rationale:** Settles structure on ADO first; GitHub messages keep flowing without blocking the queue.

### 5. Remove slice-1 “complete without normalization”

**Decision:** Replace with slice-2 ADO normalization requirement in spec delta.

**Rationale:** ADO normalization is the purpose of this change.

## Risks / Trade-offs

| Risk | Mitigation |
| ---- | ---------- |
| Rename/create/delete audit `Data` shapes differ from default-branch example | Fixtures + tests per `ActionId`; dead-letter on missing required fields |
| `Data.PreviousRepoName` absent on some rename audits | Require field; validate with real rename export during implementation |
| `ScopeDisplayName` is not an ADO URL slug | Store as `orgDisplayName`; derive slug later only if REST enrichment needs it |
| GitHub messages complete without normalization temporarily | Explicit log + follow-up change; spec retains GitHub scenarios |

## Migration Plan

1. Deploy worker with slice-2 normalization (ADO only).
2. Update ADO transport fixture with org scope fields.
3. Verify integration tests still complete ADO fixtures end-to-end.
4. GitHub normalization lands in a follow-up change without changing the normalized model.

## Open Questions

- Confirm `Data.RepoId` and `Data.PreviousRepoName` on real create/rename/delete audit exports (default-branch change confirmed).
- Whether `repo.created` should treat `Data.DefaultBranch` as optional (recommend yes).

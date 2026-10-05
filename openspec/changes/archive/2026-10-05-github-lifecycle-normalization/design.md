## Context

Queue messages for GitHub are JSON with top-level `repository` and `action`. Two shapes are in production:

1. **Raw webhook** — snake_case fields per [GitHub webhook payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads#repository).
2. **Parsed contract** — GitHubHooks output for topic `ENVLOG_GitHub_Repository_Event`: top-level `deliveryId` (GUID), camelCase `repository` (GET-repository-shaped), optional `changes`, and `sender`.

ADO normalization and lifecycle sync are implemented. `NormalizedEvent` requires `ado: AdoScope`; lifecycle, ignore policy, and target lookup use `event.ado.project_name`. The handler short-circuits GitHub with a deferred-normalization log.

Scope mapping and ignore policy already key GitHub by **org login**. Sync-state spec text references numeric org id for GitHub partitions; parsed contract and GET-repository shape expose **owner login** only for scope.

## Goals / Non-Goals

**Goals:**

- Provider-neutral normalized lifecycle events for GitHub with optional `ado` / `github` scope objects.
- Dual-shape adapters → canonical input → single `normalize_github_repository_event()`.
- Full lifecycle for mapped GitHub orgs (create, rename, delete, default branch change).
- Integration-scoped Snyk target lookup and import (`source_types` from mapped GitHub integration).
- Stable `eventId` from parsed `deliveryId`; raw webhook may use Service Bus application property when available.

**Non-goals:**

- Kafka client or GitHubHooks deployment in this repository.
- Parsing previous rename from `repository.description`.
- GitHub API enrichment when fields are missing.
- Project tagging via Projects API.

## Decisions

### 1. Shape detection

**Decision:** If top-level `deliveryId` is a non-empty string, treat as **parsed contract**; otherwise **raw webhook** (still requires `repository` + `action`).

**Rationale:** Matches GitHubHooks contract; avoids mis-detecting on camelCase alone.

### 2. GitHub `scopeId` = org login

**Decision:** `scopeId` and `github.orgLogin` = `repository.owner.login` when `owner.type` is `Organization`. Partition key `github:{scopeId}` uses that login string.

**Alternatives:** Numeric `organization.id` (raw webhooks only) — rejected for parity with parsed contract and scope mapping.

### 3. Nested `github` scope; optional `ado`

**Decision:** `NormalizedEvent` has `ado: AdoScope | None` and `github: GitHubScope | None` with invariant exactly one set matching `source`. Expose `scope_lookup_key(event)` and `owner_name(event)` for lifecycle.

### 4. Parsed contract field mapping

| Action | `eventType` | Notes |
|--------|-------------|--------|
| `created` | `repo.created` | optional `payload.defaultBranch` ← `repository.defaultBranch` |
| `renamed` | `repo.renamed` | `payload.previousRepoName` ← `changes.repository.name.from` when present |
| `deleted` | `repo.deleted` | — |
| `edited` | `repo.default_branch_changed` | **only if** `changes.default_branch.from` present; `previousDefaultBranch` ← `from`, `defaultBranch` ← `repository.defaultBranch` |
| `edited` | *(no lifecycle)* | description/homepage-only `changes` → complete without sync |

**Note:** In parsed contract, `changes.default_branch` uses **snake_case**; `repository` uses **camelCase**.

Raw webhook uses snake_case throughout; same semantic paths (`changes.repository.name.from`, `changes.default_branch.from`).

### 5. Default branch lifecycle without payload previous branch (GitHub)

**Decision:** For `source: github`, do not require `previousDefaultBranch` in normalized `payload` before loading sync state. Resolve old target via: (1) `state.snykTargetId`, (2) REST lookup with owner login + repo name + branch from `changes.default_branch.from` or `state.defaultBranch`, filtered by mapped GitHub `source_types`. Assume at most one relevant target per repo under that integration.

**Rationale:** Parsed contract may omit `to`; new branch is always on `repository.defaultBranch`. Avoids touching CLI/other SCM targets.

### 6. Rename without `changes.repository.name.from`

**Decision:** Fallback order: explicit `from` → `state.repoName` (same `repository.id`) → proceed with new-name import only, log `rename_previous_name_unknown`, do not remove old target via REST unless resolved.

### 7. Non-org repositories

**Decision:** If `owner.type != Organization`, complete message without normalization error and without Snyk side effects (info log).

### 8. Module layout

**Decision:** `normalize.py`: adapters `adapt_github_raw_webhook`, `adapt_github_parsed_contract`, canonical struct, `normalize_github_repository_event`. `message.py`: optional `event_id` from `deliveryId` or SB properties for raw.

## Risks / Trade-offs

| Risk | Mitigation |
| ---- | ---------- |
| Login-based partition if org renames login (rare) | Document; new login = new partition; operational migration out of scope |
| Rename without `from` and without state leaves orphan target | Log warning; customer contract documents `from`; state helps after first sync |
| `select_target_id` heuristics match wrong target | Filter `source_types`; prefer stored `snykTargetId` |
| Breaking test fixtures constructing `NormalizedEvent` | Update builders; optional ADO-only defaults in tests |
| `edited` storms for non-branch settings | Ignore unless `changes.default_branch.from` present |

## Migration Plan

1. Deploy worker with GitHub normalization + lifecycle (mapped orgs only).
2. No sync-state backfill required if no GitHub rows exist yet; if numeric org id rows exist in dev, document wipe or migration script out of scope.
3. Verify raw and parsed fixtures in CI.

## Open Questions

- Raw webhook `eventId` when `deliveryId` absent and SB application property not set: prefer requiring property from ingress vs synthetic id (implementation: use `deliveryId` from body when present; else SB user property `GitHubDelivery` if documented).
- Confirm production always sends `changes.repository.name.from` on rename when GitHubHooks omits it (fallbacks cover gap).

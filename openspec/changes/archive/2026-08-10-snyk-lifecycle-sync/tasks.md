## 1. Config and settings

- [x] 1.1 Add `SnykSettings` parser: `maxConcurrentPendingImports` (default 100), `targetRemoval` (`onRename`, `onDefaultBranchChange`, `onRepoDelete`; default `deactivate`)
- [x] 1.2 Extend scope mapping entries with optional `snykIntegrationId`; validate non-empty when present
- [x] 1.3 Require `SNYK_TOKEN` at worker startup; fail fast with clear error when missing
- [x] 1.4 Unit tests: default snyk settings, invalid removal mode, optional integration id

## 2. Snyk client

- [x] 2.1 Add `src/snyk/client.py`: list integrations, start import, get import job, REST target/project lookup, project deactivate, target delete
- [x] 2.4 Resolve Snyk target ids via REST Targets API; deactivate all projects under target; REST target delete; gated reimport on rename/branch change
- [x] 2.2 Implement process-local integration id cache with API refresh on invalid configured id
- [x] 2.3 Unit tests with mocked HTTP for each public client method and rate-limit backoff

## 3. Sync state

- [x] 3.1 Extend `RepositoryState` with `importJobId` and `importStatus`
- [x] 3.2 Implement `SyncStateStore` get/upsert and pending-import count query
- [x] 3.3 Unit tests: pending → complete/failed transitions; retain `importJobId` after success

## 4. Internal message envelope

- [x] 4.1 Define follow-up message schema (`syncPhase`: `import_poll`, `lifecycle_deferred`)
- [x] 4.2 Extend queue message parser to route internal envelopes vs provider payloads
- [x] 4.3 Implement schedule/send on same queue with exponential backoff and `retryCount`
- [x] 4.4 Unit tests: parser routing, backoff calculation, max 5 retries → DLQ reason `ImportJobFailed`

## 5. Lifecycle sync (ADO)

- [x] 5.1 Implement idempotency: `lastEventId`, `desiredStateHash`, pending job guard
- [x] 5.2 Handler: `repo.created` — trigger import, pending state, schedule poll
- [x] 5.3 Handler: `repo.renamed` — remove old per config, import, poll
- [x] 5.4 Handler: `repo.default_branch_changed` — skip without prior branch; else remove, re-import, poll
- [x] 5.5 Handler: `repo.deleted` — remove per config; handle pending import cancellation
- [x] 5.6 Handler: `import_poll` — poll job, finalize state (`tagApplied=false`), reschedule or DLQ
- [x] 5.7 Handler: `lifecycle_deferred` — retry when under pending import limit
- [x] 5.8 Unit tests per event type and edge cases (pending import, delete during pending, unmapped scope)
- [x] 5.9 Resolve required Snyk import branch from event payload or ADO Git REST API; unit tests for ADO client and import branch resolution

## 6. Worker wiring

- [x] 6.1 Replace slice-4 handler path with full sync pipeline for mapped ADO events
- [x] 6.2 Wire `consumer.py` settlement: complete lifecycle messages before scheduling follow-ups
- [x] 6.3 Structured logging per `observability` spec (import triggered, pending, complete, failed, limit reached, DLQ)
- [x] 6.4 Integration test: ADO create fixture → pending then complete state (mock or emulated Snyk)

## 7. Documentation

- [x] 7.1 Update `data/config.yaml.example` with `snyk` section and optional `snykIntegrationId`
- [x] 7.2 Update CONFIGURATION.md: state fields, SNYK_TOKEN, removal modes, lifecycle behavior table, cluster pending limit note
- [x] 7.3 Update README worker behavior description
- [x] 7.4 Document ADO PAT required scope (Code Read) and project/org access in CONFIGURATION.md

## 8. Archive prep

- [ ] 8.1 Merge `openspec/specs/` only when archiving: do **not** copy change deltas into canonical specs during implementation; run `openspec archive snyk-lifecycle-sync` when complete

## Explicitly deferred

- Project tagging via Projects API (`snyk-project-tagging` change)

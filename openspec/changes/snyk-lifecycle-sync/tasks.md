## 1. Config and settings

- [ ] 1.1 Add `SnykSettings` parser: `maxConcurrentPendingImports` (default 100), `targetRemoval` (`onRename`, `onDefaultBranchChange`, `onRepoDelete`; default `deactivate`)
- [ ] 1.2 Extend scope mapping entries with optional `snykIntegrationId`; validate non-empty when present
- [ ] 1.3 Require `SNYK_TOKEN` at worker startup; fail fast with clear error when missing
- [ ] 1.4 Unit tests: default snyk settings, invalid removal mode, optional integration id

## 2. Snyk client

- [ ] 2.1 Add `src/snyk/client.py`: list integrations, start import, get import job, deactivate target, delete target
- [ ] 2.2 Implement process-local integration id cache with API refresh on invalid configured id
- [ ] 2.3 Unit tests with mocked HTTP for each public client method and rate-limit backoff

## 3. Sync state

- [ ] 3.1 Extend `RepositoryState` with `importJobId` and `importStatus`
- [ ] 3.2 Implement `SyncStateStore` get/upsert and pending-import count query
- [ ] 3.3 Unit tests: pending → complete/failed transitions; retain `importJobId` after success

## 4. Internal message envelope

- [ ] 4.1 Define follow-up message schema (`syncPhase`: `import_poll`, `lifecycle_deferred`)
- [ ] 4.2 Extend queue message parser to route internal envelopes vs provider payloads
- [ ] 4.3 Implement schedule/send on same queue with exponential backoff and `retryCount`
- [ ] 4.4 Unit tests: parser routing, backoff calculation, max 5 retries → DLQ reason `ImportJobFailed`

## 5. Lifecycle sync (ADO)

- [ ] 5.1 Implement idempotency: `lastEventId`, `desiredStateHash`, pending job guard
- [ ] 5.2 Handler: `repo.created` — trigger import, pending state, schedule poll
- [ ] 5.3 Handler: `repo.renamed` — remove old per config, import, poll
- [ ] 5.4 Handler: `repo.default_branch_changed` — skip without prior branch; else remove, re-import, poll
- [ ] 5.5 Handler: `repo.deleted` — remove per config; handle pending import cancellation
- [ ] 5.6 Handler: `import_poll` — poll job, finalize state (`tagApplied=false`), reschedule or DLQ
- [ ] 5.7 Handler: `lifecycle_deferred` — retry when under pending import limit
- [ ] 5.8 Unit tests per event type and edge cases (pending import, delete during pending, unmapped scope)

## 6. Worker wiring

- [ ] 6.1 Replace slice-4 handler path with full sync pipeline for mapped ADO events
- [ ] 6.2 Wire `consumer.py` settlement: complete lifecycle messages before scheduling follow-ups
- [ ] 6.3 Structured logging per `observability` spec (import triggered, pending, complete, failed, limit reached, DLQ)
- [ ] 6.4 Integration test: ADO create fixture → pending then complete state (mock or emulated Snyk)

## 7. Documentation

- [ ] 7.1 Update `data/config.yaml.example` with `snyk` section and optional `snykIntegrationId`
- [ ] 7.2 Update CONFIGURATION.md: state fields, SNYK_TOKEN, removal modes, lifecycle behavior table, cluster pending limit note
- [ ] 7.3 Update README worker behavior description

## 8. Archive prep

- [ ] 8.1 Merge `openspec/specs/` only when archiving: do **not** copy change deltas into canonical specs during implementation; run `openspec archive snyk-lifecycle-sync` when complete

## Explicitly deferred

- Project tagging via Projects API (`snyk-project-tagging` change)

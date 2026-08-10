## RENAMED Requirements

- FROM: `### Requirement: Slice-4 ADO normalization with scope mapping`
- TO: `### Requirement: Slice-5 ADO lifecycle sync with import deferral`

## MODIFIED Requirements

### Requirement: Source-aware processing flow
For each normalized event, the worker MUST: resolve scope mapping per the `scope-mapping` capability; read repository state from sync state; perform idempotency check; execute the mapped lifecycle action; update repository state; complete, schedule follow-up, or dead-letter the message.

Unmapped scopes MUST log and complete without Snyk side effects per the `scope-mapping` capability.

#### Scenario: Successful ADO repo create
- **WHEN** a repo-created event with `source: "ado"` passes idempotency checks and scope mapping resolves a Snyk org
- **THEN** the worker triggers import, upserts pending repository state, schedules import job polling if needed, and completes or dead-letters the message per retry policy

#### Scenario: Successful ADO repo delete
- **WHEN** a repo-deleted event with `source: "ado"` passes idempotency checks and scope mapping resolves a Snyk org
- **THEN** the worker removes the target per configured removal mode, updates repository state, and completes the message

#### Scenario: Successful GitHub repo create
- **WHEN** a repo-created event with `source: "github"` passes idempotency checks and scope mapping resolves a Snyk org
- **THEN** the worker imports and updates repo state per lifecycle contract (when GitHub normalization is implemented)

### Requirement: Unrecoverable failure handling
On unrecoverable processing failure, the worker MUST dead-letter the message and emit an alert.

Import job polling MUST dead-letter with reason `ImportJobFailed` when `retryCount` reaches 5 on `import_poll` follow-up messages.

#### Scenario: Snyk import permanently fails
- **WHEN** import fails after retries/backoff with a non-transient error or max poll retries exceeded
- **THEN** the message is dead-lettered and an alert is raised

### Requirement: Import job polling with concurrency limits
When an import is initiated, the worker MUST NOT block the Service Bus receive loop until the job completes. The worker MUST schedule follow-up messages on the same queue with exponential backoff and MUST respect `snyk.maxConcurrentPendingImports` (default 100 per worker process).

Follow-up messages MUST carry `syncPhase`, `importJobId`, `importStatus`, and `retryCount`.

#### Scenario: Import in progress
- **WHEN** Snyk returns an in-progress import job
- **THEN** the worker upserts `importStatus=pending`, completes the current message, and schedules an `import_poll` follow-up with incremented backoff

#### Scenario: Import job completes
- **WHEN** an `import_poll` follow-up finds the import job succeeded
- **THEN** the worker updates repository state with `importStatus=complete`, retains `importJobId`, sets `snykTargetId`, and completes the follow-up message without project tagging

#### Scenario: Pending import limit reached
- **WHEN** the count of repository rows with `importStatus=pending` equals or exceeds `snyk.maxConcurrentPendingImports`
- **THEN** the worker logs a structured warning, completes the lifecycle message, and schedules a `lifecycle_deferred` follow-up with backoff rather than dead-lettering

### Requirement: Slice-5 ADO lifecycle sync with import deferral
After successful ADO lifecycle normalization and scope mapping resolution, the worker MUST execute repository lifecycle sync per the `repo-lifecycle` and `snyk-target-sync` capabilities for mapped scopes.

The worker MUST read and write repository sync state, call the Snyk API, and route internal follow-up messages on the same queue.

GitHub queue messages MUST be completed without normalization or sync side effects until GitHub normalization is implemented.

#### Scenario: Valid ADO message with mapped project and repo created
- **WHEN** the worker normalizes a repo-created ADO message whose scope mapping resolves
- **THEN** it triggers Snyk import and updates sync state without completing import inline in the receive handler

#### Scenario: Valid ADO message with unmapped project
- **WHEN** the worker normalizes an ADO lifecycle message whose scope has no mapping and no default org
- **THEN** it logs an unmapped-scope warning and completes the message without Snyk side effects

#### Scenario: Valid GitHub message in slice 5
- **WHEN** the worker parses a valid GitHub webhook queue message
- **THEN** it completes the message without normalization or sync side effects

## ADDED Requirements

### Requirement: Internal follow-up message routing
The worker MUST deserialize internal follow-up messages on the same Service Bus queue distinguished by top-level `syncPhase`. Supported values: `import_poll`, `lifecycle_deferred`.

Internal messages MUST NOT be parsed as ADO Event Grid or GitHub webhook payloads.

#### Scenario: Import poll follow-up received
- **WHEN** the worker receives a message with `syncPhase: import_poll`
- **THEN** it polls the referenced import job and reschedules, finalizes state, or dead-letters per retry policy

#### Scenario: Lifecycle deferred follow-up received
- **WHEN** the worker receives a message with `syncPhase: lifecycle_deferred`
- **THEN** it re-attempts the deferred lifecycle action when pending import count is below the configured limit

### Requirement: Slice-5 lifecycle sync without project tagging
In this implementation slice, after import job completion the worker MUST update repository state with `importStatus=complete` and `snykTargetId`. The worker MUST NOT call the Projects API or set `tagApplied=true`.

#### Scenario: Import completes in slice 5
- **WHEN** the import job succeeds
- **THEN** repository state is updated with `importStatus=complete`, `snykTargetId`, retained `importJobId`, and `tagApplied=false`

### Requirement: Operator Snyk settings in config
The worker MUST load optional `snyk` settings from operator config at startup: `maxConcurrentPendingImports` (default 100) and `targetRemoval` with keys `onRename`, `onDefaultBranchChange`, and `onRepoDelete` (each `deactivate` or `delete`, default `deactivate`).

Invalid removal mode values MUST cause startup failure.

The worker MUST require `SNYK_TOKEN` from the environment when Snyk sync is enabled for mapped ADO processing.

#### Scenario: Default Snyk settings
- **WHEN** `snyk` section is absent from config
- **THEN** the worker uses `maxConcurrentPendingImports=100` and deactivation for all removal actions

#### Scenario: Missing SNYK_TOKEN at startup
- **WHEN** the worker starts without `SNYK_TOKEN` set
- **THEN** it exits with a non-zero status and a clear error message

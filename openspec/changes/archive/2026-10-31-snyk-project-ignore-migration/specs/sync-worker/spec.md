## MODIFIED Requirements

### Requirement: Idempotency by event and desired state
The worker MUST skip duplicate processing when `lastEventId` matches the incoming `eventId` or when `desiredStateHash` already reflects the intended outcome.

A parsed GitHub updated body MUST NOT be treated as desired-state current when the repository row has a non-empty `snykOrgId` or `snykIntegrationType` and either value differs from the scope resolution for that event. A blank stored org id MUST be a backfill and MUST NOT by itself force a new import.

#### Scenario: Duplicate delivery
- **WHEN** the same `eventId` is delivered twice for a repository row
- **THEN** the worker completes the message without repeating Snyk side effects

#### Scenario: Updated body moves to a different org
- **WHEN** a parsed updated body resolves a Snyk org id that differs from the non-empty `snykOrgId` on the repository row
- **THEN** the worker imports the GitHub repository into the resolved org

#### Scenario: Blank stored org does not force a new import
- **WHEN** a parsed updated body resolves the same repository name and branch already stored, and `snykOrgId` is blank
- **THEN** the worker does not start a new import solely because the stored org id is blank

### Requirement: Unrecoverable failure handling
On unrecoverable processing failure, the worker MUST reject or dead-letter the message and emit an alert.

On `serviceBus`, dead-letter MUST use the Service Bus dead-letter queue. On `kafka`, a failed inbound `/github-events` request MUST return non-2xx so the event connector retries it, while a failed internal Storage queue follow-up MUST poison-settle per the `storage-queue-transport` capability. Dead-letter reason strings for queued messages MUST remain the same across queue transports.

Import job polling MUST dead-letter or poison-settle with reason `ImportJobFailed` when `retryCount` reaches 5 on `import_poll` follow-up messages.

v1 project-ignore migration MUST dead-letter or poison-settle with reason `IgnoreMigrationFailed` when `retryCount` reaches 5 on `ignore_migration` follow-up messages.

#### Scenario: Snyk import permanently fails for HTTP ingress
- **WHEN** initial processing of a `/github-events` request fails with an unrecoverable Snyk error
- **THEN** the endpoint returns non-2xx and an alert is raised

#### Scenario: Snyk import polling permanently fails
- **WHEN** a queued `import_poll` follow-up reaches its retry limit
- **THEN** the message is dead-lettered or poison-settled for the active queue transport and an alert is raised

#### Scenario: Ignore migration permanently fails
- **WHEN** a queued `ignore_migration` follow-up reaches its retry limit
- **THEN** the message is dead-lettered or poison-settled with reason `IgnoreMigrationFailed` and the source projects remain active

### Requirement: Internal follow-up message routing
The worker MUST deserialize internal follow-up messages on the active follow-up queue, distinguished by top-level `syncPhase`. Supported values: `import_poll`, `lifecycle_deferred`, `ignore_migration`.

On `serviceBus`, that queue is the Service Bus queue. On `kafka`, that queue is the storage queue.

Internal messages MUST NOT be parsed as ADO Event Grid or GitHub webhook payloads.

#### Scenario: Import poll follow-up received
- **WHEN** the worker receives a message with `syncPhase: import_poll`
- **THEN** it polls the referenced import job and reschedules, finalizes state, or dead-letters per retry policy

#### Scenario: Lifecycle deferred follow-up received
- **WHEN** the worker receives a message with `syncPhase: lifecycle_deferred`
- **THEN** it re-attempts the deferred lifecycle action when pending import count is below the configured limit

#### Scenario: Ignore migration follow-up received
- **WHEN** the worker receives a message with `syncPhase: ignore_migration`
- **THEN** it copies or skips v1 project ignores and retires the source only when that event requires retirement

### Requirement: Slice-5 lifecycle sync without project tagging
In this implementation slice, after import job completion the worker MUST update repository state with `importStatus=complete` and `snykTargetId`. The worker MUST NOT call the Projects API to apply repository id tags or set `tagApplied=true`.

Listing projects and reading or creating v1 project ignores MUST be allowed for `snyk-project-ignore-migration`.

#### Scenario: Import completes in slice 5
- **WHEN** the import job succeeds
- **THEN** repository state is updated with `importStatus=complete`, `snykTargetId`, retained `importJobId`, and `tagApplied=false`

### Requirement: Custom property updated imports the GitHub repository
The worker MUST normalize the parsed updated body in `data/fixtures/github_parsed_updated.json` to `repo.created` and MUST record on the normalized event that the body was a parsed updated import. It MUST run the GitHub create flow for that event, including a new import when the org-move rule in idempotency applies. This body is the import signal for the parsed updated contract. The worker MUST NOT require a GitHub `action: created` body before importing.

After that import completes, and when `snyk.migrateIgnores` is `true`, the worker MUST copy v1 project ignores from the Azure DevOps target identified by the extracted `azure-devops-project` value when that target exists. When `snyk.migrateIgnores` is `false`, the worker MUST skip that copy. The lookup MUST use integration type `azure-repos` in the resolved Snyk org, owner equal to that property value, repository name equal to the GitHub repository name, and branch equal to the import branch. A missing ADO target MUST skip the copy and MUST still leave the GitHub import complete.

The worker MUST NOT deactivate or delete an Azure DevOps Snyk target because a GitHub updated event imported the repository. It MUST NOT deactivate or delete the previous GitHub target. It MUST NOT persist a standing link from the GitHub repository to an ADO project or ADO target. In-flight migration fields cleared at the end of the attempt are not a standing link.

#### Scenario: Updated body imports the GitHub repository
- **WHEN** the worker receives `data/fixtures/github_parsed_updated.json` and scope mapping resolves a Snyk org
- **THEN** it runs the GitHub `repo.created` import path for that body's `repository` and records the event as a parsed updated import

#### Scenario: Updated import copies ADO project ignores
- **WHEN** `snyk.migrateIgnores` is `true` and the GitHub updated event imports a repository and an `azure-repos` target exists for the extracted `azure-devops-project` value, the GitHub repository name, and the import branch
- **THEN** the worker copies v1 project ignores from that ADO target onto the new GitHub projects and does not deactivate or delete the ADO target

#### Scenario: Updated import leaves ADO targets in place
- **WHEN** the GitHub updated event imports a repository whose `azure-devops-project` value names an ADO project that already has a Snyk target
- **THEN** the worker does not deactivate or delete that ADO target

#### Scenario: Updated import with no ADO target
- **WHEN** the GitHub updated event imports a repository and no matching `azure-repos` target exists
- **THEN** the worker completes the GitHub import, skips the ignore copy, and does not fail the message

### Requirement: Operator Snyk settings in config
The worker MUST load optional `snyk` settings from operator config at startup: `maxConcurrentPendingImports` (default 100), `migrateIgnores` (boolean, default `true`), and `targetRemoval` with keys `onRename`, `onDefaultBranchChange`, and `onRepoDelete` (each `deactivate` or `delete`, default `deactivate`).

Invalid removal mode values MUST cause startup failure. A non-boolean `snyk.migrateIgnores` MUST cause startup failure.

The worker MUST require `SNYK_TOKEN` from the environment when Snyk sync is enabled for mapped ADO processing.

#### Scenario: Default Snyk settings
- **WHEN** `snyk` section is absent from config
- **THEN** the worker uses `maxConcurrentPendingImports=100`, `migrateIgnores=true`, and deactivation for all removal actions

#### Scenario: Missing SNYK_TOKEN at startup
- **WHEN** the worker starts without `SNYK_TOKEN` set
- **THEN** it exits with a non-zero status and a clear error message

#### Scenario: Migrate ignores disabled
- **WHEN** `snyk.migrateIgnores` is `false`
- **THEN** the worker loads that value and skips v1 project-ignore copies

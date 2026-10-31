## Purpose

Queue-driven worker that normalizes provider events, validates state, routes repo lifecycle events by source, enforces idempotency, and handles retries and dead-lettering. Event normalization is owned by the worker application in this repository so lifecycle mapping ships with worker releases rather than customer-owned ingress infrastructure.

Scope-to-Snyk resolution is owned by the `scope-mapping` capability (operator config + Snyk API), not Table Storage `_meta` rows.
## Requirements
### Requirement: Queue-driven processing
The worker MUST consume messages from the selected transport on demand; it MUST NOT rely on always-on polling of ADO, GitHub, or Snyk as its primary trigger.

On `serviceBus`, provider events and internal follow-ups come from the Service Bus queue. On `kafka`, GitHub events arrive as event-connector POST requests to `/github-events` and internal follow-ups come from the Storage queue.

#### Scenario: Message available
- **WHEN** a Service Bus or Storage queue message is available on the selected transport, or the Kafka event connector posts a GitHub event
- **THEN** the worker receives and processes it

### Requirement: Multi-source event normalization
The worker MUST parse native queue messages and produce a normalized internal lifecycle event model before sync state access or lifecycle actions. Lifecycle normalization MUST be implemented in the worker application in this repository, not in customer-owned ingress infrastructure.

The worker MUST infer `source` from message structure. ADO identification MUST be applied before GitHub identification:

| Detected source | Identification rule |
| --------------- | ------------------- |
| `"ado"` | `eventType` is `AzureDevOpsAuditEvent` **or** `subject` is `AzureDevOps/Auditing` |
| `"github"` | `repository` is an object and `newPropertyValues` is an array, and `action` is not a non-empty string |
| `"github"` | Top-level JSON with `repository` object and string `action` (when not ADO) |

For ADO, the audit record MUST be read from Event Grid `data`. For GitHub raw webhook, parsed lifecycle, and parsed updated messages, the queue message body is the full GitHub payload. For the parsed updated body, repository fields MUST be read from top-level `repository`.

GitHub messages MUST be classified by shape in this order:

| Shape | Detection |
| ----- | --------- |
| Parsed updated | `repository` is an object, `newPropertyValues` is an array, and `action` is not a non-empty string |
| Parsed contract | Non-empty string top-level `deliveryId` |
| Raw webhook | Otherwise |

The normalized model MUST include:

| Field | Type | ADO source | GitHub source |
| ----- | ---- | ---------- | ------------- |
| `source` | `"ado"` \| `"github"` | inferred | inferred |
| `eventId` | string | audit `Id` in `data` | parsed lifecycle and parsed updated: `deliveryId`; raw: delivery id from message metadata when available |
| `eventType` | lifecycle enum | audit `ActionId` | webhook `action` or parsed updated body (see GitHub mapping) |
| `scopeId` | string | `ProjectId` | org login (`repository.owner.login`) |
| `repositoryId` | string | `Data.RepoId` | `repository.id` (string) |
| `occurredAt` | datetime UTC | audit `Timestamp` | raw: `repository.updated_at`; parsed lifecycle: `repository.updatedAt`; parsed updated: `repository.updatedAt` |
| `ado` | object | ADO scope table | absent |
| `github` | object | absent | see GitHub scope table |
| `repository` | object | `name` ← `Data.RepoName` | `name` ← repository `name` |
| `payload` | object | event-specific | event-specific |

Supported `eventType` values: `repo.created`, `repo.renamed`, `repo.deleted`, `repo.default_branch_changed`.

When `source` is `"ado"`, the `ado` object MUST include:

| Field | ADO audit source |
| ----- | ---------------- |
| `orgId` | `ScopeId` |
| `orgDisplayName` | `ScopeDisplayName` |
| `projectId` | `ProjectId` (MUST equal `scopeId`) |
| `projectName` | `ProjectName` |

When `source` is `"github"`, the `github` object MUST include:

| Field | Source |
| ----- | ------ |
| `orgLogin` | repository owner login (MUST equal `scopeId`) |

The `ado` object MUST be absent when `source` is `"github"`. The `github` object MUST be absent when `source` is `"ado"`.

Property values used for Snyk org selection MUST NOT replace `scopeId` or `github.orgLogin`.

ADO audit `ActionId` mapping:

| `ActionId` | `eventType` |
| -------- | ----------- |
| `Git.RepositoryCreated` | `repo.created` |
| `Git.RepositoryRenamed` | `repo.renamed` |
| `Git.RepositoryDeleted` | `repo.deleted` |
| `Git.RepositoryDefaultBranchChanged` | `repo.default_branch_changed` |

GitHub mapping:

| Inbound signal | `eventType` | Conditions |
| -------- | ----------- | ---------- |
| Parsed updated body | `repo.created` | `repository` is an object and `newPropertyValues` is an array; this is the import for the parsed updated contract |
| `action: created` | `repo.created` | existing raw webhook and parsed lifecycle fixtures only |
| `renamed` | `repo.renamed` | — |
| `deleted` | `repo.deleted` | — |
| `edited` | `repo.default_branch_changed` | `changes.default_branch.from` present (snake_case in parsed contract) |
| `edited` | *(no normalized lifecycle)* | no `changes.default_branch.from` — complete without sync |

Normalized `payload` fields by `eventType`:

| `eventType` | `payload` fields |
| ----------- | ---------------- |
| `repo.created` | optional `defaultBranch` from repository default branch field |
| `repo.renamed` | optional `previousRepoName` from `changes.repository.name.from` when present |
| `repo.deleted` | none |
| `repo.default_branch_changed` | `defaultBranch` (new); optional `previousDefaultBranch` from `changes.default_branch.from` |

Branch values in `payload` MUST NOT include the `refs/heads/` prefix.

GitHub repositories with owner type other than `Organization` MUST complete without normalization error and without lifecycle sync.

Existing fixtures under `data/fixtures/github_webhook_*.json`, `data/fixtures/github_parsed_created.json`, `data/fixtures/github_parsed_renamed.json`, `data/fixtures/github_parsed_deleted.json`, `data/fixtures/github_parsed_edited_*.json`, and `data/fixtures/eventgrid_ado_*.json` MUST keep their current normalized outcomes.

#### Scenario: ADO audit stream normalized to repo created
- **WHEN** the worker receives an Event Grid message identified as ADO with audit `ActionId: Git.RepositoryCreated` and required scope, project, and repository fields in `data`
- **THEN** it produces a normalized event with `eventType: repo.created`, populated `ado` org and project fields, `repository.name`, and optional `payload.defaultBranch`

#### Scenario: ADO audit stream normalized to repo renamed
- **WHEN** the worker receives an Event Grid message identified as ADO with audit `ActionId: Git.RepositoryRenamed` and required fields including `Data.PreviousRepoName`
- **THEN** it produces a normalized event with `eventType: repo.renamed`, populated `ado` org and project fields, `repository.name`, and `payload.previousRepoName`

#### Scenario: ADO audit stream normalized to repo deleted
- **WHEN** the worker receives an Event Grid message identified as ADO with audit `ActionId: Git.RepositoryDeleted` and required scope, project, and repository fields in `data`
- **THEN** it produces a normalized event with `eventType: repo.deleted`, populated `ado` org and project fields, and `repository.name`

#### Scenario: ADO audit stream normalized to default branch changed
- **WHEN** the worker receives an Event Grid message identified as ADO with audit `ActionId: Git.RepositoryDefaultBranchChanged` and required scope, project, repository, and branch fields in `data`
- **THEN** it produces a normalized event with `eventType: repo.default_branch_changed`, populated `ado` org and project fields, `repository.name`, and `payload.defaultBranch` / `payload.previousDefaultBranch` without `refs/heads/` prefixes

#### Scenario: GitHub raw webhook normalized to repo created
- **WHEN** the worker receives raw GitHub webhook JSON with `action: created` and required repository and owner fields
- **THEN** it produces a normalized event with `source: github`, `eventType: repo.created`, `scopeId` equal to org login, populated `github.orgLogin`, and optional `payload.defaultBranch`

#### Scenario: GitHub parsed contract normalized to repo created
- **WHEN** the worker receives parsed JSON with `deliveryId`, `action: created`, and camelCase repository fields
- **THEN** it produces a normalized event with `eventId` equal to `deliveryId` and the same normalized fields as the raw created scenario

#### Scenario: GitHub parsed updated normalized to repo created
- **WHEN** the worker receives `data/fixtures/github_parsed_updated.json`
- **THEN** it produces `source: github`, `eventType: repo.created`, `eventId` equal to `deliveryId` (`b2c3d4e5-f6a7-8901-bcde-f12345678901`), `scopeId` and `github.orgLogin` equal to `sample-org`, `repository.name` equal to `sample-repo`, and `occurredAt` equal to `repository.updatedAt` (`2026-09-02T12:00:00Z`)

#### Scenario: GitHub renamed with previous name in changes
- **WHEN** the worker receives GitHub JSON with `action: renamed` and `changes.repository.name.from`
- **THEN** it produces `eventType: repo.renamed` with `payload.previousRepoName` set from `from` and `repository.name` as the new name

#### Scenario: GitHub edited with default branch change
- **WHEN** the worker receives GitHub JSON with `action: edited` and `changes.default_branch.from`
- **THEN** it produces `eventType: repo.default_branch_changed` with `payload.previousDefaultBranch` from `from` and `payload.defaultBranch` from the repository default branch field

#### Scenario: GitHub edited without default branch change
- **WHEN** the worker receives GitHub JSON with `action: edited` and no `changes.default_branch.from`
- **THEN** it completes the message without lifecycle sync

#### Scenario: Unrecognized or unsupported provider payload
- **WHEN** the worker receives an ADO message with an unsupported audit `ActionId` or missing required audit/`Data` fields, or a GitHub message missing required repository or owner fields for a supported action
- **THEN** it dead-letters the message with reason `InvalidNormalization`

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
- **THEN** the worker triggers import, upserts pending repository state, schedules import job polling if needed, and completes or dead-letters the message per retry policy

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

### Requirement: Rate limit backoff
The worker MUST apply exponential backoff when Snyk or upstream provider APIs (ADO or GitHub) return rate-limit responses.

#### Scenario: Snyk rate limit
- **WHEN** the Snyk API returns a rate-limit response during import
- **THEN** the worker retries with exponential backoff before succeeding or failing unrecoverably

### Requirement: Import job polling with concurrency limits
When an import is initiated, the worker MUST NOT block the receive loop until the job completes. The worker MUST schedule follow-up messages with exponential backoff and MUST respect `snyk.maxConcurrentPendingImports` (default 100 per worker process).

On `serviceBus`, follow-ups MUST be scheduled on that same Service Bus queue. On `kafka`, follow-ups MUST be scheduled on the storage queue in the sync-state storage account. Follow-ups MUST NOT be published to Kafka.

Follow-up messages MUST carry `syncPhase`, `importJobId`, `importStatus`, and `retryCount`.

#### Scenario: Import in progress
- **WHEN** Snyk returns an in-progress import job
- **THEN** the worker upserts `importStatus=pending`, completes the current message, and schedules an `import_poll` follow-up with incremented backoff on the active follow-up queue

#### Scenario: Import job completes
- **WHEN** an `import_poll` follow-up finds the import job succeeded
- **THEN** the worker updates repository state with `importStatus=complete`, retains `importJobId`, sets `snykTargetId`, and completes the follow-up message without project tagging

#### Scenario: Pending import limit reached
- **WHEN** the count of repository rows with `importStatus=pending` equals or exceeds `snyk.maxConcurrentPendingImports`
- **THEN** the worker logs a structured warning, completes the lifecycle message, and schedules a `lifecycle_deferred` follow-up with backoff rather than dead-lettering

### Requirement: Ignored repo short-circuit
Before executing repo lifecycle actions, the worker MUST evaluate ignore policy (explicit entries and name patterns) loaded from `ignoredRepos.path` and MUST NOT import repos that match. Ignore policy MUST be evaluated immediately on every lifecycle event type (create, rename, default branch change).

When a matching repository has an active Snyk target, the worker MUST remove it per `snyk.targetRemoval.onIgnore` before completing the message without import.

#### Scenario: Ignored repo created
- **WHEN** a repo-created event matches the ignore policy
- **THEN** the worker completes the message without import or tag actions

#### Scenario: Ignored repo renamed
- **WHEN** a repo-renamed event produces a new name matching ignore policy
- **THEN** the worker removes the existing target per `onIgnore`, does not import the new name, and completes the message

#### Scenario: Ignored repo default branch changed
- **WHEN** a default-branch-changed event matches ignore policy
- **THEN** the worker removes the existing target per `onIgnore` if active, does not re-import, and completes the message

### Requirement: Manifest changes are out of scope
The worker MUST NOT act on within-repo manifest or file changes; Repo Content Sync handles those after import.

#### Scenario: Manifest change event
- **WHEN** a manifest or file change event is received (if any)
- **THEN** the worker ignores it or does not subscribe to such events

### Requirement: Operator config and credential startup
The worker MUST authenticate to Azure with `DefaultAzureCredential`. It MUST load operator settings from the config file path supplied via `--config` (default `data/config.yaml`). The config file MUST exist. Settings MAY be supplied in config and MAY be overridden by environment variables; env values MUST take precedence when set. The worker MUST ensure the sync-state table exists on startup. Connection strings MUST NOT be supported or documented.

On `serviceBus`, the worker MUST authenticate to Azure Service Bus and the runtime identity MUST be granted **Azure Service Bus Data Owner** (or Azure Service Bus Data Receiver and Azure Service Bus Data Sender) on the queue or namespace — data plane only. On `kafka`, Service Bus credentials MUST NOT be required, and the runtime identity MUST be granted the queue data role from the `storage-queue-transport` capability.

On every transport the runtime identity MUST be granted **Storage Table Data Contributor** on the storage account or table scope.

The worker MUST fail fast when the config file path does not exist, when required settings for the selected transport are missing after config/env merge, or when credential initialization fails.

#### Scenario: Worker starts in production on Service Bus
- **WHEN** the container starts with `--config /config/config.yaml`, `messaging.transport` omitted or `serviceBus`, valid YAML, and a managed identity with Service Bus and table RBAC roles
- **THEN** it ensures the sync-state table exists, connects to the pre-provisioned Service Bus queue, and begins receiving messages

#### Scenario: Local run with default config path
- **WHEN** a developer runs `worker run` without `--config`
- **THEN** the worker loads `data/config.yaml` and authenticates via `az login` (or configured dev principal)

#### Scenario: Local run with env override
- **WHEN** `data/config.yaml` exists, transport is `serviceBus`, and `SERVICEBUS_QUEUE_NAME` overrides the file value
- **THEN** the worker uses the env value for the queue name

#### Scenario: Missing config file
- **WHEN** `--config` points to a path that does not exist
- **THEN** the worker exits with a non-zero status and a clear error message

#### Scenario: Missing required setting after merge
- **WHEN** transport is `serviceBus` and `serviceBus.fullyQualifiedNamespace` is absent in both config and env after merge
- **THEN** the worker exits with a non-zero status and a clear error message

### Requirement: Existing queue reference only
On the `serviceBus` transport, the worker MUST consume from a pre-provisioned Service Bus queue. The worker MUST NOT create, alter, or delete Service Bus queues or namespaces.

On the `kafka` transport, the worker MUST NOT open a Service Bus client. Storage queue provisioning rules are defined by the `storage-queue-transport` capability.

#### Scenario: Queue consumption
- **WHEN** transport is `serviceBus` and transport messages are available on the configured queue
- **THEN** the worker receives them without provisioning queue infrastructure

### Requirement: Transport integration tests
The repository MUST include integration tests that publish native queue message fixtures to the configured or emulated Service Bus queue and assert the worker consumes and completes them.

#### Scenario: ADO fixture end-to-end
- **WHEN** an integration test publishes an ADO Event Grid fixture to the queue
- **THEN** the worker receives and completes the message

#### Scenario: GitHub fixture end-to-end
- **WHEN** an integration test publishes a raw GitHub webhook fixture to the queue
- **THEN** the worker receives and completes the message

### Requirement: Native queue message parsing
The worker MUST deserialize inbound queue messages as JSON and identify the provider source from message structure. ADO messages MUST be identified when `eventType` is `AzureDevOpsAuditEvent` **or** `subject` is `AzureDevOps/Auditing`; the audit record MUST be extracted from `data`.

GitHub parsed updated messages MUST be identified when `repository` is an object, `newPropertyValues` is an array, and `action` is not a non-empty string. Other GitHub messages MUST be identified by JSON shape (top-level `repository` and `action`). Parsed GitHub contract messages MUST be recognized when `deliveryId` is present.

Unrecognized or invalid JSON MUST dead-letter with reason `InvalidMessage`.

#### Scenario: Valid ADO Event Grid message
- **WHEN** the worker receives Event Grid JSON with `subject: AzureDevOps/Auditing` and a valid audit object in `data`
- **THEN** it parses the message as ADO and extracts the audit record from `data`

#### Scenario: Valid ADO message by eventType only
- **WHEN** the worker receives Event Grid JSON with `eventType: AzureDevOpsAuditEvent` and a valid audit object in `data`
- **THEN** it parses the message as ADO and extracts the audit record from `data`

#### Scenario: Valid GitHub parsed updated message
- **WHEN** the worker receives `data/fixtures/github_parsed_updated.json`
- **THEN** it parses the message as GitHub parsed updated shape and uses top-level `deliveryId` as the event id

#### Scenario: Valid GitHub raw webhook message
- **WHEN** the worker receives raw webhook JSON with `repository` and `action` fields and no top-level `deliveryId`
- **THEN** it parses the message as GitHub raw webhook shape

#### Scenario: Valid GitHub parsed contract message
- **WHEN** the worker receives JSON with `deliveryId`, `repository`, and `action`
- **THEN** it parses the message as GitHub parsed contract shape

#### Scenario: Malformed queue message
- **WHEN** the worker receives a message that is not valid JSON, is not a JSON object, or matches no supported provider shape
- **THEN** it dead-letters the message with reason `InvalidMessage`

### Requirement: Slice-5 ADO lifecycle sync with import deferral
After successful lifecycle normalization and scope mapping resolution, the worker MUST execute repository lifecycle sync per the `repo-lifecycle` and `snyk-target-sync` capabilities for mapped scopes (ADO and GitHub).

The worker MUST read and write repository sync state, call the Snyk API, and route internal follow-up messages on the active follow-up queue for the selected transport (the Service Bus queue on `serviceBus`; the storage queue on `kafka`).

#### Scenario: Valid ADO message with mapped project and repo created
- **WHEN** the worker normalizes a repo-created ADO message whose scope mapping resolves
- **THEN** it triggers Snyk import and updates sync state without completing import inline in the receive handler

#### Scenario: Valid ADO message with unmapped project
- **WHEN** the worker normalizes an ADO lifecycle message whose scope has no mapping and no default org
- **THEN** it logs an unmapped-scope warning and completes the message without Snyk side effects

#### Scenario: Valid GitHub message with mapped org and repo created
- **WHEN** the worker normalizes a repo-created GitHub message whose scope mapping resolves by org login
- **THEN** it triggers Snyk import and updates sync state without completing import inline in the receive handler

#### Scenario: Valid GitHub message with unmapped org
- **WHEN** the worker normalizes a GitHub lifecycle message whose org login has no mapping and no default org
- **THEN** it logs an unmapped-scope warning and completes the message without Snyk side effects

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

### Requirement: Operator Azure Container App deployment documentation
Operator documentation MUST describe deploying the worker as an Azure Container App with: managed identity, RBAC roles for Service Bus and Table Storage, config file mount at `/config/config.yaml`, secret injection for `SNYK_TOKEN`, conditional secret injection for `ADO_PAT` when `scopeMapping.azure-repos` contains one or more mappings, and optional KEDA Service Bus scaling for replica count based on queue depth. Documentation MUST NOT document Container App Job deployment.

Operator documentation MUST state that `ado.organization` and `ADO_PAT` with Code (Read) are required for deployments with explicit `azure-repos` mappings and are not required for deployments without those mappings.

Operator documentation MUST reference the canonical container image **`ghcr.io/snyk-ps/snyk-repo-sync:<version>`** (where `<version>` is the release tag, e.g. `v0.1.0`).

README.md MUST place the **Deployment** section before local development / installation instructions so operators see production guidance first.

#### Scenario: Operator deploys worker to Azure
- **WHEN** an operator follows README deployment guidance after completing INGESTION.md queue setup
- **THEN** they can configure a Container App with identity, applicable secrets, config mount, queue connection settings, and the GHCR image `ghcr.io/snyk-ps/snyk-repo-sync:<version>` without reading application source code

#### Scenario: Operator deploys GitHub-only worker
- **WHEN** an operator deploys a worker without any `scopeMapping.azure-repos` entries
- **THEN** documentation makes clear that neither `ado.organization` nor `ADO_PAT` needs to be configured

#### Scenario: Operator deploys worker with ADO mappings
- **WHEN** an operator deploys a worker with one or more `scopeMapping.azure-repos` entries
- **THEN** documentation instructs them to configure `ado.organization` and inject `ADO_PAT` with Code (Read)

#### Scenario: Operator enables queue-driven scaling
- **WHEN** an operator reads optional KEDA scaling guidance in README deployment documentation
- **THEN** they can configure a Service Bus message-count scaler without changing worker application code

#### Scenario: Operator finds deployment before local setup
- **WHEN** an operator opens README.md
- **THEN** the Deployment runbook appears before local development / installation instructions

### Requirement: Ignore policy startup load
When `ignoredRepos.path` is configured, the worker MUST load and validate the ignore-policy file at startup. The worker MUST run a background reconciliation loop at `ignoredRepos.reconciliationIntervalMinutes` (default 15).

#### Scenario: Worker starts with ignore policy configured
- **WHEN** the worker starts with a valid `ignoredRepos.path` and policy file
- **THEN** ignore policy is loaded, persisted to sync state, and reconciliation is scheduled

#### Scenario: Missing policy file at startup
- **WHEN** `ignoredRepos.path` is set and the policy file does not exist at startup
- **THEN** the worker exits with a clear configuration error

### Requirement: Continuous queue consumption on idle queue
On the `serviceBus` transport, the worker MUST remain running and continue polling the configured Service Bus queue when no messages are available. An idle queue MUST NOT cause the worker process to exit with status 0.

#### Scenario: Empty queue does not stop worker
- **WHEN** the worker starts successfully on the `serviceBus` transport and the queue has no available messages for longer than one receive poll interval
- **THEN** the worker continues polling and does not exit solely due to the idle period

#### Scenario: Message processed after idle period
- **WHEN** the worker is polling an idle Service Bus queue and a message is later published
- **THEN** the worker receives and processes the message without requiring a process restart

### Requirement: Service Bus receive poll interval
On the `serviceBus` transport, the worker MUST poll the queue using a configurable maximum wait time per receive attempt. The default MUST be 5 seconds. The setting MUST be read from `serviceBus.receiveMaxWaitSeconds` in operator config, with environment override `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS`. Invalid values MUST fail at startup with a clear configuration error.

The receive poll interval MUST NOT be implemented by setting `max_wait_time` on the Service Bus receiver constructor when iterating messages, because that causes the SDK iterator to terminate after an idle timeout.

#### Scenario: Default poll interval
- **WHEN** transport is `serviceBus` and `serviceBus.receiveMaxWaitSeconds` is omitted from config
- **THEN** the worker uses a 5-second maximum wait per receive attempt

#### Scenario: Configured poll interval
- **WHEN** transport is `serviceBus` and `serviceBus.receiveMaxWaitSeconds` is set to a positive integer in config
- **THEN** the worker uses that value for each receive attempt

#### Scenario: Environment override
- **WHEN** transport is `serviceBus` and `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS` is set in the environment
- **THEN** it takes precedence over the config file value

### Requirement: Selectable message transport
The worker MUST select a message transport from `messaging.transport` in operator config, overridable by `MESSAGING_TRANSPORT`. Allowed values are `serviceBus` and `kafka`. When the key is omitted, the transport MUST be `serviceBus`. Any other value MUST fail startup with a clear configuration error.

On `serviceBus`, GitHub events, ADO events, and internal follow-ups MUST use the configured Service Bus queue, and `serviceBus.fullyQualifiedNamespace` and `serviceBus.queueName` MUST remain required. Storage queue and GitHub events HTTP settings MUST be ignored.

On `kafka`, internal follow-ups MUST use the Storage queue from the `storage-queue-transport` capability, GitHub events MUST use connector-pushed HTTP ingress from `github-events-http-ingress`, and Service Bus settings MUST NOT be required. The production worker command MUST start both the HTTP ingress and Storage queue follow-up consumer and MUST stop both if either component terminates unexpectedly.

#### Scenario: Existing config stays on Service Bus
- **WHEN** operator config has `serviceBus` and `syncState` sections and no `messaging.transport`
- **THEN** the worker consumes and schedules messages on the Service Bus queue as before and does not start an HTTP listener

#### Scenario: Unknown transport
- **WHEN** `messaging.transport` is `eventHub`
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Kafka transport does not require Service Bus settings
- **WHEN** `messaging.transport` is `kafka`, `serviceBus` is absent, and Storage queue and HTTP settings are valid
- **THEN** startup initializes the private `/github-events` listener and Storage queue consumer without failing for a missing Service Bus namespace or queue name

#### Scenario: Kafka component terminates unexpectedly
- **WHEN** the Kafka-mode HTTP server or Storage queue consumer exits unexpectedly
- **THEN** the worker stops the other component and exits non-zero

### Requirement: Storage queue idle consumption
When the storage-queue transport is running, the worker MUST keep polling it when no messages are available. An idle queue MUST NOT cause the process to exit with status 0. The poll wait MUST use `storageQueue.receiveMaxWaitSeconds`.

#### Scenario: Empty storage queue does not stop the consumer
- **WHEN** the storage-queue consumer is running and no messages are visible for longer than one poll interval
- **THEN** it continues polling and does not exit solely because the queue is idle

### Requirement: Kafka HTTP ingress integration tests
The repository MUST include integration tests that post already-supported GitHub fixture bodies to `/github-events` and assert synchronous HTTP outcomes and follow-up routing without requiring a Kafka client.

#### Scenario: Existing GitHub fixture succeeds
- **WHEN** an integration test posts an already-supported GitHub `renamed`, `edited`, or `deleted` fixture and processing succeeds
- **THEN** the endpoint returns 204 and performs the expected lifecycle handling

#### Scenario: Follow-up is durable before acknowledgement
- **WHEN** an integration test posts an event whose handling requests an internal follow-up
- **THEN** the Storage queue fake or emulator observes the follow-up before the endpoint returns 204

#### Scenario: Failed processing is retryable
- **WHEN** an integration test injects a processing or follow-up scheduling failure
- **THEN** the endpoint returns non-2xx

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


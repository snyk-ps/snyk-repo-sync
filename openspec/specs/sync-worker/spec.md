## Purpose

Queue-driven worker that normalizes provider events, validates state, routes repo lifecycle events by source, enforces idempotency, and handles retries and dead-lettering. Event normalization is owned by the worker application in this repository so lifecycle mapping ships with worker releases rather than customer-owned ingress infrastructure.

Scope-to-Snyk resolution is owned by the `scope-mapping` capability (operator config + Snyk API), not Table Storage `_meta` rows.
## Requirements
### Requirement: Queue-driven processing
The worker MUST consume messages from the Service Bus queue on demand; it MUST NOT rely on always-on polling of ADO, GitHub, or Snyk as its primary trigger.

#### Scenario: Message available
- **WHEN** a transport message is available on the queue
- **THEN** the worker receives and processes it

### Requirement: Multi-source event normalization
The worker MUST parse native queue messages and produce a normalized internal lifecycle event model before sync state access or lifecycle actions. Lifecycle normalization MUST be implemented in the worker application in this repository, not in customer-owned ingress infrastructure.

The worker MUST infer `source` from message structure:

| Detected source | Identification rule |
| --------------- | ------------------- |
| `"ado"` | `eventType` is `AzureDevOpsAuditEvent` **or** `subject` is `AzureDevOps/Auditing` |
| `"github"` | Top-level webhook JSON with `repository` object and string `action` (when not ADO) |

For ADO, the audit record MUST be read from Event Grid `data`. For GitHub, the webhook body is the queue message body.

The normalized model MUST include:

| Field | Type | ADO source | GitHub source (future) |
| ----- | ---- | ---------- | ---------------------- |
| `source` | `"ado"` \| `"github"` | inferred from message shape | inferred from message shape |
| `eventId` | string | audit `Id` in `data` | delivery id (future) |
| `eventType` | lifecycle enum | mapped from audit `ActionId` | mapped from webhook action |
| `scopeId` | string | `ProjectId` | organization id |
| `repositoryId` | string | `Data.RepoId` | repository id (string) |
| `occurredAt` | datetime UTC | audit `Timestamp` | webhook timestamp |
| `ado` | object | see ADO scope table | absent |
| `repository` | object | `name` ← `Data.RepoName` | repo name (future) |
| `payload` | object | event-specific fields | event-specific fields (future) |

Supported `eventType` values: `repo.created`, `repo.renamed`, `repo.deleted`, `repo.default_branch_changed`.

When `source` is `"ado"`, the `ado` object MUST include:

| Field | ADO audit source |
| ----- | ---------------- |
| `orgId` | `ScopeId` |
| `orgDisplayName` | `ScopeDisplayName` |
| `projectId` | `ProjectId` (MUST equal `scopeId`) |
| `projectName` | `ProjectName` |

ADO audit `ActionId` mapping:

| `ActionId` | `eventType` |
| -------- | ----------- |
| `Git.RepositoryCreated` | `repo.created` |
| `Git.RepositoryRenamed` | `repo.renamed` |
| `Git.RepositoryDeleted` | `repo.deleted` |
| `Git.RepositoryDefaultBranchChanged` | `repo.default_branch_changed` |

Normalized `payload` fields by `eventType`:

| `eventType` | Required `payload` fields |
| ----------- | ------------------------- |
| `repo.created` | none; `defaultBranch` optional if present in audit `Data` |
| `repo.renamed` | `previousRepoName` |
| `repo.deleted` | none |
| `repo.default_branch_changed` | `defaultBranch`, `previousDefaultBranch` |

Branch values in `payload` MUST NOT include the `refs/heads/` prefix.

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

#### Scenario: GitHub webhook normalized to repo renamed
- **WHEN** the worker receives a queue message with raw GitHub webhook JSON containing a `repository` webhook with action `renamed`
- **THEN** it produces a normalized event with `eventType: repo.renamed` before further processing

#### Scenario: Unrecognized or unsupported provider payload
- **WHEN** the worker receives an ADO message with an unsupported audit `ActionId` or missing required audit/`Data` fields
- **THEN** it dead-letters the message with reason `InvalidNormalization`

#### Scenario: GitHub message before normalization implementation
- **WHEN** the worker receives a valid GitHub webhook queue message before GitHub normalization is implemented
- **THEN** it completes the message without normalization or sync side effects

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

### Requirement: Idempotency by event and desired state
The worker MUST skip duplicate processing when `lastEventId` matches the incoming `eventId` or when `desiredStateHash` already reflects the intended outcome.

#### Scenario: Duplicate delivery
- **WHEN** the same `eventId` is delivered twice for a repository row
- **THEN** the worker completes the message without repeating Snyk side effects

### Requirement: Unrecoverable failure handling
On unrecoverable processing failure, the worker MUST dead-letter the message and emit an alert.

Import job polling MUST dead-letter with reason `ImportJobFailed` when `retryCount` reaches 5 on `import_poll` follow-up messages.

#### Scenario: Snyk import permanently fails
- **WHEN** import fails after retries/backoff with a non-transient error or max poll retries exceeded
- **THEN** the message is dead-lettered and an alert is raised

### Requirement: Rate limit backoff
The worker MUST apply exponential backoff when Snyk or upstream provider APIs (ADO or GitHub) return rate-limit responses.

#### Scenario: Snyk rate limit
- **WHEN** the Snyk API returns a rate-limit response during import
- **THEN** the worker retries with exponential backoff before succeeding or failing unrecoverably

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
The worker MUST authenticate to Azure Service Bus and Azure Table Storage using `DefaultAzureCredential`. It MUST load operator settings from the config file path supplied via `--config` (default `data/config.yaml`). The config file MUST exist. Service Bus and sync-state settings MAY be supplied in config and MAY be overridden by environment variables; env values MUST take precedence when set. The worker MUST ensure the sync-state table exists on startup. Connection strings MUST NOT be supported or documented.

The runtime identity MUST be granted:
- **Azure Service Bus Data Owner** (or Azure Service Bus Data Receiver and Azure Service Bus Data Sender) on the queue or namespace — data plane only
- **Storage Table Data Contributor** on the storage account or table scope

The worker MUST fail fast when the config file path does not exist, when required settings are missing after config/env merge, or when credential initialization fails.

#### Scenario: Worker starts in production
- **WHEN** the container starts with `--config /config/config.yaml`, valid YAML, and a managed identity with required RBAC roles
- **THEN** it ensures the sync-state table exists, connects to the pre-provisioned queue, and begins receiving messages

#### Scenario: Local run with default config path
- **WHEN** a developer runs `worker run` without `--config`
- **THEN** the worker loads `data/config.yaml` and authenticates via `az login` (or configured dev principal)

#### Scenario: Local run with env override
- **WHEN** `data/config.yaml` exists and `SERVICEBUS_QUEUE_NAME` overrides the file value
- **THEN** the worker uses the env value for the queue name

#### Scenario: Missing config file
- **WHEN** `--config` points to a path that does not exist
- **THEN** the worker exits with a non-zero status and a clear error message

#### Scenario: Missing required setting after merge
- **WHEN** `serviceBus.fullyQualifiedNamespace` is absent in both config and env after merge
- **THEN** the worker exits with a non-zero status and a clear error message

### Requirement: Existing queue reference only
The worker MUST consume from a pre-provisioned Service Bus queue. The worker MUST NOT create, alter, or delete Service Bus queues or namespaces.

#### Scenario: Queue consumption
- **WHEN** transport messages are available on the configured queue
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

GitHub messages MUST be identified by webhook JSON shape (top-level `repository` and `action`).

Unrecognized or invalid JSON MUST dead-letter with reason `InvalidMessage`.

#### Scenario: Valid ADO Event Grid message
- **WHEN** the worker receives Event Grid JSON with `subject: AzureDevOps/Auditing` and a valid audit object in `data`
- **THEN** it parses the message as ADO and extracts the audit record from `data`

#### Scenario: Valid ADO message by eventType only
- **WHEN** the worker receives Event Grid JSON with `eventType: AzureDevOpsAuditEvent` and a valid audit object in `data`
- **THEN** it parses the message as ADO and extracts the audit record from `data`

#### Scenario: Valid GitHub webhook message
- **WHEN** the worker receives raw webhook JSON with `repository` and `action` fields
- **THEN** it parses the message as GitHub

#### Scenario: Malformed queue message
- **WHEN** the worker receives a message that is not valid JSON, is not a JSON object, or matches no supported provider shape
- **THEN** it dead-letters the message with reason `InvalidMessage`

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

### Requirement: Operator Azure Container App deployment documentation
Operator documentation MUST describe deploying the worker as an Azure Container App with: managed identity, RBAC roles for Service Bus and Table Storage, config file mount at `/config/config.yaml`, secret injection for `SNYK_TOKEN` and `ADO_PAT`, and optional KEDA Service Bus scaling for replica count based on queue depth. Documentation MUST NOT document Container App Job deployment.

Operator documentation MUST reference the canonical container image **`ghcr.io/snyk-ps/snyk-repo-sync:<version>`** (where `<version>` is the release tag, e.g. `v0.1.0`).

README.md MUST place the **Deployment** section before local development / installation instructions so operators see production guidance first.

#### Scenario: Operator deploys worker to Azure
- **WHEN** an operator follows README deployment guidance after completing INGESTION.md queue setup
- **THEN** they can configure a Container App with identity, secrets, config mount, queue connection settings, and the GHCR image `ghcr.io/snyk-ps/snyk-repo-sync:<version>` without reading application source code

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


## Purpose

Queue-driven worker that normalizes provider events, validates state, routes repo lifecycle events by source, enforces idempotency, and handles retries and dead-lettering. Event normalization is owned by the worker application in this repository so lifecycle mapping ships with worker releases rather than customer-owned ingress infrastructure.
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
For each normalized event, the worker MUST: route by `source` to load the correct `_meta` partition; read repository state (if applicable); perform idempotency check; execute the mapped action; update repository state; complete or dead-letter the message.

#### Scenario: Successful ADO repo create
- **WHEN** a repo-created event with `source: "ado"` passes idempotency checks
- **THEN** the worker imports and tags the target, updates repo state, and completes the message

#### Scenario: Successful GitHub repo create
- **WHEN** a repo-created event with `source: "github"` passes idempotency checks
- **THEN** the worker imports and tags the target, updates repo state, and completes the message

### Requirement: Idempotency by event and desired state
The worker MUST skip duplicate processing when `lastEventId` matches the incoming `eventId` or when `desiredStateHash` already reflects the intended outcome.

#### Scenario: Duplicate delivery
- **WHEN** the same `eventId` is delivered twice for a repository row
- **THEN** the worker completes the message without repeating Snyk side effects

### Requirement: Unknown scope handling
When an event references a scope (ADO project or GitHub org) with no `_meta` row, the worker MUST dead-letter the message and emit an alert.

#### Scenario: Missing ADO project metadata
- **WHEN** a message arrives for an unknown ADO `scopeId`
- **THEN** the message is sent to the DLQ and an alert is raised in Dynatrace

#### Scenario: Missing GitHub org metadata
- **WHEN** a message arrives for an unknown GitHub `scopeId`
- **THEN** the message is sent to the DLQ and an alert is raised in Dynatrace

### Requirement: Unrecoverable failure handling
On unrecoverable processing failure, the worker MUST dead-letter the message and emit an alert.

#### Scenario: Snyk import permanently fails
- **WHEN** import fails after retries/backoff with a non-transient error
- **THEN** the message is dead-lettered and an alert is raised

### Requirement: Rate limit backoff
The worker MUST apply exponential backoff when Snyk or upstream provider APIs (ADO or GitHub) return rate-limit responses.

#### Scenario: Snyk rate limit
- **WHEN** the Snyk API returns a rate-limit response during import
- **THEN** the worker retries with exponential backoff before succeeding or failing unrecoverably

### Requirement: Import job polling with concurrency limits
When an import is initiated, the worker MUST poll the import job status with exponential backoff and MUST respect configured concurrency limits for in-flight import jobs.

#### Scenario: Import in progress
- **WHEN** Snyk returns an in-progress import job
- **THEN** the worker polls until completion, failure, or unrecoverable timeout

### Requirement: Ignored repo short-circuit
Before executing repo lifecycle actions, the worker MUST evaluate ignore policy (list + regex) and MUST NOT import repos that match.

#### Scenario: Ignored repo created
- **WHEN** a repo-created event matches the ignore policy
- **THEN** the worker completes the message without import or tag actions

### Requirement: Manifest changes are out of scope
The worker MUST NOT act on within-repo manifest or file changes; Repo Content Sync handles those after import.

#### Scenario: Manifest change event
- **WHEN** a manifest or file change event is received (if any)
- **THEN** the worker ignores it or does not subscribe to such events

### Requirement: Environment-driven worker startup
The worker MUST read Service Bus connection settings from environment variables injected by the Container App. It MUST NOT require a configuration file. It MUST fail fast at startup when required environment variables are missing.

#### Scenario: Worker starts with valid environment
- **WHEN** the worker container starts with Service Bus connection settings in the environment
- **THEN** it connects to the configured queue and begins receiving messages

#### Scenario: Missing Service Bus environment
- **WHEN** a required Service Bus environment variable is not set at startup
- **THEN** the worker exits with a non-zero status and a clear error message

### Requirement: Existing queue reference only
The worker MUST consume from a pre-provisioned Service Bus queue. This change MUST NOT create, alter, or delete Service Bus queues or namespaces.

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

### Requirement: Slice-2 ADO normalization without sync
In this implementation slice, after successful native queue message parsing the worker MUST normalize supported ADO audit lifecycle events into the normalized model, emit structured logs for the normalized event (including `event_type`, `scope_id`, `repository_id`, `event_id`, and ADO org/project context), and complete the message without sync state access or Snyk side effects.

GitHub queue messages MUST be completed without normalization or sync side effects until GitHub normalization is implemented.

#### Scenario: Valid ADO message normalized in slice 2
- **WHEN** the worker parses and normalizes a supported ADO Event Grid lifecycle message
- **THEN** it logs normalized org, project, repository, and branch fields as applicable, then completes the message

#### Scenario: Valid GitHub message in slice 2
- **WHEN** the worker parses a valid GitHub webhook queue message
- **THEN** it completes the message without normalization or sync actions

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


## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Transport envelope deserialization
**Reason:** Queue messages are provider-native JSON; transport envelope removed.
**Migration:** Worker uses native queue message parsing requirement instead.

## ADDED Requirements

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

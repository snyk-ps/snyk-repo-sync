## MODIFIED Requirements

### Requirement: Multi-source event normalization
The worker MUST parse transport messages and produce a normalized internal lifecycle event model before sync state access or lifecycle actions. Lifecycle normalization MUST be implemented in the worker application in this repository, not in customer-owned ingress infrastructure.

The normalized model MUST include:

| Field | Type | ADO source | GitHub source (future) |
| ----- | ---- | ---------- | ---------------------- |
| `source` | `"ado"` \| `"github"` | transport `source` | transport `source` |
| `eventId` | string | audit `Id` | delivery GUID (`ingressId`) |
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
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryCreated` and required scope, project, and repository fields
- **THEN** it produces a normalized event with `eventType: repo.created`, populated `ado` org and project fields, `repository.name`, and optional `payload.defaultBranch`

#### Scenario: ADO audit stream normalized to repo renamed
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryRenamed` and required fields including `Data.PreviousRepoName`
- **THEN** it produces a normalized event with `eventType: repo.renamed`, populated `ado` org and project fields, `repository.name`, and `payload.previousRepoName`

#### Scenario: ADO audit stream normalized to repo deleted
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryDeleted` and required scope, project, and repository fields
- **THEN** it produces a normalized event with `eventType: repo.deleted`, populated `ado` org and project fields, and `repository.name`

#### Scenario: ADO audit stream normalized to default branch changed
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryDefaultBranchChanged` and required scope, project, repository, and branch fields
- **THEN** it produces a normalized event with `eventType: repo.default_branch_changed`, populated `ado` org and project fields, `repository.name`, and `payload.defaultBranch` / `payload.previousDefaultBranch` without `refs/heads/` prefixes

#### Scenario: GitHub webhook normalized to repo renamed
- **WHEN** the worker receives a transport message with `source: "github"` containing a `repository` webhook with action `renamed`
- **THEN** it produces a normalized event with `eventType: repo.renamed` before further processing

#### Scenario: Unrecognized or unsupported provider payload
- **WHEN** the worker receives an ADO transport message with an unsupported audit `ActionId` or missing required audit/`Data` fields
- **THEN** it dead-letters the message with reason `InvalidNormalization`

#### Scenario: GitHub transport before normalization implementation
- **WHEN** the worker receives a valid GitHub transport envelope before GitHub normalization is implemented
- **THEN** it completes the message without normalization or sync side effects

## REMOVED Requirements

### Requirement: Slice-1 completion without normalization
**Reason:** Superseded by slice-2 ADO normalization behavior.
**Migration:** Worker normalizes ADO audit lifecycle events after envelope validation; GitHub messages complete without normalization until a follow-up change.

## ADDED Requirements

### Requirement: Slice-2 ADO normalization without sync
In this implementation slice, after successful transport envelope validation the worker MUST normalize supported ADO audit lifecycle events into the normalized model, emit structured logs for the normalized event (including `event_type`, `scope_id`, `repository_id`, `event_id`, and ADO org/project context), and complete the message without sync state access or Snyk side effects.

GitHub transport messages MUST be completed without normalization or sync side effects until GitHub normalization is implemented.

#### Scenario: Valid ADO envelope normalized in slice 2
- **WHEN** the worker validates and normalizes a supported ADO audit lifecycle envelope
- **THEN** it logs normalized org, project, repository, and branch fields as applicable, then completes the message

#### Scenario: Valid GitHub envelope in slice 2
- **WHEN** the worker validates a GitHub transport envelope
- **THEN** it completes the message without normalization or sync actions

## MODIFIED Requirements

### Requirement: Multi-source event normalization
The worker MUST parse native queue messages and produce a normalized internal lifecycle event model before sync state access or lifecycle actions. Lifecycle normalization MUST be implemented in the worker application in this repository, not in customer-owned ingress infrastructure.

The worker MUST infer `source` from message structure:

| Detected source | Identification rule |
| --------------- | ------------------- |
| `"ado"` | `eventType` is `AzureDevOpsAuditEvent` **or** `subject` is `AzureDevOps/Auditing` |
| `"github"` | Top-level JSON with `repository` object and string `action` (when not ADO) |

For ADO, the audit record MUST be read from Event Grid `data`. For GitHub, the queue message body is the full GitHub payload (raw webhook or parsed contract).

GitHub messages MUST be classified by shape:

| Shape | Detection |
| ----- | --------- |
| Parsed contract | Non-empty string top-level `deliveryId` |
| Raw webhook | Otherwise |

The normalized model MUST include:

| Field | Type | ADO source | GitHub source |
| ----- | ---- | ---------- | ------------- |
| `source` | `"ado"` \| `"github"` | inferred | inferred |
| `eventId` | string | audit `Id` in `data` | parsed: `deliveryId`; raw: delivery id from message metadata when available |
| `eventType` | lifecycle enum | audit `ActionId` | webhook `action` (see GitHub mapping) |
| `scopeId` | string | `ProjectId` | org login (`repository.owner.login`) |
| `repositoryId` | string | `Data.RepoId` | `repository.id` (string) |
| `occurredAt` | datetime UTC | audit `Timestamp` | raw: `repository.updated_at`; parsed: `repository.updatedAt` |
| `ado` | object | ADO scope table | absent |
| `github` | object | absent | see GitHub scope table |
| `repository` | object | `name` ← `Data.RepoName` | `name` ← `repository.name` |
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
| `orgLogin` | `repository.owner.login` (MUST equal `scopeId`) |

The `ado` object MUST be absent when `source` is `"github"`. The `github` object MUST be absent when `source` is `"ado"`.

ADO audit `ActionId` mapping:

| `ActionId` | `eventType` |
| -------- | ----------- |
| `Git.RepositoryCreated` | `repo.created` |
| `Git.RepositoryRenamed` | `repo.renamed` |
| `Git.RepositoryDeleted` | `repo.deleted` |
| `Git.RepositoryDefaultBranchChanged` | `repo.default_branch_changed` |

GitHub webhook `action` mapping:

| `action` | `eventType` | Conditions |
| -------- | ----------- | ---------- |
| `created` | `repo.created` | — |
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

GitHub repositories with `repository.owner.type` other than `Organization` MUST complete without normalization error and without lifecycle sync.

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
- **WHEN** a repo-created event with `source: "github"` passes idempotency checks and scope mapping resolves a Snyk org by org login
- **THEN** the worker triggers import, upserts pending repository state, schedules import job polling if needed, and completes or dead-letters the message per retry policy

### Requirement: Native queue message parsing
The worker MUST deserialize inbound queue messages as JSON and identify the provider source from message structure. ADO messages MUST be identified when `eventType` is `AzureDevOpsAuditEvent` **or** `subject` is `AzureDevOps/Auditing`; the audit record MUST be extracted from `data`.

GitHub messages MUST be identified by JSON shape (top-level `repository` and `action`). Parsed GitHub contract messages MUST be recognized when `deliveryId` is present.

Unrecognized or invalid JSON MUST dead-letter with reason `InvalidMessage`.

#### Scenario: Valid ADO Event Grid message
- **WHEN** the worker receives Event Grid JSON with `subject: AzureDevOps/Auditing` and a valid audit object in `data`
- **THEN** it parses the message as ADO and extracts the audit record from `data`

#### Scenario: Valid ADO message by eventType only
- **WHEN** the worker receives Event Grid JSON with `eventType: AzureDevOpsAuditEvent` and a valid audit object in `data`
- **THEN** it parses the message as ADO and extracts the audit record from `data`

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

The worker MUST read and write repository sync state, call the Snyk API, and route internal follow-up messages on the same queue.

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

## REMOVED Requirements

### Requirement: GitHub queue pass-through before normalization
**Reason:** GitHub normalization and lifecycle sync are implemented in this change.
**Migration:** Replace expectations that valid GitHub webhook messages complete without normalization or sync side effects with GitHub raw/parsed normalization and mapped-org lifecycle scenarios in this change.

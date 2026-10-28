## MODIFIED Requirements

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

### Requirement: Custom property updated imports the GitHub repository
The worker MUST normalize the parsed updated body in `data/fixtures/github_parsed_updated.json` to `repo.created` and MUST run the existing GitHub create flow for that event. This body is the import signal for the parsed updated contract. The worker MUST NOT require a GitHub `action: created` body before importing.

The worker MUST NOT deactivate or delete an Azure DevOps Snyk target because a GitHub updated event imported the repository. It MUST NOT persist a link from the GitHub repository to an ADO project or ADO target.

#### Scenario: Updated body imports the GitHub repository
- **WHEN** the worker receives `data/fixtures/github_parsed_updated.json` and scope mapping resolves a Snyk org
- **THEN** it runs the GitHub `repo.created` import path for that body's `repository`

#### Scenario: Updated import leaves ADO targets in place
- **WHEN** the GitHub updated event imports a repository whose `azure-devops-project` value names an ADO project that already has a Snyk target
- **THEN** the worker does not deactivate or delete that ADO target

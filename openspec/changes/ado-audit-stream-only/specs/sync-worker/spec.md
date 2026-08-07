## MODIFIED Requirements

### Requirement: Multi-source event normalization
The worker MUST parse transport messages from ADO and GitHub and produce a normalized internal event model before state access or lifecycle actions. The normalized model MUST include: `source`, `eventId`, `eventType`, `scopeId`, `repositoryId` (when applicable), `occurredAt`, and event-specific `payload` fields required by downstream handlers. Lifecycle normalization MUST be implemented in the worker application in this repository, not in customer-owned ingress infrastructure.

| Field          | ADO                  | GitHub                 |
| -------------- | -------------------- | ---------------------- |
| `source`       | `"ado"`              | `"github"`             |
| `eventId`      | audit record `Id`    | GitHub delivery GUID   |
| `eventType`    | `repo.created`, etc. | same lifecycle types   |
| `scopeId`      | ADO project ID       | GitHub org ID          |
| `repositoryId` | ADO repository ID    | GitHub repo ID (numeric) |
| `occurredAt`   | audit `Timestamp`    | webhook timestamp      |
| `payload`      | ADO audit extras     | repo name, default branch, etc. |

#### Scenario: ADO audit stream normalized to repo created
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryCreated`
- **THEN** it produces a normalized event with `eventType: repo.created` before further processing

#### Scenario: ADO audit stream normalized to repo renamed
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryRenamed`
- **THEN** it produces a normalized event with `eventType: repo.renamed` before further processing

#### Scenario: ADO audit stream normalized to repo deleted
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryDeleted`
- **THEN** it produces a normalized event with `eventType: repo.deleted` before further processing

#### Scenario: ADO audit stream normalized to default branch changed
- **WHEN** the worker receives a transport message with `source: "ado"` containing an audit payload with `ActionId: Git.RepositoryDefaultBranchChanged`
- **THEN** it produces a normalized event with `eventType: repo.default_branch_changed` before further processing

#### Scenario: GitHub webhook normalized to repo renamed
- **WHEN** the worker receives a transport message with `source: "github"` containing a `repository` webhook with action `renamed`
- **THEN** it produces a normalized event with `eventType: repo.renamed` before further processing

#### Scenario: Unrecognized or unsupported provider payload
- **WHEN** the worker cannot parse a transport message or the event is not a supported repository lifecycle change
- **THEN** it completes the message without lifecycle side effects or dead-letters the message when parsing is unrecoverably invalid

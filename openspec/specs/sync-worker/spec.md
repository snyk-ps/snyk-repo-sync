## Purpose

Queue-driven worker that normalizes provider events, validates state, routes repo lifecycle events by source, enforces idempotency, and handles retries and dead-lettering. Event normalization is owned by this PS-maintained application so lifecycle mapping ships with worker releases rather than customer-owned ingress infrastructure.

## Requirements

### Requirement: Queue-driven processing
The worker MUST consume messages from the Service Bus queue on demand; it MUST NOT rely on always-on polling of ADO, GitHub, or Snyk as its primary trigger.

#### Scenario: Message available
- **WHEN** a transport message is available on the queue
- **THEN** the worker receives and processes it

### Requirement: Multi-source event normalization
The worker MUST parse transport messages from ADO and GitHub and produce a normalized internal event model before state access or lifecycle actions. The normalized model MUST include: `source`, `eventId`, `eventType`, `scopeId`, `repositoryId` (when applicable), `occurredAt`, and event-specific `payload` fields required by downstream handlers.

| Field          | ADO                  | GitHub                 |
| -------------- | -------------------- | ---------------------- |
| `source`       | `"ado"`              | `"github"`             |
| `eventId`      | hook or audit id     | GitHub delivery GUID   |
| `eventType`    | `repo.created`, etc. | same lifecycle types   |
| `scopeId`      | ADO project ID       | GitHub org ID          |
| `repositoryId` | ADO repository ID    | GitHub repo ID (numeric) |
| `occurredAt`   | event timestamp      | webhook timestamp      |
| `payload`      | ADO-specific extras  | repo name, default branch, etc. |

#### Scenario: ADO service hook normalized to repo created
- **WHEN** the worker receives a transport message with `source: "ado"` containing a repository-created service hook payload
- **THEN** it produces a normalized event with `eventType: repo.created` before further processing

#### Scenario: ADO audit stream normalized to default branch changed
- **WHEN** the worker receives a transport message with `source: "ado"` containing a default-branch audit payload
- **THEN** it produces a normalized event with `eventType: repo.default_branch_changed` before further processing

#### Scenario: GitHub webhook normalized to repo renamed
- **WHEN** the worker receives a transport message with `source: "github"` containing a `repository` webhook with action `renamed`
- **THEN** it produces a normalized event with `eventType: repo.renamed` before further processing

#### Scenario: Unrecognized or unsupported provider payload
- **WHEN** the worker cannot parse a transport message or the event is not a supported repository lifecycle change
- **THEN** it completes the message without lifecycle side effects or dead-letters the message when parsing is unrecoverably invalid

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

## Purpose

Ingest ADO service hook and audit stream events and publish normalized messages to a single Service Bus queue shared with GitHub webhook ingress.

## Requirements

### Requirement: Multi-source normalized envelope
All ingress paths (ADO and GitHub) MUST publish to one Service Bus queue using a normalized envelope that includes: `source`, `eventId`, `eventType`, `scopeId`, `repositoryId` (when applicable), `occurredAt`, and event-specific `payload` fields required by downstream handlers.

| Field          | ADO                  | GitHub                 |
| -------------- | -------------------- | ---------------------- |
| `source`       | `"ado"`              | `"github"`             |
| `eventId`      | hook or audit id     | GitHub delivery GUID   |
| `eventType`    | `repo.created`, etc. | same lifecycle types   |
| `scopeId`      | ADO project ID       | GitHub org ID          |
| `repositoryId` | ADO repository ID    | GitHub repo ID (numeric) |
| `occurredAt`   | event timestamp      | webhook timestamp      |
| `payload`      | ADO-specific extras  | repo name, default branch, etc. |

#### Scenario: ADO service hook repo lifecycle event
- **WHEN** ADO emits a service hook for repository created, renamed, or deleted
- **THEN** the ingress path publishes one normalized message with `source: "ado"` to the Service Bus queue

#### Scenario: Audit stream default branch event
- **WHEN** ADO audit stream reports a repository default branch change
- **THEN** Event Grid (audit subscriber) publishes one normalized message with `source: "ado"` to the same Service Bus queue

#### Scenario: GitHub webhook lifecycle event
- **WHEN** a GitHub repository lifecycle webhook is normalized by github-webhook-ingestion
- **THEN** the message includes `source: "github"` and GitHub org/repository IDs in the shared envelope

### Requirement: Cloud ADO only
ADO event ingestion MUST support Azure DevOps Cloud (`dev.azure.com`) only.

#### Scenario: On-premises ADO event
- **WHEN** an event originates from ADO Server (on-premises)
- **THEN** the system does not ingest or process it (out of scope)

### Requirement: Optional audit normalizer
When an audit-stream normalizer function is deployed, it MUST transform raw audit payloads into the normalized envelope before queue publish.

#### Scenario: Normalizer present
- **WHEN** a default-branch audit event passes through the normalizer
- **THEN** the message on the queue conforms to the same envelope schema as service hook messages

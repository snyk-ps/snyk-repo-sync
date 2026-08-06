## Purpose

Deliver ADO service hook and audit stream events to a single Service Bus queue shared with GitHub webhook ingress. Ingress is customer-owned infrastructure; it validates and forwards provider-native payloads without lifecycle normalization.

## Requirements

### Requirement: Multi-source transport envelope
All ingress paths (ADO and GitHub) MUST publish to one Service Bus queue using a transport envelope that includes: `source`, `ingressId`, `receivedAt`, and `rawPayload` (the provider-native event body). Ingress MUST NOT perform lifecycle normalization; that is owned by the PS-maintained worker application.

| Field         | ADO                              | GitHub                          |
| ------------- | -------------------------------- | ------------------------------- |
| `source`      | `"ado"`                          | `"github"`                      |
| `ingressId`   | service hook or audit event id   | `X-GitHub-Delivery` GUID        |
| `receivedAt`  | ingress receive timestamp        | ingress receive timestamp       |
| `rawPayload`  | ADO service hook or audit body   | GitHub webhook JSON body        |

#### Scenario: ADO service hook repo lifecycle event
- **WHEN** ADO emits a service hook for repository created, renamed, or deleted
- **THEN** the ingress path publishes one transport message with `source: "ado"` and the raw hook payload to the Service Bus queue

#### Scenario: Audit stream default branch event
- **WHEN** ADO audit stream reports a repository default branch change
- **THEN** Event Grid forwards one transport message with `source: "ado"` and the raw audit payload to the same Service Bus queue

#### Scenario: GitHub webhook lifecycle event
- **WHEN** GitHub delivers a repository lifecycle webhook accepted by github-webhook-ingestion
- **THEN** the message includes `source: "github"`, the delivery GUID as `ingressId`, and the raw webhook body in `rawPayload`

### Requirement: Cloud ADO only
ADO event ingestion MUST support Azure DevOps Cloud (`dev.azure.com`) only.

#### Scenario: On-premises ADO event
- **WHEN** an event originates from ADO Server (on-premises)
- **THEN** the system does not ingest or process it (out of scope)

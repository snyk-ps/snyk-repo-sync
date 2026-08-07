## MODIFIED Requirements

### Requirement: Multi-source transport envelope
All ingress paths (ADO and GitHub) MUST publish to one Service Bus queue using a transport envelope that includes: `source`, `ingressId`, `receivedAt`, and `rawPayload` (the provider-native event body). Ingress MUST NOT perform lifecycle normalization; that is owned by the worker application in this repository.

| Field         | ADO                              | GitHub                          |
| ------------- | -------------------------------- | ------------------------------- |
| `source`      | `"ado"`                          | `"github"`                      |
| `ingressId`   | audit event `Id`                 | `X-GitHub-Delivery` GUID        |
| `receivedAt`  | ingress receive timestamp        | ingress receive timestamp       |
| `rawPayload`  | ADO audit record body            | GitHub webhook JSON body        |

#### Scenario: ADO audit stream repo lifecycle event
- **WHEN** ADO audit stream reports a Git repository created, renamed, deleted, or default-branch-changed event
- **THEN** the ingress path publishes one transport message with `source: "ado"` and the raw audit record in `rawPayload` to the Service Bus queue

#### Scenario: Audit stream default branch event
- **WHEN** ADO audit stream reports a repository default branch change
- **THEN** Event Grid forwards one transport message with `source: "ado"` and the raw audit payload to the same Service Bus queue

#### Scenario: GitHub webhook lifecycle event
- **WHEN** GitHub delivers a repository lifecycle webhook accepted by github-webhook-ingestion
- **THEN** the message includes `source: "github"`, the delivery GUID as `ingressId`, and the raw webhook body in `rawPayload`

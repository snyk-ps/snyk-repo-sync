## MODIFIED Requirements

### Requirement: Raw payload publish
GitHub webhooks MUST be published to the same Service Bus queue using the shared transport envelope with `source: "github"`, `ingressId` set to the delivery GUID, `receivedAt`, and the provider-native webhook body in `rawPayload`. Lifecycle normalization MUST be performed by the worker application in this repository, not by customer-owned ingress infrastructure.

#### Scenario: Repository lifecycle webhook accepted
- **WHEN** GitHub delivers a signed `repository` webhook
- **THEN** one transport message containing the raw webhook body is published to the queue

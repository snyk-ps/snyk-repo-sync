## MODIFIED Requirements

### Requirement: Raw payload publish
GitHub webhooks MUST be published to the same Service Bus queue as the raw webhook JSON body after signature validation and delivery deduplication. Lifecycle normalization MUST be performed by the worker application in this repository, not by customer-owned ingress infrastructure.

#### Scenario: Repository lifecycle webhook accepted
- **WHEN** GitHub delivers a signed `repository` webhook
- **THEN** one queue message containing the raw webhook JSON body is published to the queue

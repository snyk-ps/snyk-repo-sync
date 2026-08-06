## ADDED Requirements

### Requirement: Worker-side transport consumption
The worker application MUST consume transport messages from the same Service Bus queue that external ingress paths publish to. The worker MUST deserialize messages using the transport envelope schema (`source`, `ingressId`, `receivedAt`, `rawPayload`).

#### Scenario: Worker receives published transport message
- **WHEN** an external ingress path publishes a transport message to the queue
- **THEN** the worker container can receive and deserialize that message

### Requirement: Existing queue only
Queue infrastructure MUST be provisioned outside this repository. The worker MUST reference the existing queue via environment configuration and MUST NOT create or manage Service Bus resources.

#### Scenario: No queue provisioning in worker
- **WHEN** the worker application is deployed
- **THEN** it connects to the pre-existing queue without creating queue infrastructure

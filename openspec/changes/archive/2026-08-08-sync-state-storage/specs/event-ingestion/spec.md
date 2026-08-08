## MODIFIED Requirements

### Requirement: Existing queue only
Queue infrastructure MUST be provisioned outside this repository. The worker MUST reference the existing queue via operator configuration and MUST authenticate with `DefaultAzureCredential`. The worker MUST NOT create, alter, or delete Service Bus queues or namespaces. The worker MUST NOT use connection strings or shared access signatures for Service Bus.

Queue connection settings (`fullyQualifiedNamespace`, `queueName`) MUST be readable from operator config and MAY be overridden by environment variables (`SERVICEBUS_FULLY_QUALIFIED_NAMESPACE`, `SERVICEBUS_QUEUE_NAME`); env values MUST take precedence when set.

#### Scenario: Pre-provisioned queue only
- **WHEN** the worker starts with valid config and RBAC
- **THEN** it connects to the existing queue without creating or modifying queue infrastructure

#### Scenario: RBAC data-plane access
- **WHEN** the worker identity has Azure Service Bus Data Owner (or equivalent send and receive data roles) on the namespace or queue
- **THEN** it can receive, settle, and send messages without connection string secrets

#### Scenario: Missing queue settings after config/env merge
- **WHEN** required Service Bus settings are absent in both config and env after merge
- **THEN** the worker exits at startup with a clear error

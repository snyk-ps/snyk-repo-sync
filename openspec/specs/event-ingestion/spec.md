## Purpose

Deliver ADO audit stream and GitHub webhook events to a single Service Bus queue shared with GitHub webhook ingress. Ingress is customer-owned infrastructure; it validates and forwards provider-native payloads without lifecycle normalization.
## Requirements
### Requirement: Cloud ADO only
ADO event ingestion MUST support Azure DevOps Cloud (`dev.azure.com`) only.

#### Scenario: On-premises ADO event
- **WHEN** an event originates from ADO Server (on-premises)
- **THEN** the system does not ingest or process it (out of scope)

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

### Requirement: Native queue message contract
All messages on the shared Service Bus queue MUST be provider-native JSON bodies. The worker MUST NOT require `source`, `ingressId`, `receivedAt`, or `rawPayload` wrapper fields.

ADO messages MUST be Event Grid schema JSON delivered from an Event Grid subscription to Service Bus. The audit record MUST appear in the `data` property.

GitHub messages MUST be the raw signed webhook JSON body published after signature validation and delivery deduplication.

#### Scenario: ADO Event Grid message on queue
- **WHEN** Event Grid delivers an ADO audit event to Service Bus after subscription filtering
- **THEN** the queue message body is Event Grid JSON with audit fields under `data`

#### Scenario: GitHub webhook message on queue
- **WHEN** GitHub webhook ingress accepts a signed repository lifecycle webhook
- **THEN** the queue message body is the raw webhook JSON without a transport envelope wrapper

### Requirement: ADO Event Grid subscription filters
ADO Event Grid subscriptions that forward to Service Bus MUST use advanced filters on `subject` and `data.ActionId`. Operators MUST configure:

| Filter | Key | Operator | Values |
| ------ | --- | -------- | ------ |
| Subject | `subject` | String in | `AzureDevOps/Auditing` |
| Lifecycle | `data.ActionId` | String in | `Git.RepositoryCreated`, `Git.RepositoryRenamed`, `Git.RepositoryDeleted`, `Git.RepositoryDefaultBranchChanged` |

#### Scenario: Subscription filters configured
- **WHEN** an operator configures the Event Grid subscription per INGESTION.md
- **THEN** only auditing-subject and supported Git lifecycle audit events are delivered to Service Bus

### Requirement: Worker-side native queue consumption
The worker application MUST consume messages from the same Service Bus queue. The worker MUST parse native queue message bodies and infer `source` from message structure before normalization.

#### Scenario: Worker receives Event Grid message
- **WHEN** an Event Grid JSON message is available on the queue
- **THEN** the worker parses the audit record from `data` and processes it as an ADO message


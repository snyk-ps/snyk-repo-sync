## REMOVED Requirements

### Requirement: Multi-source transport envelope
**Reason:** Queue messages are provider-native Event Grid JSON (ADO) and raw webhook JSON (GitHub); transport envelope wrapper removed.
**Migration:** Worker parses message shape directly; ingress publishes native bodies only.

### Requirement: Worker-side transport consumption
**Reason:** Superseded by native queue message consumption.
**Migration:** Worker deserializes Event Grid or webhook JSON per native queue message contract.

## ADDED Requirements

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

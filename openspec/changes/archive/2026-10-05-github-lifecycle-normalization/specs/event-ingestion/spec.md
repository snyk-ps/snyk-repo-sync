## MODIFIED Requirements

### Requirement: Native queue message contract
All messages on the shared Service Bus queue MUST be provider-native JSON bodies. The worker MUST NOT require `source`, `ingressId`, `receivedAt`, or `rawPayload` wrapper fields.

ADO messages MUST be Event Grid schema JSON delivered from an Event Grid subscription to Service Bus. The audit record MUST appear in the `data` property.

GitHub messages MUST be one of:

1. **Raw webhook JSON** — the signed GitHub `repository` webhook body published after signature validation and delivery deduplication (snake_case fields per GitHub API).
2. **Parsed repository event JSON** — GitHubHooks output for repository lifecycle (top-level `deliveryId`, `action`, camelCase `repository`, optional `changes`, and `sender`) consumed from the same queue when bridged from Kafka or equivalent ingress.

#### Scenario: ADO Event Grid message on queue
- **WHEN** Event Grid delivers an ADO audit event to Service Bus after subscription filtering
- **THEN** the queue message body is Event Grid JSON with audit fields under `data`

#### Scenario: GitHub raw webhook message on queue
- **WHEN** GitHub webhook ingress accepts a signed repository lifecycle webhook
- **THEN** the queue message body is the raw webhook JSON without a transport envelope wrapper

#### Scenario: GitHub parsed repository event on queue
- **WHEN** ingress publishes a GitHubHooks parsed repository event with `deliveryId` and `action`
- **THEN** the queue message body is that JSON object without a transport envelope wrapper

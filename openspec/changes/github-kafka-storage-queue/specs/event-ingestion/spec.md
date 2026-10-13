## ADDED Requirements

### Requirement: Kafka event-connector ingress
Deployments MAY ingest GitHub repository lifecycle events from a Kafka topic through an event connector REST API over HTTP. This path is consumption only. The worker MUST NOT publish GitHub events or internal follow-up messages to Kafka.

On this path the message body, once the connector delivers it, MUST be the same GitHub JSON the Service Bus path already accepts (raw webhook JSON or parsed repository event JSON). The worker MUST NOT require a transport envelope.

The HTTP client MUST NOT be implemented in this change. The worker MUST NOT invent a base URL, authentication scheme, poll interval, or ack format. When `messaging.transport` is `kafka`, the worker MUST exit at startup with a clear error that the event-connector REST contract is pending. It MUST NOT fall back to Service Bus.

ADO audit events MUST NOT use this path. They remain on the Service Bus path described by the existing requirements.

#### Scenario: Kafka transport selected before the connector exists
- **WHEN** the worker starts with `messaging.transport: kafka`
- **THEN** it exits with a non-zero status and a clear error that the event-connector REST API is not implemented

#### Scenario: Follow-up is not written to Kafka
- **WHEN** a GitHub event has been handled and an `import_poll` follow-up is required on the `kafka` transport
- **THEN** the follow-up is scheduled on the storage queue in the sync-state storage account and is not published to Kafka

## MODIFIED Requirements

### Requirement: Native queue message contract
All messages on the shared Service Bus queue MUST be provider-native JSON bodies. The worker MUST NOT require `source`, `ingressId`, `receivedAt`, or `rawPayload` wrapper fields.

ADO messages MUST be Event Grid schema JSON delivered from an Event Grid subscription to Service Bus. The audit record MUST appear in the `data` property.

GitHub messages MUST be one of:

1. **Raw webhook JSON** — the signed GitHub `repository` webhook body published after signature validation and delivery deduplication (snake_case fields per GitHub API).
2. **Parsed repository event JSON** — GitHubHooks output for repository lifecycle (top-level `deliveryId`, `action`, camelCase `repository`, optional `changes`, and `sender`).

On the Service Bus path (`messaging.transport` omitted or `serviceBus`), both GitHub shapes are consumed from that Service Bus queue, including when an operator bridges a Kafka topic onto the queue. On the Kafka path (`messaging.transport: kafka`), those same JSON shapes are consumed from the event connector and MUST NOT be required to appear on Service Bus.

#### Scenario: ADO Event Grid message on queue
- **WHEN** Event Grid delivers an ADO audit event to Service Bus after subscription filtering
- **THEN** the queue message body is Event Grid JSON with audit fields under `data`

#### Scenario: GitHub raw webhook message on queue
- **WHEN** GitHub webhook ingress accepts a signed repository lifecycle webhook on the Service Bus path
- **THEN** the queue message body is the raw webhook JSON without a transport envelope wrapper

#### Scenario: GitHub parsed repository event on queue
- **WHEN** ingress publishes a GitHubHooks parsed repository event with `deliveryId` and `action` on the Service Bus path
- **THEN** the queue message body is that JSON object without a transport envelope wrapper

#### Scenario: GitHub event consumed from the connector
- **WHEN** the Kafka path delivers a parsed repository event or raw webhook body from the event connector
- **THEN** the worker normalizes that JSON body and does not require a copy of it on Service Bus

### Requirement: Worker-side native queue consumption
On the Service Bus path, the worker application MUST consume messages from the configured Service Bus queue. The worker MUST parse native queue message bodies and infer `source` from message structure before normalization.

On the Kafka path, the worker MUST consume GitHub event bodies from the event connector (when that client exists) and MUST consume internal follow-ups from the storage queue. It MUST NOT require GitHub events to be present on Service Bus.

#### Scenario: Worker receives Event Grid message
- **WHEN** an Event Grid JSON message is available on the Service Bus queue and `messaging.transport` is `serviceBus`
- **THEN** the worker parses the audit record from `data` and processes it as an ADO message

#### Scenario: Kafka transport does not open Service Bus
- **WHEN** the worker builds the `kafka` transport
- **THEN** it does not construct a Service Bus client, and GitHub event intake is the event-connector source rather than the Service Bus queue

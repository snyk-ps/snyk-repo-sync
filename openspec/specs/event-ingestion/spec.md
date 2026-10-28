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

GitHub messages MUST be one of:

1. **Raw webhook JSON** — the signed GitHub `repository` webhook body published after signature validation and delivery deduplication (snake_case fields per GitHub API).
2. **Parsed repository event JSON** — GitHubHooks output for repository lifecycle (top-level `deliveryId`, `action`, camelCase `repository`, optional `changes`, and `sender`).
3. **Parsed updated JSON** — top-level `deliveryId`, camelCase `repository`, `oldPropertyValues`, `newPropertyValues`, and `sender`, as in `data/fixtures/github_parsed_updated.json`. This body is the GitHub import. `repository` and `newPropertyValues` are top-level fields.

On the Service Bus path (`messaging.transport` omitted or `serviceBus`), these GitHub shapes are consumed from that Service Bus queue, including when an operator bridges a Kafka topic onto the queue. On the Kafka path (`messaging.transport: kafka`), those same JSON shapes are consumed from the event connector and MUST NOT be required to appear on Service Bus.

#### Scenario: ADO Event Grid message on queue
- **WHEN** Event Grid delivers an ADO audit event to Service Bus after subscription filtering
- **THEN** the queue message body is Event Grid JSON with audit fields under `data`

#### Scenario: GitHub raw webhook message on queue
- **WHEN** GitHub webhook ingress accepts a signed repository lifecycle webhook on the Service Bus path
- **THEN** the queue message body is the raw webhook JSON without a transport envelope wrapper

#### Scenario: GitHub parsed repository event on queue
- **WHEN** ingress publishes a GitHubHooks parsed repository event with `deliveryId` and `action` on the Service Bus path
- **THEN** the queue message body is that JSON object without a transport envelope wrapper

#### Scenario: GitHub parsed updated event on queue
- **WHEN** a message body matches `data/fixtures/github_parsed_updated.json`
- **THEN** the worker accepts that JSON as a GitHub message

#### Scenario: GitHub event consumed from the connector
- **WHEN** the Kafka path delivers a parsed repository event, a parsed updated body, or a raw webhook body from the event connector
- **THEN** the worker normalizes that JSON body and does not require a copy of it on Service Bus

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
On the Service Bus path, the worker application MUST consume messages from the configured Service Bus queue. The worker MUST parse native queue message bodies and infer `source` from message structure before normalization.

On the Kafka path, the worker MUST receive GitHub event bodies through connector-pushed HTTP ingress and MUST consume internal follow-ups from the storage queue. It MUST NOT require GitHub events to be present on Service Bus.

#### Scenario: Worker receives Event Grid message
- **WHEN** an Event Grid JSON message is available on the Service Bus queue and `messaging.transport` is `serviceBus`
- **THEN** the worker parses the audit record from `data` and processes it as an ADO message

#### Scenario: Kafka transport does not open Service Bus
- **WHEN** the worker builds the `kafka` transport
- **THEN** it does not construct a Service Bus client, and GitHub event intake is connector-pushed HTTP ingress rather than the Service Bus queue

### Requirement: Kafka event-connector ingress
Deployments MAY ingest GitHub repository lifecycle events from a Kafka topic when an event connector relays them by HTTP POST to the application's `/github-events` endpoint. This path is consumption only. The worker MUST NOT publish GitHub events or internal follow-up messages to Kafka.

On this path the message body MUST be GitHub JSON the Service Bus path accepts: raw webhook JSON, parsed repository event JSON, or the parsed updated JSON in `data/fixtures/github_parsed_updated.json`. Raw webhook and parsed lifecycle bodies MUST NOT add a further transport envelope. The updated body is that JSON object. Its `repository` fields and `newPropertyValues` are top-level.

When `messaging.transport` is `kafka`, the application MUST receive connector-pushed requests rather than poll or pull from the connector. It MUST process requests synchronously and use the acknowledgement behavior defined by the `github-events-http-ingress` capability. It MUST consume internal follow-ups from the Storage queue and MUST NOT open or fall back to Service Bus.

The endpoint MUST require no application-level authentication. Operators MUST provide a customer-managed private route from the event connector and MUST NOT expose the endpoint publicly.

ADO audit events MUST NOT use this path. They remain on the Service Bus path described by the existing requirements.

#### Scenario: Kafka transport receives an existing GitHub shape
- **WHEN** the event connector posts an already-supported parsed repository event or raw webhook body to `/github-events`
- **THEN** the worker processes that JSON body without requiring a copy on Service Bus

#### Scenario: Kafka transport receives parsed updated
- **WHEN** the event connector posts the `github_parsed_updated.json` body to `/github-events`
- **THEN** the worker accepts that body and does not require a copy on Service Bus

#### Scenario: Follow-up is not written to Kafka
- **WHEN** a GitHub event has been handled and an `import_poll` follow-up is required on the `kafka` transport
- **THEN** the follow-up is scheduled on the Storage queue in the sync-state storage account and is not published to Kafka

#### Scenario: Kafka transport does not pull or fall back
- **WHEN** the worker starts with `messaging.transport: kafka`
- **THEN** it starts connector-pushed HTTP ingress and Storage queue follow-up consumption without opening a connector polling client or Service Bus client

#### Scenario: ADO is rejected from connector ingress
- **WHEN** an ADO Event Grid or audit payload is posted to `/github-events`
- **THEN** the request returns non-2xx and no ADO lifecycle processing occurs


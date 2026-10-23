## MODIFIED Requirements

### Requirement: Kafka event-connector ingress
Deployments MAY ingest GitHub repository lifecycle events from a Kafka topic when an event connector relays them by HTTP POST to the application's `/github-events` endpoint. This path is consumption only. The worker MUST NOT publish GitHub events or internal follow-up messages to Kafka.

On this path an already-supported message body MUST be the same GitHub JSON the Service Bus path accepts (raw webhook JSON or parsed repository event JSON), with no transport envelope. Revised connector payload contracts, including `updated` details used for Snyk organization mapping, MUST remain out of scope until a subsequent fixture-driven normalization change.

When `messaging.transport` is `kafka`, the application MUST receive connector-pushed requests rather than poll or pull from the connector. It MUST process requests synchronously and use the acknowledgement behavior defined by the `github-events-http-ingress` capability. It MUST consume internal follow-ups from the Storage queue and MUST NOT open or fall back to Service Bus.

The endpoint MUST require no application-level authentication. Operators MUST provide a customer-managed private route from the event connector and MUST NOT expose the endpoint publicly.

ADO audit events MUST NOT use this path. They remain on the Service Bus path described by the existing requirements.

#### Scenario: Kafka transport receives an existing GitHub shape
- **WHEN** the event connector posts an already-supported parsed repository event or raw webhook body to `/github-events`
- **THEN** the worker processes that JSON body without requiring a copy on Service Bus

#### Scenario: Follow-up is not written to Kafka
- **WHEN** a GitHub event has been handled and an `import_poll` follow-up is required on the `kafka` transport
- **THEN** the follow-up is scheduled on the Storage queue in the sync-state storage account and is not published to Kafka

#### Scenario: Kafka transport does not pull or fall back
- **WHEN** the worker starts with `messaging.transport: kafka`
- **THEN** it starts connector-pushed HTTP ingress and Storage queue follow-up consumption without opening a connector polling client or Service Bus client

#### Scenario: ADO is rejected from connector ingress
- **WHEN** an ADO Event Grid or audit payload is posted to `/github-events`
- **THEN** the request returns non-2xx and no ADO lifecycle processing occurs

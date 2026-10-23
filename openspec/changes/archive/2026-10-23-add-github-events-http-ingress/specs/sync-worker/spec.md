## MODIFIED Requirements

### Requirement: Queue-driven processing
The worker MUST consume messages from the selected transport on demand; it MUST NOT rely on always-on polling of ADO, GitHub, or Snyk as its primary trigger.

On `serviceBus`, provider events and internal follow-ups come from the Service Bus queue. On `kafka`, GitHub events arrive as event-connector POST requests to `/github-events` and internal follow-ups come from the Storage queue.

#### Scenario: Message available
- **WHEN** a Service Bus or Storage queue message is available on the selected transport, or the Kafka event connector posts a GitHub event
- **THEN** the worker receives and processes it

### Requirement: Unrecoverable failure handling
On unrecoverable processing failure, the worker MUST reject or dead-letter the message and emit an alert.

On `serviceBus`, dead-letter MUST use the Service Bus dead-letter queue. On `kafka`, a failed inbound `/github-events` request MUST return non-2xx so the event connector retries it, while a failed internal Storage queue follow-up MUST poison-settle per the `storage-queue-transport` capability. Dead-letter reason strings for queued messages MUST remain the same across queue transports.

Import job polling MUST dead-letter or poison-settle with reason `ImportJobFailed` when `retryCount` reaches 5 on `import_poll` follow-up messages.

#### Scenario: Snyk import permanently fails for HTTP ingress
- **WHEN** initial processing of a `/github-events` request fails with an unrecoverable Snyk error
- **THEN** the endpoint returns non-2xx and an alert is raised

#### Scenario: Snyk import polling permanently fails
- **WHEN** a queued `import_poll` follow-up reaches its retry limit
- **THEN** the message is dead-lettered or poison-settled for the active queue transport and an alert is raised

### Requirement: Selectable message transport
The worker MUST select a message transport from `messaging.transport` in operator config, overridable by `MESSAGING_TRANSPORT`. Allowed values are `serviceBus` and `kafka`. When the key is omitted, the transport MUST be `serviceBus`. Any other value MUST fail startup with a clear configuration error.

On `serviceBus`, GitHub events, ADO events, and internal follow-ups MUST use the configured Service Bus queue, and `serviceBus.fullyQualifiedNamespace` and `serviceBus.queueName` MUST remain required. Storage queue and GitHub events HTTP settings MUST be ignored.

On `kafka`, internal follow-ups MUST use the Storage queue from the `storage-queue-transport` capability, GitHub events MUST use connector-pushed HTTP ingress from `github-events-http-ingress`, and Service Bus settings MUST NOT be required. The production worker command MUST start both the HTTP ingress and Storage queue follow-up consumer and MUST stop both if either component terminates unexpectedly.

#### Scenario: Existing config stays on Service Bus
- **WHEN** operator config has `serviceBus` and `syncState` sections and no `messaging.transport`
- **THEN** the worker consumes and schedules messages on the Service Bus queue as before and does not start an HTTP listener

#### Scenario: Unknown transport
- **WHEN** `messaging.transport` is `eventHub`
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Kafka transport does not require Service Bus settings
- **WHEN** `messaging.transport` is `kafka`, `serviceBus` is absent, and Storage queue and HTTP settings are valid
- **THEN** startup initializes the private `/github-events` listener and Storage queue consumer without failing for a missing Service Bus namespace or queue name

#### Scenario: Kafka component terminates unexpectedly
- **WHEN** the Kafka-mode HTTP server or Storage queue consumer exits unexpectedly
- **THEN** the worker stops the other component and exits non-zero

## ADDED Requirements

### Requirement: Kafka HTTP ingress integration tests
The repository MUST include integration tests that post already-supported GitHub fixture bodies to `/github-events` and assert synchronous HTTP outcomes and follow-up routing without requiring a Kafka client.

#### Scenario: Existing GitHub fixture succeeds
- **WHEN** an integration test posts an already-supported GitHub `renamed`, `edited`, or `deleted` fixture and processing succeeds
- **THEN** the endpoint returns 204 and performs the expected lifecycle handling

#### Scenario: Follow-up is durable before acknowledgement
- **WHEN** an integration test posts an event whose handling requests an internal follow-up
- **THEN** the Storage queue fake or emulator observes the follow-up before the endpoint returns 204

#### Scenario: Failed processing is retryable
- **WHEN** an integration test injects a processing or follow-up scheduling failure
- **THEN** the endpoint returns non-2xx

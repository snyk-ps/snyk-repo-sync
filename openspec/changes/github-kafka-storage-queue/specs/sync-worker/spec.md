## ADDED Requirements

### Requirement: Selectable message transport
The worker MUST select a message transport from `messaging.transport` in operator config, overridable by `MESSAGING_TRANSPORT`. Allowed values are `serviceBus` and `kafka`. When the key is omitted, the transport MUST be `serviceBus`. Any other value MUST fail startup with a clear configuration error.

On `serviceBus`, GitHub events, ADO events, and internal follow-ups MUST use the configured Service Bus queue, and `serviceBus.fullyQualifiedNamespace` and `serviceBus.queueName` MUST remain required. Storage queue settings MUST be ignored.

On `kafka`, internal follow-ups MUST use the storage queue from the `storage-queue-transport` capability, GitHub events MUST use the event-connector ingress from `event-ingestion`, and Service Bus settings MUST NOT be required. The production worker command MUST exit at startup until an event-connector client exists, as specified by `event-ingestion`.

#### Scenario: Existing config stays on Service Bus
- **WHEN** operator config has `serviceBus` and `syncState` sections and no `messaging.transport`
- **THEN** the worker consumes and schedules messages on the Service Bus queue as before

#### Scenario: Unknown transport
- **WHEN** `messaging.transport` is `eventHub`
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Kafka transport does not require Service Bus settings
- **WHEN** `messaging.transport` is `kafka`, `serviceBus` is absent, and storage-queue settings are valid
- **THEN** startup does not fail for a missing Service Bus namespace or queue name

### Requirement: Storage queue idle consumption
When the storage-queue transport is running, the worker MUST keep polling it when no messages are available. An idle queue MUST NOT cause the process to exit with status 0. The poll wait MUST use `storageQueue.receiveMaxWaitSeconds`.

#### Scenario: Empty storage queue does not stop the consumer
- **WHEN** the storage-queue consumer is running and no messages are visible for longer than one poll interval
- **THEN** it continues polling and does not exit solely because the queue is idle

## MODIFIED Requirements

### Requirement: Queue-driven processing
The worker MUST consume messages from the selected transport on demand; it MUST NOT rely on always-on polling of ADO, GitHub, or Snyk as its primary trigger.

On `serviceBus`, that transport is the Service Bus queue. On `kafka`, GitHub events come from the event connector and internal follow-ups come from the storage queue.

#### Scenario: Message available
- **WHEN** a transport message is available on the selected transport
- **THEN** the worker receives and processes it

### Requirement: Unrecoverable failure handling
On unrecoverable processing failure, the worker MUST dead-letter the message and emit an alert.

On `serviceBus`, dead-letter MUST use the Service Bus dead-letter queue. On `kafka`, dead-letter MUST poison-settle the storage-queue message per the `storage-queue-transport` capability. The dead-letter reason strings MUST be the same on both transports.

Import job polling MUST dead-letter with reason `ImportJobFailed` when `retryCount` reaches 5 on `import_poll` follow-up messages.

#### Scenario: Snyk import permanently fails
- **WHEN** import fails after retries/backoff with a non-transient error or max poll retries exceeded
- **THEN** the message is dead-lettered and an alert is raised

### Requirement: Import job polling with concurrency limits
When an import is initiated, the worker MUST NOT block the receive loop until the job completes. The worker MUST schedule follow-up messages with exponential backoff and MUST respect `snyk.maxConcurrentPendingImports` (default 100 per worker process).

On `serviceBus`, follow-ups MUST be scheduled on that same Service Bus queue. On `kafka`, follow-ups MUST be scheduled on the storage queue in the sync-state storage account. Follow-ups MUST NOT be published to Kafka.

Follow-up messages MUST carry `syncPhase`, `importJobId`, `importStatus`, and `retryCount`.

#### Scenario: Import in progress
- **WHEN** Snyk returns an in-progress import job
- **THEN** the worker upserts `importStatus=pending`, completes the current message, and schedules an `import_poll` follow-up with incremented backoff on the active follow-up queue

#### Scenario: Import job completes
- **WHEN** an `import_poll` follow-up finds the import job succeeded
- **THEN** the worker updates repository state with `importStatus=complete`, retains `importJobId`, sets `snykTargetId`, and completes the follow-up message without project tagging

#### Scenario: Pending import limit reached
- **WHEN** the count of repository rows with `importStatus=pending` equals or exceeds `snyk.maxConcurrentPendingImports`
- **THEN** the worker logs a structured warning, completes the lifecycle message, and schedules a `lifecycle_deferred` follow-up with backoff rather than dead-lettering

### Requirement: Operator config and credential startup
The worker MUST authenticate to Azure with `DefaultAzureCredential`. It MUST load operator settings from the config file path supplied via `--config` (default `data/config.yaml`). The config file MUST exist. Settings MAY be supplied in config and MAY be overridden by environment variables; env values MUST take precedence when set. The worker MUST ensure the sync-state table exists on startup. Connection strings MUST NOT be supported or documented.

On `serviceBus`, the worker MUST authenticate to Azure Service Bus and the runtime identity MUST be granted **Azure Service Bus Data Owner** (or Azure Service Bus Data Receiver and Azure Service Bus Data Sender) on the queue or namespace — data plane only. On `kafka`, Service Bus credentials MUST NOT be required, and the runtime identity MUST be granted the queue data role from the `storage-queue-transport` capability.

On every transport the runtime identity MUST be granted **Storage Table Data Contributor** on the storage account or table scope.

The worker MUST fail fast when the config file path does not exist, when required settings for the selected transport are missing after config/env merge, or when credential initialization fails.

#### Scenario: Worker starts in production on Service Bus
- **WHEN** the container starts with `--config /config/config.yaml`, `messaging.transport` omitted or `serviceBus`, valid YAML, and a managed identity with Service Bus and table RBAC roles
- **THEN** it ensures the sync-state table exists, connects to the pre-provisioned Service Bus queue, and begins receiving messages

#### Scenario: Local run with default config path
- **WHEN** a developer runs `worker run` without `--config`
- **THEN** the worker loads `data/config.yaml` and authenticates via `az login` (or configured dev principal)

#### Scenario: Local run with env override
- **WHEN** `data/config.yaml` exists, transport is `serviceBus`, and `SERVICEBUS_QUEUE_NAME` overrides the file value
- **THEN** the worker uses the env value for the queue name

#### Scenario: Missing config file
- **WHEN** `--config` points to a path that does not exist
- **THEN** the worker exits with a non-zero status and a clear error message

#### Scenario: Missing required setting after merge
- **WHEN** transport is `serviceBus` and `serviceBus.fullyQualifiedNamespace` is absent in both config and env after merge
- **THEN** the worker exits with a non-zero status and a clear error message

### Requirement: Existing queue reference only
On the `serviceBus` transport, the worker MUST consume from a pre-provisioned Service Bus queue. The worker MUST NOT create, alter, or delete Service Bus queues or namespaces.

On the `kafka` transport, the worker MUST NOT open a Service Bus client. Storage queue provisioning rules are defined by the `storage-queue-transport` capability.

#### Scenario: Queue consumption
- **WHEN** transport is `serviceBus` and transport messages are available on the configured queue
- **THEN** the worker receives them without provisioning queue infrastructure

### Requirement: Slice-5 ADO lifecycle sync with import deferral
After successful lifecycle normalization and scope mapping resolution, the worker MUST execute repository lifecycle sync per the `repo-lifecycle` and `snyk-target-sync` capabilities for mapped scopes (ADO and GitHub).

The worker MUST read and write repository sync state, call the Snyk API, and route internal follow-up messages on the active follow-up queue for the selected transport (the Service Bus queue on `serviceBus`; the storage queue on `kafka`).

#### Scenario: Valid ADO message with mapped project and repo created
- **WHEN** the worker normalizes a repo-created ADO message whose scope mapping resolves
- **THEN** it triggers Snyk import and updates sync state without completing import inline in the receive handler

#### Scenario: Valid ADO message with unmapped project
- **WHEN** the worker normalizes an ADO lifecycle message whose scope has no mapping and no default org
- **THEN** it logs an unmapped-scope warning and completes the message without Snyk side effects

#### Scenario: Valid GitHub message with mapped org and repo created
- **WHEN** the worker normalizes a repo-created GitHub message whose scope mapping resolves by org login
- **THEN** it triggers Snyk import and updates sync state without completing import inline in the receive handler

#### Scenario: Valid GitHub message with unmapped org
- **WHEN** the worker normalizes a GitHub lifecycle message whose org login has no mapping and no default org
- **THEN** it logs an unmapped-scope warning and completes the message without Snyk side effects

### Requirement: Internal follow-up message routing
The worker MUST deserialize internal follow-up messages on the active follow-up queue, distinguished by top-level `syncPhase`. Supported values: `import_poll`, `lifecycle_deferred`.

On `serviceBus`, that queue is the Service Bus queue. On `kafka`, that queue is the storage queue.

Internal messages MUST NOT be parsed as ADO Event Grid or GitHub webhook payloads.

#### Scenario: Import poll follow-up received
- **WHEN** the worker receives a message with `syncPhase: import_poll`
- **THEN** it polls the referenced import job and reschedules, finalizes state, or dead-letters per retry policy

#### Scenario: Lifecycle deferred follow-up received
- **WHEN** the worker receives a message with `syncPhase: lifecycle_deferred`
- **THEN** it re-attempts the deferred lifecycle action when pending import count is below the configured limit

### Requirement: Continuous queue consumption on idle queue
On the `serviceBus` transport, the worker MUST remain running and continue polling the configured Service Bus queue when no messages are available. An idle queue MUST NOT cause the worker process to exit with status 0.

#### Scenario: Empty queue does not stop worker
- **WHEN** the worker starts successfully on the `serviceBus` transport and the queue has no available messages for longer than one receive poll interval
- **THEN** the worker continues polling and does not exit solely due to the idle period

#### Scenario: Message processed after idle period
- **WHEN** the worker is polling an idle Service Bus queue and a message is later published
- **THEN** the worker receives and processes the message without requiring a process restart

### Requirement: Service Bus receive poll interval
On the `serviceBus` transport, the worker MUST poll the queue using a configurable maximum wait time per receive attempt. The default MUST be 5 seconds. The setting MUST be read from `serviceBus.receiveMaxWaitSeconds` in operator config, with environment override `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS`. Invalid values MUST fail at startup with a clear configuration error.

The receive poll interval MUST NOT be implemented by setting `max_wait_time` on the Service Bus receiver constructor when iterating messages, because that causes the SDK iterator to terminate after an idle timeout.

#### Scenario: Default poll interval
- **WHEN** transport is `serviceBus` and `serviceBus.receiveMaxWaitSeconds` is omitted from config
- **THEN** the worker uses a 5-second maximum wait per receive attempt

#### Scenario: Configured poll interval
- **WHEN** transport is `serviceBus` and `serviceBus.receiveMaxWaitSeconds` is set to a positive integer in config
- **THEN** the worker uses that value for each receive attempt

#### Scenario: Environment override
- **WHEN** transport is `serviceBus` and `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS` is set in the environment
- **THEN** it takes precedence over the config file value

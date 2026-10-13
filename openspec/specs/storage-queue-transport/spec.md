# storage-queue-transport Specification

## Purpose
TBD - created by archiving change github-kafka-storage-queue. Update Purpose after archive.
## Requirements
### Requirement: Same storage account as sync state
When `messaging.transport` is `kafka`, the worker MUST use an Azure Storage queue in the same storage account as the sync-state table. The queue service URL MUST be derived from `syncState.storageAccountEndpoint` by replacing the `.table.` host label with `.queue.`. The worker MUST NOT accept a separate storage account endpoint for the queue.

#### Scenario: Queue URL derived from the table endpoint
- **WHEN** `syncState.storageAccountEndpoint` is `https://myaccount.table.core.windows.net` and `storageQueue.queueName` is `repo-sync-followups`
- **THEN** the worker addresses queue `repo-sync-followups` at `https://myaccount.queue.core.windows.net`

#### Scenario: Table endpoint is not a table service URL
- **WHEN** `messaging.transport` is `kafka` and `syncState.storageAccountEndpoint` has no `.table.` host label
- **THEN** the worker exits at startup with a clear configuration error

### Requirement: Pre-provisioned queue and identity auth
The storage queue and its poison queue MUST be provisioned outside this repository. The worker MUST NOT create, alter, or delete storage accounts or queues. The worker MUST authenticate with `DefaultAzureCredential` and MUST NOT use connection strings, account keys, or shared access signatures.

`storageQueue.queueName` MUST be set when `messaging.transport` is `kafka`. It MAY be overridden by `STORAGE_QUEUE_NAME`. Env values MUST take precedence when set. The poison queue name MUST default to `{queueName}-poison` and MAY be overridden by `storageQueue.poisonQueueName` or `STORAGE_QUEUE_POISON_NAME`.

Queue names MUST be 3–63 characters and contain only lowercase letters, numbers, and hyphens. Invalid names MUST fail startup.

The runtime identity MUST be granted a queue data role that allows send and receive (Storage Queue Data Contributor or equivalent) on that storage account when `messaging.transport` is `kafka`.

#### Scenario: Worker starts against an existing queue
- **WHEN** the worker starts with `messaging.transport: kafka`, a valid queue name, and RBAC on the sync-state storage account
- **THEN** it uses the existing queue and does not create queue infrastructure

#### Scenario: Missing queue name
- **WHEN** `messaging.transport` is `kafka` and the queue name is absent from both config and env after merge
- **THEN** the worker exits at startup with a clear configuration error

### Requirement: Follow-up messages only
The storage queue MUST carry only internal follow-up JSON bodies with top-level `syncPhase` of `import_poll` or `lifecycle_deferred`. The body MUST be the same JSON object the worker already schedules on Service Bus, with no transport envelope.

A message without a supported `syncPhase` MUST be poison-settled with reason `InvalidMessage`.

#### Scenario: Import poll body on the storage queue
- **WHEN** the worker receives a storage-queue message whose JSON has `syncPhase: import_poll` and the fields required by the follow-up schema
- **THEN** it polls the referenced import job using the same handler as the Service Bus path

#### Scenario: GitHub webhook body on the storage queue
- **WHEN** the worker receives a storage-queue message that is GitHub webhook JSON and has no `syncPhase`
- **THEN** it poison-settles the message with reason `InvalidMessage` and does not run lifecycle sync

### Requirement: Delayed send and lock
The worker MUST schedule follow-ups by sending the JSON body with an initial visibility timeout equal to the follow-up delay. Delays MUST be at least 0 seconds and MUST NOT exceed 7 days.

While processing, the worker MUST hide the message for `storageQueue.visibilityTimeoutSeconds` (default 60). The setting MAY be overridden by `STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS`. Invalid values MUST fail startup. The idle poll interval MUST use `storageQueue.receiveMaxWaitSeconds` (default 5), overridable by `STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS`, with the same 1–300 second bounds as the Service Bus poll interval. An empty queue MUST NOT stop the worker when this transport is running under test with an injected event source.

Successful processing MUST delete the message. Scheduling a follow-up MUST delete the current message and enqueue a new delayed message.

#### Scenario: Import poll scheduled with backoff
- **WHEN** lifecycle handling requests an `import_poll` follow-up with `delay_seconds` of 30
- **THEN** the worker enqueues that JSON body with an initial visibility timeout of 30 seconds and deletes the message that triggered it

#### Scenario: Successful follow-up
- **WHEN** an `import_poll` message is processed to a terminal success
- **THEN** the worker deletes that message and does not enqueue another copy

### Requirement: Poison settlement
Dead-letter on this transport MUST copy the original message body unchanged onto the poison queue, log the dead-letter reason, and delete the source message. The reason MUST NOT be written into the message body.

The worker MUST poison-settle a message whose dequeue count is greater than or equal to 10, with reason `MaxDequeueCountExceeded`, even when the body is otherwise valid.

#### Scenario: Import job failed
- **WHEN** an `import_poll` message reaches `retryCount` 5 and the handler dead-letters with reason `ImportJobFailed`
- **THEN** the original body is on the poison queue, the source message is deleted, and the reason is logged

#### Scenario: Dequeue count exhausted
- **WHEN** a storage-queue message is received with dequeue count 10
- **THEN** the worker poison-settles it with reason `MaxDequeueCountExceeded` and does not run lifecycle handling


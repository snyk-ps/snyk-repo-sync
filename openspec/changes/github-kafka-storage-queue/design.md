## Context

The worker has one transport. `WorkerConsumer` receives from a Service Bus queue, `handle_queue_message` parses the JSON body, and follow-ups (`import_poll`, `lifecycle_deferred`) are scheduled back onto that same queue with `schedule_messages`. Sync state is an Azure Table in the account given by `syncState.storageAccountEndpoint`. Auth is `DefaultAzureCredential`. The worker does not create the Service Bus queue. Ignore reconciliation is an in-process timer, not a queue message.

Some GitHub deployments will deliver repository lifecycle events on a Kafka topic. The worker will read that topic only through an event connector's REST API over HTTP. That REST contract is not available yet. Internal follow-ups must not be published back to Kafka. ADO audit ingestion stays on Service Bus.

## Goals / Non-Goals

**Goals:**

- Keep the Service Bus path as the default. Existing configs keep working with no new required keys.
- Add a `kafka` transport mode whose worker-produced messages use a Storage queue in the same storage account as the sync-state table.
- Hide complete, dead-letter, and delayed send behind a small transport interface so lifecycle handling stays body-oriented.
- Fail closed when `kafka` is selected, because the event-connector client cannot be implemented yet.
- Define poison-message handling that preserves the original JSON body and the same log reason as Service Bus dead-letter.

**Non-Goals:**

- Implementing the event-connector HTTP client, choosing its auth scheme, or adding a Kafka client library.
- Publishing anything to Kafka.
- Accepting GitHub or ADO lifecycle events on the storage queue.
- Moving ADO off Service Bus.
- Changing the sync-state table schema or creating storage accounts, queues, or Service Bus resources.
- KEDA scaling for the storage queue (document the gap; do not design a scaler in this change).

## Decisions

### 1. Two transports, default `serviceBus`

**Decision:** Operator config gains `messaging.transport`: `serviceBus` (default when omitted) or `kafka`.

| Transport | GitHub and ADO events | `import_poll` and `lifecycle_deferred` | Sync state |
| --------- | --------------------- | -------------------------------------- | ---------- |
| `serviceBus` | Service Bus queue | Same Service Bus queue | Table |
| `kafka` | Event connector HTTP (not implemented) | Storage queue in the table's storage account | Table |

`serviceBus.*` stays required only when `transport` is `serviceBus`. `storageQueue.queueName` is required only when `transport` is `kafka`. Env overrides follow the existing precedence (env wins when set).

**Alternative rejected:** Always requiring both queues. Operators on Service Bus would have to provision a storage queue they do not use.

### 2. Derive the queue endpoint from the table endpoint

**Decision:** Do not add a second storage account setting. Given `https://{account}.table.{suffix}`, the queue service URL is `https://{account}.queue.{suffix}`. Startup fails if the table host does not contain a `.table.` label, so sovereign-cloud suffixes still work and a wrong endpoint is not silently rewritten.

The queue and its poison queue are pre-provisioned in that account. The worker uses `DefaultAzureCredential` and does not use connection strings, account keys, or SAS. It does not create the queues. On the `kafka` path the identity needs a queue data role (Storage Queue Data Contributor, or equivalent send and receive) on that account, plus the existing table role. Service Bus roles are not required on that path.

**Alternative rejected:** A separate `storageQueue.accountEndpoint`. That allows the queue and the table to drift into different accounts, which this change forbids.

### 3. Storage queue carries follow-ups only

**Decision:** Bodies are the same JSON objects already built in `worker.followup` (top-level `syncPhase`). No envelope. A storage-queue message without a supported `syncPhase` is an invalid message and is poison-settled.

Delayed send uses the initial visibility timeout on `send_message`. Current backoff is 30–900 seconds, under the 7-day visibility maximum. While a message is being processed, receive uses a configurable visibility timeout (default 60 seconds) as the lock. Success deletes the message. Scheduling a follow-up deletes (completes) the current message and enqueues a new one, matching today's complete-then-schedule behavior.

Azure Queue names must be 3–63 characters, lowercase letters, numbers, and hyphens. Validate at startup.

**Alternative rejected:** Putting raw GitHub webhook bodies on the storage queue. Those payloads are the connector's job, and the 64 KiB queue limit is a poor fit for webhook bodies.

### 4. Poison queue instead of a dead-letter subqueue

**Decision:** Application dead-letter (invalid JSON, `InvalidNormalization`, `ImportJobFailed`, Snyk API failure, and any other current dead-letter reason) copies the original body onto `{queueName}-poison` (override `storageQueue.poisonQueueName`), logs the reason, and deletes the source message. The reason is not stuffed into the body.

A message whose `dequeue_count` reaches 10 (aligned with the Service Bus max delivery count guidance) takes the same poison path, with reason `MaxDequeueCountExceeded`. That covers crashes that let the visibility timeout expire.

**Alternative rejected:** Delete-and-log only. Operators could not replay the body. **Alternative rejected:** Wrapping the body with a reason field. That would make poison messages a different schema from the live follow-up.

### 5. Event connector is a seam, not a client

**Decision:** Define a `GitHubEventSource` protocol (receive, complete, dead-letter) and do not add an HTTP implementation. `worker run` with `messaging.transport: kafka` exits non-zero with a clear configuration error that the REST contract is pending. It does not fall back to Service Bus and does not call a placeholder URL.

Tests may inject a fake event source plus the storage-queue transport to prove follow-ups are scheduled on the storage queue and GitHub bodies are not. Production wiring has nothing to inject.

**Alternative rejected:** Starting the storage-queue loop with GitHub intake disabled. A running worker that never sees repository events looks healthy and is not.

### 6. Lifecycle code stays on bytes

**Decision:** `handle_queue_message` keeps taking a JSON body. Service Bus and storage-queue receivers translate their native message types into body plus settlement. Follow-up scheduling takes `(body, delay_seconds)` and the active transport performs the delayed send.

## Risks / Trade-offs

- [Kafka path cannot run in production until the REST spec exists] → Fail closed at startup; storage-queue behavior is covered by unit tests with a fake queue client. No Azurite requirement in CI.
- [Storage queue has no native dead-letter or scheduled-message type] → Poison queue plus initial visibility timeout. Reasons live in logs, which observability already alerts on.
- [Visibility timeout is shorter than a stuck Snyk call] → Idempotency by `eventId` and desired state still applies if the message reappears. Default lock is 60 seconds and is configurable.
- [64 KiB message limit] → Follow-up envelopes stay small. Do not put webhook bodies on this queue.
- [Poison enqueue succeeds and source delete fails] → Duplicate body on the poison queue is acceptable; the source message retries and may poison again. Log both steps.
- [No KEDA storage-queue scaler documented] → `kafka` path is documented as min replicas 1 until a later change. Service Bus KEDA guidance stays as it is.

## Migration Plan

1. Ship with default `serviceBus`. Existing Container Apps keep their config and RBAC.
2. Operators who will use Kafka later provision a storage queue and a poison queue in the sync-state storage account and grant the worker identity a queue data role. They do not switch `messaging.transport` until the connector client exists; switching now exits at startup.
3. Rollback is reverting the image. No table schema change and no Service Bus entity change.

## Open Questions

- Event-connector base URL, auth, poll vs push, payload wrapper, and ack/nack semantics. Blocked on the REST spec. Do not guess them in implementation.
- Whether the connector will hand the worker raw webhook JSON, the parsed `deliveryId` contract, or both. The worker already normalizes both shapes once the body is in hand.

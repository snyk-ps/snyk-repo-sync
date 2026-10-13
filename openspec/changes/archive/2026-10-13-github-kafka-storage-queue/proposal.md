## Why

GitHub lifecycle events will arrive on a Kafka topic in some deployments, consumed through an event-connector REST API, while the worker still has to schedule its own import-poll and deferred-lifecycle messages. Those internal messages do not belong on the Kafka topic. Deployments that stay on Service Bus must keep working unchanged.

## What Changes

- Keep the current path: one pre-provisioned Service Bus queue carries GitHub events, ADO events, and internal follow-ups (`import_poll`, `lifecycle_deferred`). Azure Table Storage remains the sync-state store on every path.
- Add a second path for GitHub deployments:
  - GitHub events are consumed only from Kafka, via an event connector and its REST API over HTTP. The worker does not publish follow-ups back to that topic.
  - Internal follow-ups go to a pre-provisioned Azure Storage queue in the **same storage account** as the sync-state table.
- The HTTP event-connector client is **out of scope for this change**. The REST contract is not available yet, so this change must not invent request shapes, auth, or ack semantics. It specifies the seam and implements the storage-queue half plus the transport switch.
- Selecting the Kafka path without a connector implementation fails closed at startup. It must not fall back to Service Bus or poll a guessed URL.
- ADO audit ingestion stays on the Service Bus path. Ignore reconciliation stays an in-process timer, not a queue message.

## Capabilities

### New Capabilities

- `storage-queue-transport`: Azure Storage queue in the sync-state storage account for worker-produced follow-up messages, including delayed delivery, poison handling, and data-plane auth.

### Modified Capabilities

- `event-ingestion`: Document the Service Bus path as one supported GitHub ingress, and add the Kafka event-connector path as consumption-only ingress whose HTTP client is not implemented in this change.
- `sync-worker`: Select the transport at startup. On the Service Bus path, behavior is unchanged. On the Kafka path, GitHub event intake is the deferred connector and follow-ups are scheduled on the storage queue. Settlement, backoff, and dead-letter outcomes stay equivalent across transports.
- `observability`: Unrecoverable failures on the storage queue (poison messages) raise the same alert class as Service Bus dead-letter.

## Impact

- **Code:** `src/config/settings.py` (transport mode; storage queue name derived from the sync-state account); `src/worker/consumer.py` and follow-up scheduling (`src/worker/followup.py`) split behind a transport interface. Service Bus remains the default.
- **Dependency:** `azure-storage-queue` (or the queue client shipped with the Azure Storage SDK). Snyk Open Source scan required before merge. No Kafka client library.
- **RBAC:** Storage Queue Data Contributor (or equivalent send and receive queue data roles) on the same storage account as the table, in addition to Storage Table Data Contributor. Service Bus roles stay required only for the Service Bus path.
- **Docs:** `CONFIGURATION.md`, `INGESTION.md`, `README.md` — second path, same-account queue, and an explicit note that the event-connector HTTP client is pending the REST spec.
- **Out of scope:** Implementing the event-connector REST client, Kafka producer/consumer libraries, publishing to Kafka, moving ADO off Service Bus, and changing the sync-state table schema.

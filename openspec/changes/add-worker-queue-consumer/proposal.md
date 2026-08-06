## Why

External systems push repository lifecycle events to an existing Azure Service Bus queue; the worker Container App is the only application in this repository and must consume those messages reliably. This change locks the queue-side transport contract and implements the worker's Service Bus consumer so integration tests can publish fixtures and assert end-to-end consumption before normalization, state updates, and Snyk sync land in a follow-up change.

## What Changes

- Add worker Service Bus consumer that reads from the pre-provisioned queue (no queue creation or management).
- Define and implement transport envelope deserialization (`source`, `ingressId`, `receivedAt`, `rawPayload`) per `event-ingestion`.
- Add worker Container App entrypoint configured via environment secrets only (no config file).
- Add unit tests for envelope parsing and integration tests that publish transport fixtures to the queue.
- Defer lifecycle normalization, sync state access, and Snyk actions to a follow-up change.

## Capabilities

### New Capabilities

_None — this change implements existing capabilities rather than introducing new ones._

### Modified Capabilities

- `sync-worker`: Add requirements for Service Bus consumption, transport envelope handling, environment-driven startup, and integration tests for the first implementation slice (normalization and sync deferred).
- `event-ingestion`: Add requirement documenting the worker-side transport envelope contract and that the worker references the existing queue without provisioning it.

## Impact

- **Code**: New worker modules under `src/` (Service Bus consumer, transport envelope, CLI entrypoint), tests under `tests/`, fixtures under `data/fixtures/`.
- **Dependencies**: Azure Service Bus client library (e.g. `azure-servicebus`); Snyk scan required before merge.
- **Deployment**: Worker Container App env/secrets (`SERVICEBUS_CONNECTION_STRING`, queue name, etc.); no new deployables.
- **Out of scope**: HTTP ingress, config files, queue provisioning, normalization, sync state, Snyk import, observability alerting.

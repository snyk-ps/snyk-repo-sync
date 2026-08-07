## Why

Production wiring is ADO audit stream → Event Grid topic → Event Grid subscription → Service Bus queue, with no ingress wrapper. The worker expects a transport envelope (`source`, `ingressId`, `receivedAt`, `rawPayload`) that is never produced on the wire, causing valid Event Grid messages to dead-letter as `InvalidEnvelope`.

Wrapping at ingress adds metadata we do not control and cannot treat as authoritative. The audit record inside Event Grid `data` already carries org, project, repository, branch, and timestamps. Subscription filters (`subject`, `data.ActionId`) already constrain what reaches the queue.

## What Changes

- **BREAKING:** Remove the transport envelope contract entirely (no legacy support).
- ADO: Event Grid subscription delivers native Event Grid JSON directly to Service Bus; worker identifies ADO messages when `eventType` is `AzureDevOpsAuditEvent` **or** `subject` is `AzureDevOps/Auditing`, then normalizes from `data`.
- Document Event Grid subscription advanced filters: `subject` = `AzureDevOps/Auditing` plus existing `data.ActionId` lifecycle filter (no separate `includedEventTypes` filter).
- Replace `src/worker/envelope.py` transport parsing with native queue message parsing; wire into existing ADO normalization.
- Replace fixtures and tests with Event Grid–shaped ADO messages (and raw GitHub webhook JSON).
- Remove transport envelope, ingress-handler steps, and envelope-based diagrams from README, CONFIGURATION, CONTRIBUTING, INGESTION, openspec/SPEC.md, and affected capability specs.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `event-ingestion`: Replace transport envelope with native queue message contracts (ADO Event Grid schema; GitHub raw webhook JSON).
- `sync-worker`: Replace envelope deserialization with shape-based message parsing and source detection; update DLQ reasons, scenarios, and integration test fixtures.
- `ado-provisioning`: Event Grid subscription → Service Bus with `subject` and `data.ActionId` filters; remove ingress handler requirement.
- `github-webhook-ingestion`: Publish raw signed webhook JSON to the queue (no transport envelope).

## Impact

- **Code:** Replace/rename `envelope.py` → native queue message parser; update `handler.py`, `consumer.py`, `normalize.py` input path.
- **Fixtures:** `data/fixtures/eventgrid_ado_*.json`; remove `transport_envelope_*.json`; GitHub raw webhook fixture.
- **Docs/diagrams:** README, CONFIGURATION, CONTRIBUTING, INGESTION (architecture mermaid), openspec/SPEC.md capability descriptions.
- **Specs:** `event-ingestion`, `sync-worker`, `ado-provisioning`, `github-webhook-ingestion`.
- **Out of scope:** GitHub normalization implementation; Snyk sync; building webhook ingress in this repo.

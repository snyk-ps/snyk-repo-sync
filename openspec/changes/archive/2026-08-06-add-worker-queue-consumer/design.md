## Context

Repository lifecycle events from ADO and GitHub are pushed to an existing Azure Service Bus queue by customer-owned external infrastructure (webhook handlers, Event Grid subscribers, etc.). The worker Container App in this repository is the sole deployable: one or more container replicas read from the queue and — in the full system — perform normalization, state updates, and Snyk sync.

The codebase is currently a scaffold (`src/main.py` placeholder). Canonical specs define the transport envelope in `event-ingestion` and the full worker behavior in `sync-worker`. This change implements the first slice: queue consumption and transport envelope handling only.

Configuration is environment-driven (Container App secrets). No config file. The worker MUST NOT create or manage Service Bus infrastructure.

## Goals / Non-Goals

**Goals:**

- Consume messages from the pre-provisioned Service Bus queue.
- Deserialize and validate the transport envelope (`source`, `ingressId`, `receivedAt`, `rawPayload`).
- Complete well-formed messages; dead-letter messages that fail envelope validation.
- Provide a Container App entrypoint and integration tests (publish fixture → worker consumes).
- Lock the queue-side contract so a follow-up change can add normalization and sync on a stable foundation.

**Non-Goals:**

- Lifecycle normalization (`eventType`, `scopeId`, etc.).
- Sync state, Snyk import, ignore policy, observability alerting.
- HTTP webhook endpoints or any ingress deployable in this repo.
- Service Bus queue/namespace provisioning.
- Configuration files (`data/config.yaml` or similar).

## Decisions

### 1. Single worker process with receive loop

**Decision:** Implement a long-running worker process with an Azure Service Bus receive loop (SDK `ServiceBusClient` + queue receiver).

**Rationale:** Matches Container App deployment model and existing `sync-worker` queue-driven requirement. KEDA scale-to-zero can be added at deployment time without code changes.

**Alternatives considered:**
- Azure Functions Service Bus trigger — rejected; worker is a Container App per project architecture.
- Polling ADO/GitHub directly — rejected; violates queue-driven processing requirement.

### 2. Transport envelope as typed dataclass

**Decision:** Define a `TransportEnvelope` dataclass in `src/` with validation on deserialize.

**Rationale:** Envelope fields are fixed and testable; keeps normalization layer (follow-up) separate from parsing.

**Alternatives considered:**
- Raw dict passthrough — rejected; validation belongs at consumption boundary.

### 3. Environment-only configuration

**Decision:** Required settings (`SERVICEBUS_CONNECTION_STRING`, queue name env var) read at startup; fail fast if missing.

**Rationale:** Container App injects secrets as env vars; no committed config file needed.

### 4. Slice-1 message handling: validate and complete

**Decision:** After envelope validation, complete the message without further processing. Malformed envelopes → dead-letter.

**Rationale:** Smallest vertical slice that proves queue consumption and envelope contract. Normalization hooks can be added in the follow-up change without changing the consumer loop structure.

**Alternatives considered:**
- No-op with logging only — rejected; must complete/abandon/dead-letter per Service Bus semantics.

### 5. `azure-servicebus` dependency

**Decision:** Use the official Azure Service Bus Python SDK.

**Rationale:** No stdlib equivalent; SDK handles receive, complete, and dead-letter. Snyk Open Source scan required before merge.

### 6. Package layout

| Module | Responsibility |
| ------ | -------------- |
| `src/worker/envelope.py` | Transport envelope model and validation |
| `src/worker/consumer.py` | Service Bus receive loop, complete/dead-letter |
| `src/commands/worker.py` | CLI entrypoint (`worker run`) |
| `data/fixtures/` | ADO and GitHub transport envelope JSON fixtures |
| `tests/worker/` | Unit and integration tests |

## Risks / Trade-offs

| Risk | Mitigation |
| ---- | ---------- |
| Integration tests require real or emulated Service Bus | Document env setup; use emulator or dedicated test namespace; skip integration tests when env not configured |
| Completing messages without processing hides wiring bugs until normalization lands | Integration tests assert envelope fields logged or captured via test hook before complete |
| `azure-servicebus` adds dependency surface | Snyk Open Source scan; pin version in `pyproject.toml` |
| Multiple worker replicas may process concurrently | Acceptable for slice 1; idempotency handled in follow-up change |

## Migration Plan

1. Deploy worker Container App with Service Bus env secrets pointing at existing queue.
2. Run integration tests against test namespace before production rollout.
3. Follow-up change adds normalization without changing queue subscription model.

## Open Questions

- Exact env var names for queue name (`SERVICEBUS_QUEUE_NAME` vs platform convention) — document in CONFIGURATION.md during implementation.
- Whether integration tests run in CI with emulator or are marked optional — decide during implementation based on CI Service Bus availability.

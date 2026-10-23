## Why

Kafka-based GitHub deployments need an application-owned HTTP endpoint that the event connector can call after reading repository lifecycle events from Kafka. The current `kafka` mode assumes a future pull client and fails at startup, so the connector cannot yet relay events into the worker.

## What Changes

- Add `POST /github-events` as private-network ingress for event-connector deliveries when `messaging.transport: kafka`.
- Process each request synchronously through the existing GitHub message handling path. Return a 2xx response only after processing, including durable scheduling of any internal follow-up, succeeds; any non-2xx response is retryable and retry policy remains owned by the event connector.
- Run the HTTP ingress together with Azure Storage queue consumption for `import_poll` and `lifecycle_deferred` follow-ups on the Kafka path.
- Replace the unimplemented pull-style `GitHubEventSource` seam and Kafka startup failure with connector-pushed HTTP ingress. Continue to prohibit publishing application messages to Kafka.
- Do not add application-level authentication. The endpoint is intended to have no public route and to be reachable only by the event connector through customer-managed private-network controls.
- Preserve `serviceBus` as the recommended and default transport. The Service Bus path and its GitHub and ADO behavior remain unchanged.
- Limit `/github-events` to GitHub. ADO/Azure Repos events remain explicitly excluded from the Kafka path.
- Treat `updated`, `renamed`, `edited`, and `deleted` as the intended connector event set. This change provides the HTTP transport and processes already-supported payload shapes; the connector message-contract change, new fixtures, `updated` normalization, and Snyk organization mapping from `updated` details are deferred to a subsequent change. `created` is not part of the Kafka endpoint event set.

## Capabilities

### New Capabilities

- `github-events-http-ingress`: Private `POST /github-events` ingress, synchronous processing and response semantics, transport gating, and network/authentication boundary for event-connector delivery.

### Modified Capabilities

- `event-ingestion`: Change Kafka event-connector ingress from a pending worker-side pull client to connector-pushed HTTP delivery while preserving Service Bus as the default and excluding ADO from Kafka.
- `sync-worker`: Start HTTP GitHub ingress and Storage queue follow-up consumption in Kafka mode instead of failing closed for the missing connector client.

## Impact

- **Code:** HTTP application/server adapter, Kafka-mode startup and shutdown, replacement of `worker.event_source`, reuse of message handling with HTTP response settlement, and concurrent Storage queue follow-up consumption.
- **API:** New private `POST /github-events` endpoint. A 2xx response acknowledges successful processing; all non-2xx responses are retried by the event connector.
- **Configuration/deployment:** HTTP bind and port settings; private routing from the event connector to the application; no public ingress and no application credential.
- **Dependencies:** A production-capable Python HTTP server/framework may be required. Any added dependency must be managed with `uv` and pass Snyk Open Source review with no high or critical issues.
- **Documentation:** `README.md`, `CONFIGURATION.md`, `INGESTION.md`, and example configuration must describe the push model, endpoint, response contract, private-network requirement, and deferred payload contract.
- **Risk:** Unsupported or malformed events receive non-2xx responses and may be retried or block a Kafka partition according to connector policy. That connector-managed risk is accepted for this transport slice.

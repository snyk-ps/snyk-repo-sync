## Context

The worker currently has two configured transports. `serviceBus` is the default and uses one Service Bus queue for provider events and internal follow-ups. `kafka` already uses an Azure Storage queue in the sync-state account for internal follow-ups, but production startup deliberately fails because `worker.event_source.GitHubEventSource` models a connector client whose REST contract was unknown.

The connector contract is now push-based: the event connector reads Kafka and sends `POST /github-events` to this application. Any 2xx response acknowledges the connector message; every non-2xx response is retried under connector-managed policy. The endpoint is reachable over a customer-managed private network and has no application-level authentication or public route.

The worker already normalizes raw GitHub webhook JSON and the parsed `deliveryId` contract. The connector's revised shapes, including `updated` details used for later Snyk organization mapping, remain pending and will be specified with fixtures in a subsequent change.

## Goals / Non-Goals

**Goals:**

- Serve private `POST /github-events` only on the `kafka` transport.
- Process an accepted request synchronously through the existing body-oriented GitHub handler.
- Return 204 only after initial handling and any requested Storage queue follow-up have succeeded.
- Return non-2xx for malformed, unsupported, or failed processing so the connector retries.
- Run Storage queue follow-up consumption and HTTP ingress in the same worker process with coordinated startup and shutdown.
- Keep Service Bus behavior and default selection unchanged.

**Non-Goals:**

- Defining or normalizing the connector's revised `updated`, `renamed`, `edited`, or `deleted` message contracts.
- Implementing Snyk organization mapping from `updated` details.
- Supporting GitHub `created` on the Kafka endpoint.
- Accepting ADO/Azure Repos events through HTTP or Kafka.
- Adding application authentication, Kafka client libraries, Kafka publishing, or connector retry/DLQ policy.
- Changing Service Bus GitHub ingress or removing its existing `created` behavior.

## Decisions

### 1. Connector pushes to one transport-gated endpoint

`worker run` will expose `POST /github-events` only when `messaging.transport` is `kafka`. The `serviceBus` path will not start an HTTP listener. Other paths and methods return non-2xx and do not invoke lifecycle processing.

The endpoint accepts `application/json` and passes the exact request body bytes to the existing message parser and normalizer. It does not wrap the request in another transport envelope. ADO-shaped bodies are rejected because ADO remains Service Bus-only.

**Alternative rejected:** Implement `GitHubEventSource.receive/complete/dead_letter` as an HTTP polling client. The connector initiates delivery, so a pull client reverses the actual contract.

### 2. Synchronous 204 acknowledgement

The endpoint returns `204 No Content` only when initial message handling reaches a successful terminal outcome and all requested follow-ups have been durably scheduled on the Storage queue. Duplicate, intentionally ignored, and unmapped-scope outcomes count as successful processing because no retry can change them.

Malformed JSON returns 400, a currently unsupported payload or normalization failure returns 422, and unexpected or transient processing failures return 500 or 503. The connector treats all of those non-2xx responses as retryable; the distinctions exist for logs and diagnostics rather than connector control.

The shared processing path will return a transport-neutral outcome instead of assuming that every failure can be queue-dead-lettered. Service Bus maps an unrecoverable outcome to its dead-letter queue, a Storage queue follow-up maps it to the poison queue, and HTTP maps it to a non-2xx response.

**Alternative rejected:** Return 202 before processing. There is no durable inbound queue owned by this application, so early acknowledgement could lose a connector event if the process fails.

### 3. Storage queue remains follow-up-only

The endpoint schedules only `import_poll` and `lifecycle_deferred` bodies onto the existing Storage queue. It never copies an inbound GitHub body to that queue. The follow-up consumer continues to poison-settle invalid or exhausted Storage queue messages under the existing capability.

**Alternative rejected:** Use the Storage queue as an HTTP ingress buffer. Its contract and 64 KiB limit are intentionally limited to small internal follow-ups.

### 4. One process coordinates HTTP and follow-up consumption

On `kafka`, `worker run` initializes shared configuration, credentials, sync state, Snyk dependencies, and ignore reconciliation once. It then runs a production-capable HTTP server and the long-running Storage queue consumer concurrently. Failure of either long-running component causes the process to stop non-zero; shutdown signals stop both components and the reconciliation loop.

Request processing will use a bounded concurrency guard so connector bursts cannot create unbounded concurrent Snyk operations or bypass the existing pending-import limit. The bound will be configurable with a conservative default of one, preserving the current sequential receive-loop behavior.

**Alternative rejected:** Separate HTTP and follow-up commands in this change. That duplicates initialization and requires operators to deploy and coordinate two independently configured application processes.

### 5. Production ASGI server, with dependency review

Use a small ASGI application and production server rather than `http.server` or `wsgiref`, which are not suitable production servers. The implementation may use Starlette and Uvicorn unless repository review identifies a smaller maintained option with equivalent shutdown, request-limit, and test support.

Any new packages are added with `uv`, locked, scanned with Snyk Open Source, and rejected if they introduce high or critical vulnerabilities. Snyk Code is run on the implementation before merge.

### 6. Explicit HTTP configuration and private-network boundary

Kafka-mode configuration will include an HTTP bind host, port, maximum request-body bytes, and processing concurrency, with documented defaults and environment overrides. Invalid values fail startup. Service Bus mode ignores these settings.

The application does not authenticate requests. Deployment documentation requires no public ingress and customer-managed network controls that permit the event connector to reach the endpoint. TLS termination and network policy are deployment responsibilities.

**Alternative rejected:** Invent bearer-token or mTLS configuration. The customer explicitly selected no application authentication for this private route.

### 7. Payload evolution remains a separate change

This transport slice exercises payloads already understood by the worker. The endpoint returns non-2xx for `updated` and any revised connector shape until the subsequent fixture-driven normalization change is deployed. Kafka `created` is not added to the endpoint contract; existing Service Bus support is unchanged.

## Risks / Trade-offs

- [Unsupported `updated` events are retried and may block a Kafka partition] → Do not route revised connector payloads until the subsequent normalization change is deployed; connector retry/DLQ behavior remains customer-managed and the residual risk is accepted.
- [Processing succeeds but the HTTP response is lost] → Connector redelivery is handled by existing event-id and desired-state idempotency when the payload supplies a stable ID.
- [No application authentication permits calls from another compromised private workload] → Require no public route and customer-managed source/network restrictions; document the accepted trust boundary.
- [Synchronous Snyk work exceeds the connector timeout] → Keep initial work bounded, schedule long-running import polling on the Storage queue, and document that connector timeout must exceed the endpoint's initial processing time.
- [HTTP and Storage queue loops have different failure modes] → Supervise both in one process and fail the process when either component terminates unexpectedly.
- [Additional HTTP dependencies increase supply-chain surface] → Prefer minimal maintained packages and require lockfile, Snyk Open Source, and Snyk Code checks.

## Migration Plan

1. Ship configuration and HTTP ingress while preserving `serviceBus` as the default.
2. For Kafka deployments, provision the existing follow-up and poison queues, assign Storage Queue/Table roles, and create a private route from the event connector to the configured HTTP port.
3. Deploy the worker before configuring connector delivery, then point the connector at `POST /github-events`.
4. Do not send revised `updated` or other new connector shapes until the subsequent normalization change is deployed.
5. Roll back by restoring the prior image and disabling connector delivery. Service Bus deployments require no migration.

## Open Questions

- What request timeout does the event connector enforce? This affects the documented upper bound for synchronous initial processing but does not block the endpoint contract.
- What exact revised payload shapes and stable event IDs will the connector send for `updated`, `renamed`, `edited`, and `deleted`? This is intentionally deferred to the fixture-driven normalization change.

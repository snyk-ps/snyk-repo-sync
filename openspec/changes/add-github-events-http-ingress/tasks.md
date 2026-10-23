## 1. HTTP configuration and dependencies

- [ ] 1.1 Add Kafka-mode HTTP bind host, port, maximum request-body bytes, and processing-concurrency settings with documented defaults and environment overrides; ignore them on `serviceBus` and reject invalid values on `kafka`
- [ ] 1.2 Add unit tests for HTTP setting defaults, environment precedence, transport gating, bounds, and invalid values
- [ ] 1.3 Add the selected minimal ASGI framework/server with `uv`, update the lockfile, and run Snyk Open Source; do not keep dependencies that introduce high or critical issues

## 2. Transport-neutral processing outcomes

- [ ] 2.1 Refactor body-oriented message processing to return a transport-neutral completed or failed outcome while preserving Service Bus settlement and reason behavior
- [ ] 2.2 Map failed Storage queue follow-ups to existing poison settlement and map failed HTTP ingress processing to a non-2xx outcome without copying inbound GitHub bodies to the Storage queue
- [ ] 2.3 Ensure requested follow-ups are durably scheduled before HTTP processing can report success
- [ ] 2.4 Add unit tests for completed, duplicate, ignored, unmapped, invalid-message, invalid-normalization, Snyk-failure, and follow-up-scheduling-failure outcomes

## 3. GitHub events HTTP ingress

- [ ] 3.1 Implement the ASGI application with `POST /github-events`, JSON content handling, request-size enforcement, bounded processing concurrency, and 204 success only after synchronous processing completes
- [ ] 3.2 Return non-2xx without lifecycle side effects for wrong paths or methods, invalid JSON, ADO payloads, GitHub `created`, `updated` pending its contract, and other unsupported shapes
- [ ] 3.3 Add endpoint tests for existing `renamed`, `edited`, and `deleted` fixtures; duplicate/ignored success; 204-after-follow-up ordering; rejection cases; and injected dependency failures
- [ ] 3.4 Remove the pull-style `GitHubEventSource` startup seam and its unconditional Kafka-mode configuration error

## 4. Kafka-mode runtime

- [ ] 4.1 Start the HTTP server and Storage queue follow-up consumer concurrently under `worker run` when `messaging.transport` is `kafka`, without constructing a Service Bus client
- [ ] 4.2 Coordinate shutdown of the HTTP server, Storage queue consumer, and ignore reconciliation loop; exit non-zero if either Kafka-mode long-running component terminates unexpectedly
- [ ] 4.3 Add runtime tests proving `serviceBus` remains the default and starts no HTTP listener, while `kafka` starts both components and supervises component failure

## 5. Documentation and verification

- [ ] 5.1 Update `CONFIGURATION.md`, `INGESTION.md`, `README.md`, and `data/config.yaml.example` with `POST /github-events`, HTTP settings, 2xx acknowledgement/non-2xx retry semantics, private-network/no-auth boundary, and Storage queue follow-up routing
- [ ] 5.2 Document that Kafka `created` is excluded and that revised `updated`, `renamed`, `edited`, and `deleted` contracts, fixtures, normalization, and `updated` organization mapping are deferred; retain existing Service Bus guidance and recommendation
- [ ] 5.3 Run the complete unit and integration test suites plus repository lint/check commands
- [ ] 5.4 Run Snyk Code and confirm the change introduces no high-severity vulnerabilities

## 6. Archive

- [ ] 6.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/add-github-events-http-ingress/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive add-github-events-http-ingress` (or project equivalent) to fold deltas into canonical specs.

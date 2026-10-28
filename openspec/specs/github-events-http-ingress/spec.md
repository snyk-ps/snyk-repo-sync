# github-events-http-ingress Specification

## Purpose
Private `POST /github-events` ingress, synchronous processing and response semantics, transport gating, and the network/authentication boundary for event-connector delivery.
## Requirements
### Requirement: Kafka-only GitHub events endpoint
When `messaging.transport` is `kafka`, the application MUST expose `POST /github-events` for event-connector delivery of GitHub repository lifecycle events. The request body MUST be JSON and MUST be passed to lifecycle processing without a transport envelope. The application MUST NOT expose this endpoint when `messaging.transport` is `serviceBus`.

Methods other than POST and paths other than `/github-events` MUST return a non-2xx response and MUST NOT invoke lifecycle processing.

#### Scenario: Connector posts a GitHub event
- **WHEN** the application runs with `messaging.transport: kafka` and the event connector posts an already-supported GitHub body to `/github-events`
- **THEN** the application processes that body through the existing GitHub lifecycle path

#### Scenario: Service Bus remains queue-only
- **WHEN** the application runs with `messaging.transport: serviceBus`
- **THEN** it consumes the configured Service Bus queue and does not start the GitHub events HTTP listener

#### Scenario: Unsupported method
- **WHEN** a caller sends GET to `/github-events`
- **THEN** the application returns a non-2xx response and performs no lifecycle processing

### Requirement: Synchronous connector acknowledgement
The endpoint MUST process each request synchronously. It MUST return `204 No Content` only after initial lifecycle processing succeeds and every follow-up requested by that processing has been durably scheduled on the Azure Storage queue.

Duplicate, intentionally ignored, and unmapped-scope events MUST return 204 after completing without Snyk side effects. Malformed JSON, unsupported payloads, normalization failures, configuration failures, dependency failures, and unexpected failures MUST return non-2xx.

The event connector treats any 2xx response as acknowledgement and any non-2xx response as retryable. Retry, backoff, retry exhaustion, Kafka offset management, and connector dead-letter behavior MUST remain outside this application.

#### Scenario: Processing completes without a follow-up
- **WHEN** an accepted GitHub request completes initial processing and requests no follow-up
- **THEN** the endpoint returns 204

#### Scenario: Processing schedules an import poll
- **WHEN** initial processing requests an `import_poll` follow-up
- **THEN** the endpoint returns 204 only after that follow-up has been successfully written to the Storage queue

#### Scenario: Invalid JSON
- **WHEN** the connector posts a body that is not valid JSON
- **THEN** the endpoint returns a non-2xx response so the connector retries according to its policy

#### Scenario: Processing dependency fails
- **WHEN** Snyk, sync-state storage, or follow-up scheduling fails before request processing completes
- **THEN** the endpoint returns a non-2xx response and does not acknowledge the connector message

### Requirement: Kafka GitHub event boundary
The intended Kafka endpoint event set MUST be GitHub `updated`, `renamed`, `edited`, and `deleted`. GitHub `created` MUST NOT be part of this endpoint contract. The endpoint MUST process already-supported `renamed`, `edited`, and `deleted` payload shapes through the existing normalizer.

The endpoint MUST accept the parsed updated body in `data/fixtures/github_parsed_updated.json`. That body has top-level `repository` and `newPropertyValues` and no `action`. It is the import event for this contract. The endpoint MUST pass it to lifecycle processing. A successful import MUST return 204 under the synchronous acknowledgement requirement. The endpoint MUST NOT return 422 for that body.

ADO/Azure Repos payloads MUST return non-2xx and MUST NOT enter lifecycle processing on this endpoint.

#### Scenario: Existing renamed shape
- **WHEN** the connector posts an already-supported GitHub `renamed` payload
- **THEN** the endpoint processes the rename and returns 204 after successful processing

#### Scenario: Parsed updated body is the import
- **WHEN** the connector posts the `github_parsed_updated.json` body
- **THEN** the endpoint normalizes it for import and returns 204 after successful processing

#### Scenario: Created is not a Kafka endpoint event
- **WHEN** the connector posts a GitHub payload with `action: created`
- **THEN** the endpoint returns non-2xx and performs no create lifecycle action

#### Scenario: ADO payload posted
- **WHEN** the connector posts an ADO Event Grid or audit payload to `/github-events`
- **THEN** the endpoint returns non-2xx and performs no ADO lifecycle action

### Requirement: Private unauthenticated ingress
The `/github-events` endpoint MUST NOT require application-level authentication. Operator documentation MUST require the endpoint to have no public route and to be reachable by the event connector only through customer-managed private-network controls.

The application MUST support `http.bindHost` (default `0.0.0.0`), `http.port` (default `8080`), `http.maxRequestBodyBytes` (default `1048576`), and `http.processingConcurrency` (default `1`). Environment overrides `HTTP_BIND_HOST`, `HTTP_PORT`, `HTTP_MAX_REQUEST_BODY_BYTES`, and `HTTP_PROCESSING_CONCURRENCY` MUST take precedence when set.

The HTTP port MUST be between 1 and 65535, maximum request-body bytes MUST be positive, and processing concurrency MUST be between 1 and 100. Invalid Kafka-mode HTTP settings MUST fail startup clearly. HTTP settings MUST NOT become required for `serviceBus`.

#### Scenario: Connector reaches private endpoint
- **WHEN** the Kafka deployment has a customer-managed private route from the event connector to the configured application port
- **THEN** the connector can post without an application credential

#### Scenario: Oversized request
- **WHEN** a request exceeds the configured maximum body size
- **THEN** the endpoint returns non-2xx without invoking lifecycle processing

#### Scenario: Invalid Kafka HTTP configuration
- **WHEN** `messaging.transport` is `kafka` and an HTTP port or processing-concurrency value is invalid after config and environment merge
- **THEN** startup fails with a clear configuration error


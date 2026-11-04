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

### Requirement: HTTP failure details
Every non-2xx response from the GitHub events HTTP application MUST use `Content-Type: application/json` and a JSON object with string fields `failureKind`, `reason`, and `description`. `description` MUST be empty when no description is available. A `204` response MUST remain empty.

A failed `ProcessingOutcome` MUST use that outcome's `failure_kind`, `reason`, and `description`, and the endpoint MUST emit one error log containing those three values before returning the existing status for that kind. The log and the body MUST omit `SNYK_TOKEN` and authorization headers.

Boundary responses MUST use these fields:

- `400`: `failureKind` `invalid_message`, `reason` `InvalidJson`
- `404`: `failureKind` `request`, `reason` `NotFound`
- `405`: `failureKind` `request`, `reason` `MethodNotAllowed`
- `413`: `failureKind` `request`, `reason` `RequestTooLarge`
- `415`: `failureKind` `request`, `reason` `UnsupportedMediaType`
- `422` from the GitHub payload boundary: `failureKind` `invalid_message`, `reason` `UnsupportedPayload`

A follow-up scheduling failure MUST return 503 with `failureKind` `dependency` and `reason` `FollowUpSchedulingError`. An unexpected processing exception MUST return 500 with `failureKind` `processing` and `reason` `UnexpectedError`, and its `description` MUST omit the traceback.

The connector acknowledgement rule is unchanged: a 2xx response acknowledges the delivery, and any non-2xx response remains retryable from the status code.

#### Scenario: Snyk API failure
- **WHEN** processing a `/github-events` request fails with `failure_kind` `dependency`, `reason` `SnykApiError`, and a description of the failed Snyk request
- **THEN** the endpoint returns 503, the JSON body contains `failureKind` `dependency`, `reason` `SnykApiError`, and that description, and an error log contains those same three values without `SNYK_TOKEN`

#### Scenario: Invalid message outcome
- **WHEN** processing fails with `failure_kind` `invalid_message` or `invalid_normalization`
- **THEN** the endpoint returns 422 and the JSON body and error log contain that kind and reason

#### Scenario: Malformed JSON
- **WHEN** the connector posts a body that is not valid JSON
- **THEN** the endpoint returns 400 with `failureKind` `invalid_message` and `reason` `InvalidJson`, and it does not emit the processing-failure error log

#### Scenario: Follow-up scheduling fails
- **WHEN** initial processing requests a follow-up and the Storage queue write fails
- **THEN** the endpoint returns 503 with `failureKind` `dependency` and `reason` `FollowUpSchedulingError`

#### Scenario: Successful request
- **WHEN** processing completes and any required follow-up is scheduled
- **THEN** the endpoint returns 204 with an empty body and does not emit the processing-failure error log


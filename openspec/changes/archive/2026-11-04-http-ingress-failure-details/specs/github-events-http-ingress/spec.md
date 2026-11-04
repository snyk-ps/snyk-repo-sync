## ADDED Requirements

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

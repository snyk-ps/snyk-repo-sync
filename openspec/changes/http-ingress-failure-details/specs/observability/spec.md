## ADDED Requirements

### Requirement: HTTP ingress processing failure logs
A failed `ProcessingOutcome` on `POST /github-events` MUST emit a structured error log that includes `failure_kind`, `reason`, and `description`. The log MUST omit secrets, including `SNYK_TOKEN` and authorization headers.

#### Scenario: Dependency failure on GitHub HTTP ingress
- **WHEN** `/github-events` fails because the Snyk API rejects the request
- **THEN** the error log includes `failure_kind` `dependency` and the Snyk API failure description, and the token is absent

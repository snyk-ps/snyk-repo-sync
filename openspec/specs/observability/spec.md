## Purpose

Structured logging to Dynatrace and alerting on dead-letter queue and unrecoverable failures.
## Requirements
### Requirement: Dynatrace logging
The worker, webhook ingress, and scheduled jobs MUST emit structured operational logs to Dynatrace.

#### Scenario: Successful ADO repo sync
- **WHEN** an ADO repo lifecycle action completes
- **THEN** a structured log entry is emitted with `source`, scope id, repository id, event type, and outcome

#### Scenario: Successful GitHub repo sync
- **WHEN** a GitHub repo lifecycle action completes
- **THEN** a structured log entry is emitted with `source`, scope id, repository id, event type, and outcome

### Requirement: DLQ alerting via Dynatrace
When messages are dead-lettered or unrecoverable failures occur, the system MUST raise alerts in Dynatrace (not App Insights action groups in v1).

#### Scenario: Unmapped scope
- **WHEN** a message is processed for a scope with no entry in scope mapping config
- **THEN** Dynatrace receives a log or alert suitable for operator response per the `scope-mapping` capability

### Requirement: No secret leakage in logs
Logs MUST NOT contain Snyk tokens, ADO PATs, GitHub tokens or App credentials, webhook secrets, or other secrets.

#### Scenario: API error with authorization header
- **WHEN** logging an upstream HTTP failure
- **THEN** authorization headers and token values are redacted or omitted

### Requirement: Structured import lifecycle logging
The worker MUST emit structured logs for import lifecycle transitions: import triggered, import pending poll, import complete, import failed, pending import limit reached, and import job dead-letter after max retries. Logs MUST include `source`, scope id, repository id, event type, import job id, and outcome where applicable.

#### Scenario: Import pending poll
- **WHEN** an `import_poll` follow-up message is processed
- **THEN** a structured log entry is emitted with import job id and pending status

#### Scenario: Import complete without tagging
- **WHEN** an import job completes successfully in this slice
- **THEN** a structured log entry is emitted with outcome `import_complete` and `tagApplied=false`

#### Scenario: Import dead-letter after max retries
- **WHEN** import job polling exceeds max retries
- **THEN** a structured error log is emitted and Dynatrace receives an alert suitable for operator response


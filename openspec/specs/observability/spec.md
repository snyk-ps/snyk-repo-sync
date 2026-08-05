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

#### Scenario: Unknown scope DLQ
- **WHEN** a message is dead-lettered due to missing `_meta`
- **THEN** Dynatrace receives an alert suitable for operator response

### Requirement: No secret leakage in logs
Logs MUST NOT contain Snyk tokens, ADO PATs, GitHub tokens or App credentials, webhook secrets, or other secrets.

#### Scenario: API error with authorization header
- **WHEN** logging an upstream HTTP failure
- **THEN** authorization headers and token values are redacted or omitted

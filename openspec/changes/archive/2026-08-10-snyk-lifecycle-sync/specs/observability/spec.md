## ADDED Requirements

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

## ADDED Requirements

### Requirement: Structured project ignore migration logging
The worker MUST emit structured logs when a v1 project-ignore migration is skipped, succeeds, or fails. Each log MUST include `source`, scope id, repository id, `ignoreMigrationKind`, and outcome. A failure log MUST include the failure reason. Logs MUST NOT contain secrets or ignore reason text.

#### Scenario: Migration skipped
- **WHEN** a GitHub updated import finds no matching Azure DevOps target
- **THEN** a structured log records the skip and the GitHub import remains complete

#### Scenario: Migration succeeded
- **WHEN** v1 project ignores are copied onto the destination projects
- **THEN** a structured log records success with `ignoreMigrationKind`

#### Scenario: Migration failed
- **WHEN** the v1 ignore API returns an error during migration
- **THEN** a structured error log records the failure reason without secrets and is suitable for Dynatrace alerting

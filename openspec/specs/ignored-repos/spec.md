## Purpose

Ignore-list and name-prefix regex policy with scheduled deactivation of matching Snyk targets.

## Requirements

### Requirement: Ignore list source
Ignored repositories MUST be determined by a JSON file stored in the repository (path defined in operator config), persisted to sync state after successful retrieval.

#### Scenario: Successful ignore list load
- **WHEN** the scheduled job or worker retrieves the ignore-list JSON file
- **THEN** matching repository entries are stored in state for evaluation

#### Scenario: Ignore list retrieval failure
- **WHEN** the ignore-list JSON file cannot be retrieved
- **THEN** the failure is logged; retrieval failures MUST NOT silently disable ignore enforcement without operator visibility

### Requirement: Name-prefix regex filter
Operator configuration MUST support a regex that matches repository name prefixes; repositories matching the regex MUST be treated as ignored.

#### Scenario: Prefix regex match
- **WHEN** a repository name matches the configured prefix regex
- **THEN** the repo is ignored for import and eligible for scheduled deactivation if already synced

### Requirement: Scheduled deactivation job
A scheduled job MUST deactivate Snyk targets for repositories that match ignore-list entries or the prefix regex.

#### Scenario: Previously synced repo added to ignore list
- **WHEN** a scheduled run finds an active synced repo that now matches ignore policy
- **THEN** the corresponding Snyk target is deactivated and state is updated

### Requirement: No detection hook for ignores
Ignore policy MUST NOT rely on provider event detection; enforcement uses persisted list/regex plus the scheduled job (and worker short-circuit on inbound events).

#### Scenario: Ignored repo receives create event
- **WHEN** ADO or GitHub emits repo-created for an ignored repo
- **THEN** the worker does not import; the scheduled job remains responsible for cleaning up any stale active targets

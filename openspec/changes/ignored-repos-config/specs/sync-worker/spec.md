## MODIFIED Requirements

### Requirement: Ignored repo short-circuit
Before executing repo lifecycle actions, the worker MUST evaluate ignore policy (explicit entries and name patterns) loaded from `ignoredRepos.path` and MUST NOT import repos that match. Ignore policy MUST be evaluated immediately on every lifecycle event type (create, rename, default branch change).

When a matching repository has an active Snyk target, the worker MUST remove it per `snyk.targetRemoval.onIgnore` before completing the message without import.

#### Scenario: Ignored repo created
- **WHEN** a repo-created event matches the ignore policy
- **THEN** the worker completes the message without import or tag actions

#### Scenario: Ignored repo renamed
- **WHEN** a repo-renamed event produces a new name matching ignore policy
- **THEN** the worker removes the existing target per `onIgnore`, does not import the new name, and completes the message

#### Scenario: Ignored repo default branch changed
- **WHEN** a default-branch-changed event matches ignore policy
- **THEN** the worker removes the existing target per `onIgnore` if active, does not re-import, and completes the message

## ADDED Requirements

### Requirement: Ignore policy startup load
When `ignoredRepos.path` is configured, the worker MUST load and validate the ignore-policy file at startup. The worker MUST run a background reconciliation loop at `ignoredRepos.reconciliationIntervalMinutes` (default 15).

#### Scenario: Worker starts with ignore policy configured
- **WHEN** the worker starts with a valid `ignoredRepos.path` and policy file
- **THEN** ignore policy is loaded, persisted to sync state, and reconciliation is scheduled

#### Scenario: Missing policy file at startup
- **WHEN** `ignoredRepos.path` is set and the policy file does not exist at startup
- **THEN** the worker exits with a clear configuration error

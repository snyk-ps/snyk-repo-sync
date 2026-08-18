## MODIFIED Requirements

### Requirement: Ignore list persistence
When the ignore-policy file is successfully loaded, its parsed contents MUST be persisted in sync state for use by the worker and background reconciliation loop.

#### Scenario: Ignore policy refresh
- **WHEN** the reconciliation loop reads an updated ignore-policy file
- **THEN** the persisted ignore policy in sync state is updated

#### Scenario: Initial policy load at startup
- **WHEN** the worker starts with `ignoredRepos.path` configured and the policy file loads successfully
- **THEN** the parsed policy is persisted to sync state before message processing begins

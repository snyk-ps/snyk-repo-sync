## Purpose

Ignore-policy file (YAML/JSON) with explicit repository entries and name pattern groups; event-time enforcement and background reconciliation for matching Snyk targets.
## Requirements
### Requirement: Ignore list source
Ignored repositories MUST be determined by an operator ignore-policy file (YAML or JSON, UTF-8) at the path configured in `ignoredRepos.path`. The path MAY be relative to the directory containing the operator config file or absolute. The file MUST be co-located with operator config in production (same Azure Files mount as `config.yaml`).

When `ignoredRepos.path` is unset, ignore enforcement MUST be disabled. When set and the file is missing at first worker startup, the worker MUST exit with a clear configuration error.

The policy file MUST support explicit `repos` entries and `patterns` groups. Loaded policy MUST be persisted to sync state after successful retrieval.

#### Scenario: Successful ignore policy load
- **WHEN** the worker or reconciliation loop loads a valid ignore-policy file
- **THEN** matching repository entries and compiled patterns are available for evaluation and persisted to sync state

#### Scenario: Ignore policy retrieval failure during reconciliation
- **WHEN** the ignore-policy file cannot be read during a reconciliation cycle
- **THEN** the failure is logged with structured context and the worker continues using the last successfully persisted policy

#### Scenario: Ignore policy path not configured
- **WHEN** `ignoredRepos.path` is absent from operator config
- **THEN** no repository is treated as ignored by policy

### Requirement: Scheduled deactivation job
The worker MUST run a background reconciliation loop at the interval configured by `ignoredRepos.reconciliationIntervalMinutes` (default 15 minutes). Each cycle MUST reload the ignore-policy file, persist successful loads to sync state, scan active synced repository rows, and remove targets for repositories matching ignore policy per `snyk.targetRemoval.onIgnore` (default deactivate).

#### Scenario: Previously synced repo added to ignore list
- **WHEN** a reconciliation cycle finds an active synced repo that now matches ignore policy
- **THEN** the corresponding Snyk target is removed per `snyk.targetRemoval.onIgnore` and repository state is updated

#### Scenario: Reconciliation interval default
- **WHEN** `ignoredRepos.reconciliationIntervalMinutes` is unset
- **THEN** reconciliation runs every 15 minutes

#### Scenario: Reconciliation uses persisted policy on reload failure
- **WHEN** policy file reload fails during reconciliation
- **THEN** the cycle uses the last persisted policy and logs the failure

### Requirement: No detection hook for ignores
Ignore policy MUST NOT rely on provider event detection alone; enforcement uses the persisted policy, immediate event-time evaluation, and background reconciliation.

#### Scenario: Ignored repo receives create event
- **WHEN** ADO or GitHub emits repo-created for an ignored repo
- **THEN** the worker does not import; background reconciliation remains responsible for cleaning up any stale active targets not handled at event time

#### Scenario: Policy added without lifecycle event
- **WHEN** an operator adds a repository to the explicit ignore list and no lifecycle event occurs
- **THEN** background reconciliation removes the active target within the configured interval

### Requirement: Explicit repository ignore entries
Each entry in the policy file `repos` list MUST include `source`, `owner`, and `name`. `source` MUST be `azure-repos` or `github`. Additional fields on an entry MAY be present for operator context and MUST NOT affect matching.

Duplicate `(source, owner, name)` tuples MUST cause startup failure.

For ADO lifecycle events, explicit entries with `source: azure-repos` MUST match when `owner` equals the normalized ADO project name and `name` equals the repository name. For GitHub lifecycle events, explicit entries with `source: github` MUST match when `owner` equals the GitHub org login and `name` equals the repository name. Matching MUST be case-sensitive.

#### Scenario: ADO explicit ignore match
- **WHEN** an ADO lifecycle event is evaluated against an entry with `source: azure-repos`, matching `owner` and `name`
- **THEN** the repository is ignored

#### Scenario: GitHub explicit ignore with wrong source
- **WHEN** a GitHub lifecycle event is evaluated against an entry with `source: azure-repos` and matching owner and name
- **THEN** the entry does NOT match

#### Scenario: Duplicate explicit entry
- **WHEN** the policy file contains two `repos` entries with the same `source`, `owner`, and `name`
- **THEN** the worker exits at startup with a clear configuration error

### Requirement: Name pattern ignore groups
The policy file MUST support `patterns` groups. Each group MUST include `id`, `filterType`, and a non-empty `patterns` list. Allowed `filterType` values: `regex`, `prefix`, `suffix`. Patterns MUST be matched against repository name only (not owner). A repository matching any pattern in any group MUST be treated as ignored.

#### Scenario: Prefix pattern match
- **WHEN** a repository name starts with a configured prefix pattern
- **THEN** the repo is ignored for import and eligible for target removal if already synced

#### Scenario: Suffix pattern match
- **WHEN** a repository name ends with a configured suffix pattern
- **THEN** the repo is ignored for import and eligible for target removal if already synced

#### Scenario: Regex pattern match
- **WHEN** a repository name matches a configured regex pattern via search
- **THEN** the repo is ignored for import and eligible for target removal if already synced

#### Scenario: Invalid regex at load
- **WHEN** a pattern group contains an invalid regex and `filterType` is `regex`
- **THEN** the worker exits at startup with a clear configuration error naming the group `id`

### Requirement: Event-time ignore enforcement
Ignore policy MUST be evaluated immediately on every lifecycle event (repo created, renamed, default branch changed) before import or re-import actions. Ignored repositories MUST NOT be imported.

When a lifecycle event matches ignore policy and an active Snyk target exists, the worker MUST remove the target per `snyk.targetRemoval.onIgnore` on that event.

#### Scenario: Rename into ignore policy
- **WHEN** a repo-renamed event produces a new name that matches ignore policy
- **THEN** the worker does not import the new name and removes the existing target per `snyk.targetRemoval.onIgnore` on that event

#### Scenario: Default branch change on ignored repo
- **WHEN** a default-branch-changed event is processed for a repository matching ignore policy
- **THEN** the worker completes without re-import and removes the existing target per `snyk.targetRemoval.onIgnore` if active


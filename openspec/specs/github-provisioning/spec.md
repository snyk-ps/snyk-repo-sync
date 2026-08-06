## Purpose

Provision GitHub organization webhooks so repository lifecycle events reach the webhook ingress endpoint.

## Requirements

### Requirement: Org webhook registration
Repository lifecycle webhooks MUST be registered at the GitHub organization level for events: repository created, renamed, deleted, and edited (default branch).

#### Scenario: Initial org setup
- **WHEN** an operator runs the provisioning script or follows the documented procedure for a GitHub org
- **THEN** the required org webhooks point at the configured ingress URL with the correct secret

### Requirement: Manual org onboarding
Automated GitHub org onboarding is out of scope; operators MUST manually create `_meta` state and Snyk org/integration before events are processed.

#### Scenario: Events before onboarding
- **WHEN** webhooks arrive for an org with no `_meta` row
- **THEN** the worker dead-letters and alerts per sync-worker unknown-scope handling

### Requirement: GitHub credential usage
GitHub App or PAT credentials used for webhook registration and optional metadata enrichment MUST be stored in Key Vault or container secrets and MUST NOT be logged.

#### Scenario: Provisioning or enrichment API call
- **WHEN** the system calls the GitHub REST API
- **THEN** credentials are retrieved from the configured secret store without logging token values

### Requirement: Optional metadata enrichment client
When webhook payloads lack fields required by downstream handlers, an optional GitHub integration client MAY call the GitHub REST or App API to enrich metadata before or during worker processing.

#### Scenario: Missing metadata in webhook
- **WHEN** the worker needs repository metadata not present in the normalized event
- **THEN** it may call GitHub API using configured credentials without logging secrets

### Requirement: Default branch detection mode
For GitHub, default branch changes MUST be detected via the `repository` webhook with action `edited`; reconciliation polling is out of scope for v1.

#### Scenario: Branch change without webhook
- **WHEN** default branch changes but no webhook is delivered
- **THEN** the service does not automatically re-import until a webhook event is received

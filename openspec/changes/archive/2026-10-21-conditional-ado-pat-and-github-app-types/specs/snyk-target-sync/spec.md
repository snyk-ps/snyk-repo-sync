## MODIFIED Requirements

### Requirement: GitHub integration-scoped target lookup
For GitHub lifecycle events, REST target lookup and import MUST use the Snyk integration type resolved from scope mapping for the org login (`github`, `github-cloud-app`, `github-server-app`, or `github-enterprise`). Target list queries MUST filter by that integration's `source_types` so targets imported via other SCM integrations or CLI in the same Snyk org are not selected for deactivation or deletion.

GitHub import MUST use the integration id resolved by matching the same integration type returned by scope mapping. It MUST NOT use `azure-repos`, `github-cloud`, or `github-server` as the GitHub integration or target source type.

#### Scenario: GitHub import uses mapped integration type
- **WHEN** a mapped GitHub org triggers repository import
- **THEN** the import request uses the integration id resolved for the GitHub integration type from scope mapping

#### Scenario: GitHub Cloud App target lookup is scoped
- **WHEN** the worker resolves a target id for an org mapped under `github-cloud-app`
- **THEN** it queries targets with `source_types=github-cloud-app` plus the owner login, repository name, and branch

#### Scenario: GitHub Server App target lookup is scoped
- **WHEN** the worker resolves a target id for an org mapped under `github-server-app`
- **THEN** it queries targets with `source_types=github-server-app` plus the owner login, repository name, and branch

#### Scenario: GitHub target removal lookup scoped
- **WHEN** the worker resolves a target id before rename or default-branch re-import for a GitHub event
- **THEN** it queries targets with the mapped GitHub `source_types` and owner login plus repository name and branch

## ADDED Requirements

### Requirement: GitHub integration-scoped target lookup
For GitHub lifecycle events, REST target lookup and import MUST use the Snyk integration type resolved from scope mapping for the org login (`github`, `github-cloud`, `github-server`, or `github-enterprise`). Target list queries MUST filter by that integration's `source_types` so targets imported via other SCM integrations or CLI in the same Snyk org are not selected for deactivation or deletion.

GitHub import MUST pass the same integration type as `source_types` (or equivalent) to the Snyk Import API, not `azure-repos`.

#### Scenario: GitHub import uses mapped integration type
- **WHEN** a mapped GitHub org triggers repository import
- **THEN** the import request uses the resolved GitHub integration id and GitHub source type from scope mapping

#### Scenario: GitHub target removal lookup scoped
- **WHEN** the worker resolves a target id before rename or default-branch re-import for a GitHub event
- **THEN** it queries targets with the mapped GitHub `source_types` and owner login plus repository name and branch

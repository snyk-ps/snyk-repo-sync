## ADDED Requirements

### Requirement: REST Targets API includes empty targets
When resolving a Snyk target id via `GET /rest/orgs/{org_id}/targets`, the worker MUST pass `exclude_empty=false`. The Snyk API default (`exclude_empty=true`) excludes targets with no projects and MUST NOT be relied upon for target id lookup after import or before removal when state has no stored target id.

#### Scenario: Empty target after successful import
- **WHEN** the import job completes successfully and the Snyk target exists with zero projects
- **THEN** the worker resolves and persists `snykTargetId` and sets `importStatus=complete`

#### Scenario: Empty target before removal lookup
- **WHEN** target removal requires REST lookup, `snykTargetId` is empty in sync state, and the target has zero projects
- **THEN** the worker resolves the target id via the REST Targets API including empty targets

#### Scenario: Non-empty target unchanged
- **WHEN** the import job completes successfully and the target has one or more projects
- **THEN** the worker continues to resolve the target id via the REST Targets API and persists it before marking import complete

## ADDED Requirements

### Requirement: Org name match logs
A unique Snyk org-name match MUST be logged at info with marker `scope_mapping_org_name`, the candidate string, the matched org name, the matched org id, source, scope id, repository id, and event id. An ambiguous org-name match MUST be logged at warning with marker `scope_mapping_org_name_ambiguous` and those same identifiers except the matched org id. Both logs MUST omit `scope_mapping_default` and `scope_mapping_unmapped`. Logs MUST NOT include secrets.

#### Scenario: Unique org name match
- **WHEN** scope resolution selects one Snyk org by name
- **THEN** Dynatrace receives an info log with marker `scope_mapping_org_name`, the candidate, and the matched org name and id

#### Scenario: Ambiguous org name match
- **WHEN** two or more Snyk orgs match the candidate after normalization
- **THEN** Dynatrace receives a warning log with marker `scope_mapping_org_name_ambiguous` and no Snyk side effects are performed

## MODIFIED Requirements

### Requirement: Scope resolution warning logs
When scope resolution uses `defaultSnykOrgId` after static mapping, org-name match, and the stored org id have missed, the worker MUST emit a warning log containing the marker `scope_mapping_default`, `source`, scope id, repository id, event id, lookup key, and the extracted property value when one was returned. When those same steps miss and no default org is configured, the worker MUST emit a warning log containing the marker `scope_mapping_unmapped` and those same identifiers. A static match, a unique org-name match, and a stored-org match MUST be logged at info and MUST omit both markers. Logs MUST NOT include secrets.

#### Scenario: Default org fallback
- **WHEN** an event misses static mapping, org-name match, and the stored org id, and `defaultSnykOrgId` is configured
- **THEN** Dynatrace receives a warning log with marker `scope_mapping_default` and the event identifiers

#### Scenario: Unmapped extracted property
- **WHEN** a GitHub updated event extracts a property value that misses static mapping, org-name match, and the stored org id, and no default org is configured
- **THEN** Dynatrace receives a warning log with marker `scope_mapping_unmapped` and that extracted value

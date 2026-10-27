## ADDED Requirements

### Requirement: Scope resolution warning logs
When scope resolution uses `defaultSnykOrgId`, the worker MUST emit a warning log containing the marker `scope_mapping_default`, `source`, scope id, repository id, event id, lookup key, and the extracted property value when one was returned. When scope resolution finds no mapping and no default org, the worker MUST emit a warning log containing the marker `scope_mapping_unmapped` and those same identifiers. Explicit mapping matches MUST be logged at info and MUST omit both markers. Logs MUST NOT include secrets.

#### Scenario: Default org fallback
- **WHEN** an event has no matching scope entry and `defaultSnykOrgId` is configured
- **THEN** Dynatrace receives a warning log with marker `scope_mapping_default` and the event identifiers

#### Scenario: Unmapped extracted property
- **WHEN** a GitHub updated event extracts a property value that has no `propertyValue` entry and no default org is configured
- **THEN** Dynatrace receives a warning log with marker `scope_mapping_unmapped` and that extracted value

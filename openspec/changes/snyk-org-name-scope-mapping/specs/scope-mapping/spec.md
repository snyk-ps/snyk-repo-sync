## ADDED Requirements

### Requirement: Snyk org name match
An integration section MAY be a list of static entries or a mapping with optional `entries` and optional `matchSnykOrgName`. `entries` MUST follow the same lookup-key, duplicate, and `snykIntegrationId` rules as a list section. `matchSnykOrgName` MUST include boolean `enabled` and boolean `normalize`. A missing or non-boolean value, or any other key under the section mapping or under `matchSnykOrgName`, MUST cause startup failure.

`enabled: false` MUST leave org-name matching off and MUST NOT call the Snyk group API. `enabled: true` MUST require a non-empty `scopeMapping.snykGroupId`. At most one GitHub integration section and at most one `azure-repos` section MAY set `enabled: true`. A second enabled section for the same provider MUST cause startup failure. The enabling section key MUST be the Snyk integration type for an org-name match. An object section MUST count as a configured integration type when `entries` is empty.

When `enabled` is true and static resolution misses, the worker MUST compare the candidate string to organization names from `GET /v1/group/{groupId}/orgs`. The candidate is the extracted property when the extractor returns a non-empty value, and the ADO project name or GitHub organization login when it does not. The worker MUST trim both sides. `normalize: false` MUST require exact equality after trimming. `normalize: true` MUST apply Unicode NFKD, remove nonspacing marks (category `Mn`), and casefold both sides before equality. The worker MUST skip group org entries that omit `id` or `name`.

The worker MUST cache the group org list in process memory and MUST refresh it when the cache is older than 15 minutes. A static match MUST NOT call the group API.

One matching org MUST resolve that org id and the enabling section's integration type. Zero matches MUST continue. Two or more matches MUST stop resolution, MUST NOT write a Snyk org id to sync state, and MUST NOT perform Snyk side effects. A group-list API failure MUST fail the message the same way as other Snyk API failures and MUST NOT continue to the stored org id or `defaultSnykOrgId`.

Org-name match and stored-org resolution MUST obtain the integration id by listing integrations for the resolved org and integration type. They MUST NOT read `snykIntegrationId` from sync state.

#### Scenario: Exact org name match
- **WHEN** `github-enterprise.matchSnykOrgName.enabled` is true, `normalize` is false, no static entry matches the candidate `Platform`, and the group org list contains one org named `Platform`
- **THEN** the worker resolves that org id and uses `github-enterprise` for integration lookup

#### Scenario: Normalized org name match
- **WHEN** `normalize` is true and the candidate is `Systèmes Centraux` and one group org is named `systemes centraux`
- **THEN** the worker resolves that org id

#### Scenario: Normalize leaves punctuation significant
- **WHEN** `normalize` is true and the candidate is `Systemes Centraux` and the only group org is named `Systemes-Centraux`
- **THEN** org-name match finds no org

#### Scenario: Name match disabled
- **WHEN** `matchSnykOrgName.enabled` is false and no static entry matches
- **THEN** the worker does not call the group API

#### Scenario: Ambiguous normalized names
- **WHEN** `normalize` is true and two group orgs casefold to the same name as the candidate
- **THEN** the worker logs `scope_mapping_org_name_ambiguous`, writes no Snyk org id, and performs no Snyk side effects

#### Scenario: Group list failure
- **WHEN** org-name match is enabled, static resolution misses, and the group org list call fails
- **THEN** the worker fails the message as a Snyk API failure and does not use a stored org id or `defaultSnykOrgId`

#### Scenario: Enabled without group id
- **WHEN** any section sets `matchSnykOrgName.enabled` to true and `scopeMapping.snykGroupId` is absent
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Missing enabled boolean
- **WHEN** a section contains `matchSnykOrgName` without a boolean `enabled`
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Two GitHub sections enable name match
- **WHEN** `github` and `github-enterprise` both set `matchSnykOrgName.enabled` to true
- **THEN** the worker exits at startup with a clear configuration error

### Requirement: Scope resolution order
The worker MUST resolve a scope by stopping at the first success in this order: static mapping, Snyk org-name match, non-empty `snykOrgId` on the repository sync-state row, then `defaultSnykOrgId` when configured.

Static mapping MUST use `propertyValue` when the extractor returns a non-empty value and MUST use `orgName` or `projectName` when it does not. A stored-org success MUST use that row's `snykIntegrationType`. Lifecycle processing, import polling, and ignore reconciliation MUST use this order. The worker MUST read the repository row before resolution so the stored org id is available.

When resolution succeeds, every later upsert of that repository row MUST persist the resolved `snykOrgId` and `snykIntegrationType`, including when they differ from the stored pair. An unmapped scope, an ambiguous org-name match, and a group-list failure MUST NOT write those properties.

#### Scenario: Static row wins
- **WHEN** a `propertyValue` entry matches the extracted candidate and org-name match is enabled
- **THEN** the worker uses the static entry's org id and does not call the group API

#### Scenario: Stored org after static and name match miss
- **WHEN** no static entry matches, org-name match finds no org, and the repository row has a non-empty `snykOrgId` and `snykIntegrationType`
- **THEN** the worker uses that stored pair

#### Scenario: Default org is last
- **WHEN** static mapping misses, org-name match is off, the repository row has no `snykOrgId`, and `defaultSnykOrgId` is configured
- **THEN** the worker uses `defaultSnykOrgId` and the default integration type for that provider

#### Scenario: Existing row without stored org
- **WHEN** a repository row written before this change has no `snykOrgId` property and static mapping and org-name match both miss
- **THEN** resolution continues to `defaultSnykOrgId` or leaves the scope unmapped

#### Scenario: Successful resolution is persisted
- **WHEN** resolution succeeds and the worker upserts the repository row
- **THEN** the upsert includes the resolved `snykOrgId` and `snykIntegrationType`

## MODIFIED Requirements

### Requirement: Config-based scope to Snyk org mapping
Operators MUST declare scope-to-Snyk-org mappings in operator config (`config.yaml`). ADO name mappings MUST use ADO project name as the lookup key under the `azure-repos` integration type section. GitHub name mappings MUST use GitHub organization name (login) as the lookup key under a GitHub integration type section (`github`, `github-cloud-app`, `github-server-app`, or `github-enterprise`).

ADO and GitHub sections MAY also contain `propertyValue` entries. A `propertyValue` entry maps one extracted property string to a Snyk org id. Each list entry MUST set exactly one lookup key: `projectName` or `propertyValue` under `azure-repos`, and `orgName` or `propertyValue` under a GitHub section. A `propertyValue` entry for a provider that has no extractor MUST cause startup failure. Duplicate `propertyValue` keys within a provider MUST cause startup failure.

The worker MUST load and validate scope mapping entries at startup. Each mapping entry MUST include a non-empty `snykOrgId`. Duplicate `projectName` or `orgName` lookup keys within a source MUST cause startup failure. Legacy top-level key `ado` MUST be rejected at startup.

When a provider extractor returns a non-empty value, the static step MUST consult only `propertyValue` entries for that provider. It MUST NOT use `orgName` or `projectName` for that event. A static miss MUST continue with org-name match, the stored org id, and `defaultSnykOrgId` in that order. When the extractor returns no value, the static step MUST resolve `orgName` or `projectName` as before.

#### Scenario: Mapped ADO project
- **WHEN** the worker processes an ADO event for a project name present in `scopeMapping.azure-repos` and the ADO extractor returns no value
- **THEN** it resolves the target Snyk organization id from that `projectName` entry

#### Scenario: Mapped GitHub org
- **WHEN** the worker processes a GitHub event for an org name present in a configured GitHub integration type section and the GitHub extractor returns no value
- **THEN** it resolves the target Snyk organization id from that `orgName` entry

#### Scenario: Mapped GitHub property value
- **WHEN** the GitHub extractor returns `sample-project` and a GitHub section contains `propertyValue: sample-project`
- **THEN** it resolves the target Snyk organization id from that entry and does not consult `orgName` rows

#### Scenario: Extracted value misses property map
- **WHEN** the GitHub extractor returns a non-empty value that has no `propertyValue` entry and an `orgName` entry exists for the repository's organization login
- **THEN** the worker does not use the `orgName` entry and continues with org-name match, the stored org id, and `defaultSnykOrgId`

#### Scenario: Invalid duplicate ADO project name
- **WHEN** operator config contains two `scopeMapping.azure-repos` entries with the same `projectName`
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Legacy ADO scope mapping key
- **WHEN** operator config contains `scopeMapping.ado`
- **THEN** the worker exits at startup with a clear configuration error directing operators to `azure-repos`

#### Scenario: Property value without extractor
- **WHEN** a GitHub section contains `propertyValue` and `propertyExtractors.github` is absent
- **THEN** the worker exits at startup with a clear configuration error

### Requirement: Snyk integration type as scope mapping section key
Scope mapping sections MUST be keyed by Snyk integration type, not provider source names. Allowed top-level keys under `scopeMapping` (other than `defaultSnykOrgId`, `propertyExtractors`, and `snykGroupId`) are:

| Section key | Provider source | Entry shape |
| ----------- | --------------- | ----------- |
| `azure-repos` | ADO | `projectName` or `propertyValue`, `snykOrgId`, optional `snykIntegrationId` |
| `github` | GitHub | `orgName` or `propertyValue`, `snykOrgId`, optional `snykIntegrationId` |
| `github-cloud-app` | GitHub | same as `github` |
| `github-server-app` | GitHub | same as `github` |
| `github-enterprise` | GitHub | same as `github` |

Each section value MUST be either a list of those entries or a mapping whose static entries live under `entries`. The integration type used for Snyk API lookup MUST be the section key for a static or org-name match. Unknown section keys, including `github-cloud` and `github-server`, MUST cause startup failure.

When `defaultSnykOrgId` is used, the worker MUST use `azure-repos` for ADO events. For GitHub events it MUST use `github` unless exactly one GitHub integration type section is configured, in which case that type MUST be used. That default integration type applies only to `defaultSnykOrgId` resolution.

#### Scenario: ADO entry under azure-repos section
- **WHEN** an ADO scope mapping entry is listed under `scopeMapping.azure-repos`
- **THEN** the worker uses `azure-repos` for integration lookup

#### Scenario: GitHub entry under github-enterprise section
- **WHEN** a GitHub scope mapping entry is listed under `scopeMapping.github-enterprise`
- **THEN** the worker resolves the integration whose Snyk type is `github-enterprise`

#### Scenario: GitHub Cloud App section
- **WHEN** a GitHub org mapping is listed under `scopeMapping.github-cloud-app`
- **THEN** the worker uses `github-cloud-app` for Snyk integration lookup

#### Scenario: GitHub Server App section
- **WHEN** a GitHub org mapping is listed under `scopeMapping.github-server-app`
- **THEN** the worker uses `github-server-app` for Snyk integration lookup

#### Scenario: Obsolete GitHub Cloud key
- **WHEN** operator config contains `scopeMapping.github-cloud`
- **THEN** the worker exits at startup with a clear error that lists `github-cloud-app` as an allowed key

#### Scenario: Obsolete GitHub Server key
- **WHEN** operator config contains `scopeMapping.github-server`
- **THEN** the worker exits at startup with a clear error that lists `github-server-app` as an allowed key

#### Scenario: Invalid top-level scope mapping key
- **WHEN** operator config contains `scopeMapping.ado` or an unsupported integration type key
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Property extractor key is reserved
- **WHEN** operator config contains `scopeMapping.propertyExtractors` with a valid `github` or `azure-repos` extractor
- **THEN** the worker accepts the key and does not treat it as an integration type

#### Scenario: Group id key is reserved
- **WHEN** operator config contains a non-empty `scopeMapping.snykGroupId`
- **THEN** the worker accepts the key and does not treat it as an integration type

### Requirement: Unmapped scope handling
When static mapping, org-name match, and the stored org id all miss, the worker MUST log a warning and MUST NOT dead-letter the message. Configuration MAY specify an optional default Snyk organization id.

The applicable lookup key is the extracted property value when the provider extractor returns a non-empty value, and the ADO project name or GitHub organization login when it does not.

When `defaultSnykOrgId` is configured, the worker MUST use that Snyk organization and MUST log a warning that includes a stable `scope_mapping_default` marker, source, scope id, repository id, event id, lookup key, and the extracted value when present. When `defaultSnykOrgId` is not configured, the worker MUST log a warning that includes a stable `scope_mapping_unmapped` marker and those same identifiers, and MUST NOT perform Snyk side effects.

An explicit `propertyValue`, `orgName`, or `projectName` match, a unique org-name match, and a stored-org match MUST be logged at info and MUST NOT use the warning markers.

#### Scenario: Unmapped ADO project without default
- **WHEN** an ADO event arrives for a project name with no static mapping, org-name match finds no org, the repository row has no `snykOrgId`, and no default org is configured
- **THEN** the worker logs `scope_mapping_unmapped` and does not perform Snyk side effects

#### Scenario: Unmapped scope with default org
- **WHEN** an ADO or GitHub event misses static mapping and org-name match, the repository row has no `snykOrgId`, and `defaultSnykOrgId` is configured
- **THEN** the worker uses the default Snyk organization, uses the default integration type for the provider source, and logs `scope_mapping_default`

#### Scenario: Unmapped extracted property with default org
- **WHEN** the GitHub extractor returns a value with no `propertyValue` entry, org-name match finds no org, the repository row has no `snykOrgId`, and `defaultSnykOrgId` is configured
- **THEN** the worker imports into the default Snyk organization and the warning includes the extracted value

#### Scenario: Unmapped extracted property without default
- **WHEN** the GitHub extractor returns a value with no `propertyValue` entry, org-name match finds no org, the repository row has no `snykOrgId`, and no default org is configured
- **THEN** the worker logs `scope_mapping_unmapped` and does not perform Snyk side effects

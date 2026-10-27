## ADDED Requirements

### Requirement: Provider property extractor
Operators MAY configure `scopeMapping.propertyExtractors` with at most one extractor for `github` and at most one extractor for `azure-repos`. Each configured extractor MUST include non-empty `collectionPath`, `matchField`, `matchValue`, and `valueField`.

`collectionPath` MUST be a dotted path of non-empty object keys from the received JSON root to an array of objects. The worker MUST reject paths that contain empty segments, `..`, brackets, or filter syntax at startup. Unknown `propertyExtractors` keys MUST cause startup failure.

The worker MUST select array elements whose `matchField` equals `matchValue` and MUST read `valueField`. A missing path, a missing matching element, or a null or blank matched value MUST yield no extracted value. Two matching elements with the same non-empty value MUST yield that value. Two matching elements with different non-empty values MUST fail the message as invalid normalization. A present path whose intermediate or final node has the wrong JSON type MUST fail the message as invalid normalization.

#### Scenario: GitHub sample property extracted
- **WHEN** `propertyExtractors.github` uses `collectionPath: data.newPropertyValues`, `matchField: property_name`, `matchValue: azure-devops-project`, and `valueField: value`, and the message contains that array element with value `sample-project`
- **THEN** scope resolution uses `sample-project` as the extracted lookup value

#### Scenario: Existing fixture has no property path
- **WHEN** a current GitHub raw webhook or parsed lifecycle fixture is processed and the configured collection path is absent
- **THEN** extraction yields no value and resolution continues with the GitHub organization login

#### Scenario: Conflicting property values
- **WHEN** two array elements match the configured field and name and their non-empty values differ
- **THEN** the worker fails the message as invalid normalization and does not perform Snyk side effects

### Requirement: Property value entries use their section integration type
A `propertyValue` entry MUST live under an integration-type section. The worker MUST use that section key as the Snyk integration type. Optional `snykIntegrationId` on a `propertyValue` entry MUST follow the same non-empty and API-fallback rules as other scope entries.

#### Scenario: GitHub property value under github-cloud-app
- **WHEN** `sample-project` is listed as `propertyValue` under `scopeMapping.github-cloud-app` and the GitHub extractor returns `sample-project`
- **THEN** the worker resolves that entry's Snyk org id and uses `github-cloud-app` for integration lookup

## MODIFIED Requirements

### Requirement: Config-based scope to Snyk org mapping
Operators MUST declare scope-to-Snyk-org mappings in operator config (`config.yaml`). ADO name mappings MUST use ADO project name as the lookup key under the `azure-repos` integration type section. GitHub name mappings MUST use GitHub organization name (login) as the lookup key under a GitHub integration type section (`github`, `github-cloud-app`, `github-server-app`, or `github-enterprise`).

ADO and GitHub sections MAY also contain `propertyValue` entries. A `propertyValue` entry maps one extracted property string to a Snyk org id. Each list entry MUST set exactly one lookup key: `projectName` or `propertyValue` under `azure-repos`, and `orgName` or `propertyValue` under a GitHub section. A `propertyValue` entry for a provider that has no extractor MUST cause startup failure. Duplicate `propertyValue` keys within a provider MUST cause startup failure.

The worker MUST load and validate scope mapping entries at startup. Each mapping entry MUST include a non-empty `snykOrgId`. Duplicate `projectName` or `orgName` lookup keys within a source MUST cause startup failure. Legacy top-level key `ado` MUST be rejected at startup.

When a provider extractor returns a non-empty value, the worker MUST resolve only `propertyValue` entries for that provider. It MUST NOT use `orgName` or `projectName` for that event. When the extractor returns no value, the worker MUST resolve `orgName` or `projectName` as before.

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
- **THEN** the worker does not use the `orgName` entry

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
Scope mapping sections MUST be keyed by Snyk integration type, not provider source names. Allowed top-level keys under `scopeMapping` (other than `defaultSnykOrgId` and `propertyExtractors`) are:

| Section key | Provider source | Entry shape |
| ----------- | --------------- | ----------- |
| `azure-repos` | ADO | `projectName` or `propertyValue`, `snykOrgId`, optional `snykIntegrationId` |
| `github` | GitHub | `orgName` or `propertyValue`, `snykOrgId`, optional `snykIntegrationId` |
| `github-cloud-app` | GitHub | same as `github` |
| `github-server-app` | GitHub | same as `github` |
| `github-enterprise` | GitHub | same as `github` |

The integration type used for Snyk API lookup MUST be the section key. Unknown section keys, including `github-cloud` and `github-server`, MUST cause startup failure.

When `defaultSnykOrgId` is used without an explicit scope entry, the worker MUST use `azure-repos` for ADO events. For GitHub events it MUST use `github` unless exactly one GitHub integration type section is configured, in which case that type MUST be used.

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

### Requirement: Unmapped scope handling
When no config mapping exists for the applicable lookup key, the worker MUST log a warning and MUST NOT dead-letter the message. Configuration MAY specify an optional default Snyk organization id.

The applicable lookup key is the extracted property value when the provider extractor returns a non-empty value, and the ADO project name or GitHub organization login when it does not.

When `defaultSnykOrgId` is configured, the worker MUST use that Snyk organization and MUST log a warning that includes a stable `scope_mapping_default` marker, source, scope id, repository id, event id, lookup key, and the extracted value when present. When `defaultSnykOrgId` is not configured, the worker MUST log a warning that includes a stable `scope_mapping_unmapped` marker and those same identifiers, and MUST NOT perform Snyk side effects.

An explicit `propertyValue`, `orgName`, or `projectName` match MUST be logged at info and MUST NOT use the warning markers.

#### Scenario: Unmapped ADO project without default
- **WHEN** an ADO event arrives for a project name with no config mapping, the ADO extractor returns no value, and no default org is configured
- **THEN** the worker logs `scope_mapping_unmapped` and does not perform Snyk side effects

#### Scenario: Unmapped scope with default org
- **WHEN** an ADO or GitHub event arrives for an unmapped scope name and `defaultSnykOrgId` is configured
- **THEN** the worker uses the default Snyk organization, uses the default integration type for the provider source, and logs `scope_mapping_default`

#### Scenario: Unmapped extracted property with default org
- **WHEN** the GitHub extractor returns a value with no `propertyValue` entry and `defaultSnykOrgId` is configured
- **THEN** the worker imports into the default Snyk organization and the warning includes the extracted value

#### Scenario: Unmapped extracted property without default
- **WHEN** the GitHub extractor returns a value with no `propertyValue` entry and no default org is configured
- **THEN** the worker logs `scope_mapping_unmapped` and does not perform Snyk side effects

### Requirement: Optional integration id in operator config
Scope mapping list entries MAY include an optional `snykIntegrationId` string. When present, the value MUST be non-empty. Duplicate validation rules for scope entries otherwise unchanged. `propertyValue` entries MAY include `snykIntegrationId` under the same rules.

#### Scenario: Config with integration id
- **WHEN** operator config includes `snykIntegrationId` on an ADO project entry under `azure-repos`
- **THEN** the worker uses that integration id for Snyk actions targeting that scope

#### Scenario: Property value entry with integration id
- **WHEN** operator config includes `snykIntegrationId` on a GitHub `propertyValue` entry
- **THEN** the worker uses that integration id for Snyk actions when the extracted value matches

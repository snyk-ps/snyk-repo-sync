## 1. Parsed updated fixture

- [x] 1.1 Add `data/fixtures/github_parsed_updated.json` for the CloudEvents envelope `type: ENVLOG.GitHub.custom_property_values.updated`, with `data.newPropertyValues` containing `azure-devops-project` / `sample-project` and camelCase `data.repository`

## 2. Property extractor and scope resolution

- [x] 2.1 Parse `scopeMapping.propertyExtractors` for `github` and `azure-repos` (`collectionPath`, `matchField`, `matchValue`, `valueField`) and reject unknown keys, incomplete fields, and paths with empty segments, `..`, brackets, or filters
- [x] 2.2 Parse `propertyValue` entries beside `orgName` and `projectName`, including optional `snykIntegrationId`, and fail startup on mixed lookup keys, duplicate `propertyValue` within a provider, or a `propertyValue` row with no extractor
- [x] 2.3 Resolve in order: non-empty extracted value to `propertyValue` only, then org or project name when extraction is absent, then `defaultSnykOrgId`, then unmapped; conflicting non-empty matches fail as invalid normalization
- [x] 2.4 Add unit tests for extractor parsing, GitHub and synthetic ADO extraction, authoritative extracted values, default and unmapped outcomes, and the startup failures above

## 3. Normalize the updated envelope

- [x] 3.1 Classify `ENVLOG.GitHub.custom_property_values.updated` before the parsed lifecycle contract and normalize it to `repo.created` using `data.deliveryId`, `data.repository`, and envelope `time`
- [x] 3.2 Keep `scopeId` and `github.orgLogin` as the GitHub organization login, and keep current normalized outcomes for existing GitHub and ADO fixtures
- [x] 3.3 Add unit tests for the updated fixture and for one existing fixture of each current GitHub and ADO shape

## 4. Import path and warning logs

- [x] 4.1 Run the existing GitHub `repo.created` import flow for the updated envelope, including scope resolution from the extracted value
- [x] 4.2 Log info for an explicit match, WARN with marker `scope_mapping_default` when using `defaultSnykOrgId`, and WARN with marker `scope_mapping_unmapped` when no default org is configured; include source, scope id, repository id, event id, lookup key, and extracted value when present
- [x] 4.3 Do not deactivate or delete an ADO target and do not persist an ADO link during this import
- [x] 4.4 Add unit tests for explicit property import, default-org WARN, unmapped WARN with no Snyk side effects, and absence of ADO target removal

## 5. HTTP ingress

- [x] 5.1 Accept `github_parsed_updated.json` on `POST /github-events` and return 204 after successful processing
- [x] 5.2 Keep rejecting GitHub `action: created` and ADO payloads with non-2xx and no lifecycle side effects
- [x] 5.3 Add endpoint tests for the updated fixture, an existing renamed fixture, `created`, and an ADO payload

## 6. Documentation

- [x] 6.1 Update `README.md`, `CONFIGURATION.md`, `INGESTION.md`, and `data/config.yaml.example` for the updated import contract, `propertyExtractors`, `propertyValue` rows, WARN fallback, and the deferred ADO target deactivation

## 7. Verification

- [x] 7.1 Run the unit test suite and repository lint checks
- [x] 7.2 Run Snyk Code on the change and confirm it introduces no high-severity issues

## 8. Archive

- [ ] 8.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/property-value-scope-mapping/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive property-value-scope-mapping` (or project equivalent) to fold deltas into canonical specs

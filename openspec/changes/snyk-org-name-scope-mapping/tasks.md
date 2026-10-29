## 1. Config parse

- [ ] 1.1 Accept an integration section as a list or as a mapping with `entries` and `matchSnykOrgName`, and parse required booleans `enabled` and `normalize`
- [ ] 1.2 Require non-empty `scopeMapping.snykGroupId` when any section sets `enabled: true`, reject a second enabled section for the same provider, and keep `snykGroupId` from being treated as an integration type
- [ ] 1.3 Keep list sections and `entries` on the existing lookup-key, duplicate, and `snykIntegrationId` rules, and count an object section as a configured integration type when `entries` is empty
- [ ] 1.4 Add unit tests for the list form, the object form, missing booleans, a missing group id, and two enabled GitHub sections

## 2. Group org list and name comparison

- [ ] 2.1 Add a Snyk client call for `GET /v1/group/{groupId}/orgs` that reads `orgs[].id` and `orgs[].name` and skips entries missing either field
- [ ] 2.2 Cache that list in process memory and refresh it when the cache is older than 15 minutes
- [ ] 2.3 Compare a trimmed candidate to org names, and when `normalize` is true apply NFKD, strip nonspacing marks, and casefold both sides
- [ ] 2.4 Add unit tests for exact match, `Systèmes Centraux` matching `systemes centraux`, punctuation staying significant, skipped incomplete orgs, and cache refresh

## 3. Resolution order

- [ ] 3.1 Resolve in order and stop at the first success: static row, org-name match, non-empty stored `snykOrgId`, then `defaultSnykOrgId`
- [ ] 3.2 Keep an extracted value off `orgName` and `projectName`, skip the group API on a static hit or when `enabled` is false, and use the enabling section key or the stored integration type for those hits
- [ ] 3.3 On zero name matches continue; on two or more matches stop with no org write and no Snyk side effects; on a group-list failure fail the message as a Snyk API error without continuing
- [ ] 3.4 Add unit tests for each stop in the order, an existing row with no `snykOrgId`, ambiguous names, and a group-list failure

## 4. Sync state

- [ ] 4.1 Add `snykOrgId` and `snykIntegrationType` to repository state read and merge upsert, treating a missing or blank `snykOrgId` as no stored org
- [ ] 4.2 Write the resolved pair on every repository upsert after a successful resolution, and leave the properties unwritten for unmapped, ambiguous, and group-list failure outcomes
- [ ] 4.3 Pass the stored pair into lifecycle processing, import polling, and ignore reconciliation
- [ ] 4.4 Add unit tests for round-trip, a row without the properties, and an upsert that replaces a previously stored org id

## 5. Logging

- [ ] 5.1 Log info `scope_mapping_org_name` for a unique org-name match, including the candidate, matched org name, and org id
- [ ] 5.2 Log warning `scope_mapping_org_name_ambiguous` when more than one org matches, and keep `scope_mapping_default` and `scope_mapping_unmapped` for the steps after a stored org id miss
- [ ] 5.3 Add unit tests that the name-match and ambiguous markers omit the default and unmapped markers and contain no secrets

## 6. Documentation

- [ ] 6.1 Update `CONFIGURATION.md`, `data/config.yaml.example`, the scope-mapping troubleshooting row in `README.md`, and the org-selection sentence in `INGESTION.md` for `matchSnykOrgName.enabled`, `normalize`, `snykGroupId`, the resolution order, and the stored org id

## 7. Verification

- [ ] 7.1 Run the unit test suite and repository lint checks
- [ ] 7.2 Run Snyk Code on the change and confirm it introduces no high-severity issues

## 8. Archive

- [ ] 8.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/snyk-org-name-scope-mapping/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive snyk-org-name-scope-mapping` (or project equivalent) to fold deltas into canonical specs

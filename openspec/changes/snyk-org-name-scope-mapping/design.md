## Context

Scope mapping resolves a candidate string to a Snyk organization before lifecycle sync. The candidate is the extracted property when the provider extractor returns a value, and otherwise the ADO project name or GitHub organization login. An extracted value uses `propertyValue` rows only. A miss uses `defaultSnykOrgId` when set, and otherwise completes with `scope_mapping_unmapped`.

Integration sections are lists of those static rows. The worker already calls Snyk v1 with `SNYK_TOKEN` (`GET /v1/org/{orgId}/integrations`). Repository rows in Azure Table Storage track target id, branch, and import status. Upserts use merge mode. Rows do not store a Snyk org id, and reconciliation resolves scope again from `ownerName`.

## Goals / Non-Goals

**Goals:**

- Let an integration section opt in to matching the candidate string against Snyk org names in one group.
- Make that opt-in an explicit `enabled` boolean, with a separate `normalize` boolean for accent stripping and case folding.
- Stop at the first success: static row, org-name match, stored org id, `defaultSnykOrgId`.
- Persist the resolved org id and integration type on the repository row.
- Keep existing list sections valid.

**Non-Goals:**

- A new OpenSpec capability.
- Storing mapping rules, or a Snyk integration id, in Table Storage.
- Collapsing whitespace, stripping punctuation, or decomposing ligatures such as `œ`.
- Moving an existing Snyk target when a later event resolves to a different org. This change records the new org id; target migration stays out of scope.
- Per-integration group ids. One deployment has one `scopeMapping.snykGroupId`.

## Decisions

### 1. Section object beside the existing list

A section value remains a list of static entries, or becomes a mapping:

```yaml
scopeMapping:
  snykGroupId: "GROUP-UUID"
  github-enterprise:
    entries:
      - propertyValue: sample-project
        snykOrgId: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
      - orgName: snyk-ps
        snykOrgId: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    matchSnykOrgName:
      enabled: true
      normalize: true
```

`entries` uses the same lookup-key, duplicate, and `snykIntegrationId` rules as a list. It may be omitted. `matchSnykOrgName` requires both `enabled` and `normalize` as booleans. Any other key under the section or under `matchSnykOrgName` fails startup.

`enabled: false` does not call the group API. `normalize` is unused in that case. `enabled: true` requires a non-empty `scopeMapping.snykGroupId`. At most one GitHub section and at most one `azure-repos` section may set `enabled: true`. The section key is the integration type for a name-match hit. An object section counts as a configured integration type even when `entries` is empty, including for the existing single-GitHub-section default.

Alternative considered: a bare `matchSnykOrgName: true` or a block whose presence meant enabled. Rejected because operators need to read `enabled: true` or `enabled: false` directly.

### 2. Group org list, cache, and comparison

Name match calls `GET /v1/group/{groupId}/orgs` on the existing Snyk client base URL. The `orgs` array supplies `id` and `name`. Entries missing either field are skipped.

The worker caches the list in process memory and refreshes it when the cache is older than 15 minutes. A static hit does not call the group API. `enabled: false` does not call it.

Comparison trims both the candidate and each org name. `normalize: false` then requires exact equality. `normalize: true` applies Unicode NFKD, removes nonspacing marks (category `Mn`), then `casefold` to both sides. `Systèmes Centraux` matches `systemes centraux`. Internal spaces and punctuation stay significant.

Zero matches continue. One match stops and uses that org id with the enabling section's integration type. Two or more matches stop the chain: warning `scope_mapping_org_name_ambiguous`, no sync-state org write, no Snyk side effects, and the message completes rather than dead-lettering.

A group-list failure uses the existing `SnykApiError` settlement. The worker does not continue to the stored org id or `defaultSnykOrgId`.

Integration id for a name-match or stored-org hit is resolved by listing integrations for that org and type, same as a static row that omits `snykIntegrationId`.

### 3. Resolution order

```
candidate
  → static propertyValue, or orgName / projectName when nothing was extracted
  → org-name match when enabled
  → repository row snykOrgId when non-empty
  → defaultSnykOrgId when set
  → scope_mapping_unmapped
```

An extracted value still does not consult `orgName` or `projectName`. The default-org integration type rule is unchanged and applies only on that step. A stored hit uses the row's `snykIntegrationType`.

Lifecycle, import poll, and ignore reconciliation all use this order. The repository row is read before resolution so step 3 can see `snykOrgId`. Reconciliation today passes `ownerName` as the lookup key; it also passes the stored org id and integration type.

### 4. What the repository row stores

Add string properties `snykOrgId` and `snykIntegrationType`. Every repository upsert after a successful resolution writes that pair and replaces it when a later static or name-match resolution differs. Merge upserts leave the properties in place when an older writer omits them. Rows written before this change have neither property, so step 3 misses until the next successful resolution.

`snykIntegrationType` is stored because a later rename, delete, or branch change has to select `github-enterprise` rather than the provider default. Integration ids stay out of the table.

## Risks / Trade-offs

- [Group list is stale for up to 15 minutes] → A renamed org can miss until refresh. The static row still wins immediately and does not depend on the cache.
- [Ambiguous normalized names] → The worker refuses to pick an org or fall through to the default org. Operators disambiguate with a static row or by renaming an org.
- [Ligatures and punctuation] → `œ` does not become `oe`. Operators who need that match use a static row.
- [Resolved org changes while the Snyk target stays in the previous org] → The row records the new org id and this change does not move the target. A follow-up change can define migration.
- [Group API unavailable] → Already-imported repos fail the message instead of using the stored org id. That avoids importing into `defaultSnykOrgId` while the name match is unknown.
- [403 from the group endpoint] → Same settlement as other Snyk API failures, with an error that names the group list call. The token needs permission to list orgs in the group.

## Migration Plan

Deploy the worker after the config is valid. Existing list sections need no edit. Enabling name match requires `snykGroupId` and `matchSnykOrgName.enabled` / `normalize` on one section. Existing table rows gain the two properties on their next successful upsert. Rollback to a worker that does not send those properties keeps them, because repository upserts merge.

## Open Questions

None.

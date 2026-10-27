## Context

Scope mapping today resolves an ADO project name or a GitHub organization login to a Snyk organization id. GitHub queue bodies are either raw webhook JSON or a parsed lifecycle object with top-level `deliveryId` and `action`. `POST /github-events` accepts `renamed`, `edited`, and `deleted` in those shapes and rejects `updated` until a fixture defines the contract.

The connector sample for import is a CloudEvents envelope, `type: ENVLOG.GitHub.custom_property_values.updated`. Repository fields sit on `data.repository` (camelCase, same as the parsed contract). `data.newPropertyValues` is an array of `{property_name, value}`. The sample value `azure-devops-project` / `sample-project` is the Snyk org lookup key. There is no top-level `action` and no top-level `deliveryId`.

Sync-state partitions stay `github:{orgLogin}` and `ado:{projectId}`. The extracted property selects the Snyk org. It does not replace `scopeId`.

## Goals / Non-Goals

**Goals:**

- Accept `data/fixtures/github_parsed_updated.json` on Service Bus and on `POST /github-events`, and normalize it to `repo.created` so the existing import path runs.
- Let operators define one property extractor per provider and map each extracted value to a Snyk org id under the existing integration-type sections.
- Keep `orgName` and `projectName` mappings for messages that do not yield an extracted value, including current fixtures.
- Log **WARN** and use `defaultSnykOrgId` when nothing matches. Log **WARN** and skip Snyk work when no default org is configured.
- Use the same extractor shape for `azure-repos` when an operator supplies a path. Cover Azure with a synthetic unit payload.

**Non-Goals:**

- Deactivating or deleting a previous Azure DevOps Snyk target after the GitHub import. A later change may import the GitHub repository and retire the ADO target identified by `azure-devops-project`. This change does not store that link and does not call ADO target removal.
- Moving a repository between Snyk orgs when the property value changes.
- Treating GitHub `action: created` as the import signal for this contract. Existing Service Bus `created` fixtures keep their current normalization. `/github-events` still rejects `created`.
- A general JSONPath engine, new lifecycle event types, or a new OpenSpec capability.

## Decisions

### 1. The updated envelope is the import

`ENVLOG.GitHub.custom_property_values.updated` normalizes to `eventType: repo.created` and then uses the existing create flow (ignore policy, scope resolution, idempotent import, follow-up polling).

Field mapping:

| Normalized field | Source |
| --- | --- |
| `eventId` | `data.deliveryId` |
| `occurredAt` | envelope `time`, otherwise `data.repository.updatedAt` |
| `scopeId` and `github.orgLogin` | `data.repository.owner.login` |
| `repositoryId` | `data.repository.id` |
| `repository.name` | `data.repository.name` |
| `payload.defaultBranch` | `data.repository.defaultBranch` when present |

`oldPropertyValues`, `sender`, `correlationid`, `env`, and other envelope metadata are ignored for routing and lifecycle. Owner type other than `Organization` completes with no lifecycle sync, same as other GitHub shapes.

Classification order for GitHub bodies: updated envelope (`type` equals `ENVLOG.GitHub.custom_property_values.updated`), then parsed contract (non-empty top-level `deliveryId`), then raw webhook. ADO detection (`eventType: AzureDevOpsAuditEvent` or `subject: AzureDevOps/Auditing`) stays first so an ADO body is never read as GitHub.

Alternative considered: a new `eventType` for custom-property updates. Rejected because the user decision is that this event is the import, and the create flow already covers idempotent import.

### 2. One extractor per provider, mappings as list items

```yaml
scopeMapping:
  defaultSnykOrgId: "00000000-0000-0000-0000-000000000000"
  propertyExtractors:
    github:
      collectionPath: data.newPropertyValues
      matchField: property_name
      matchValue: azure-devops-project
      valueField: value
  github-cloud-app:
    - orgName: sample-org
      snykOrgId: "11111111-1111-1111-1111-111111111111"
    - propertyValue: sample-project
      snykOrgId: "22222222-2222-2222-2222-222222222222"
```

`propertyExtractors` is allowed beside `defaultSnykOrgId`. Keys are providers: `github` and `azure-repos`. GitHub integration sections share the `github` extractor because they share one JSON shape. The integration type remains the section key, including for `propertyValue` rows and their optional `snykIntegrationId`.

Traversal is only a dotted object path from the message root to an array of objects. The extractor keeps objects whose `matchField` equals `matchValue` and reads `valueField`. Paths reject empty segments, `..`, brackets, and filters at startup.

Resolution:

1. Extractor configured, one non-empty value, and a `propertyValue` entry for that provider → that row.
2. Path missing, no matching element, or matched value null or blank → existing `orgName` or `projectName` lookup.
3. Non-empty extracted value with no `propertyValue` row → do not use org or project rows. Use `defaultSnykOrgId` or leave the scope unmapped.
4. No extractor and no org or project row → same default or unmapped outcome.

Two matching elements with the same non-empty value use that value. Two matching elements with different non-empty values fail normalization (`InvalidNormalization`: Service Bus dead-letter, HTTP non-2xx).

Startup failures: unknown extractor key, missing extractor field, duplicate `propertyValue` within a provider, `propertyValue` row with no extractor for that provider, and an entry that sets both a name key (`orgName` or `projectName`) and `propertyValue`.

Alternative considered: a full JSONPath library. Rejected because the sample needs one array filter and operators should not be able to express arbitrary queries in config.

Alternative considered: falling through from an unknown property value to the GitHub org-login row. Rejected because that would place the repository in the org-wide Snyk org without the warning operators asked for.

### 3. Missing default org logs WARN and completes

Explicit matches log at info. Default-org fallback logs **WARN** with a stable `scope_mapping_default` message, including source, scope id, repository id, event id, lookup key, and extracted value when present. No match and no default logs **WARN** with `scope_mapping_unmapped` and the same identifiers, then completes with no Snyk side effects and no dead-letter. HTTP ingress returns 204 for that completion.

ERROR was rejected because the message is handled on purpose. On Kafka, non-2xx would retry a config gap that retry cannot fix. Dynatrace can alert on the warning text. This replaces today's info log for `resolution=default`. Unmapped scopes already log a warning.

### 4. ADO extractor is config-only in this change

`azure-repos` uses the same four extractor fields and `propertyValue` rows beside `projectName` rows. No ADO fixture is added. Unit tests supply a synthetic ADO object. When no `azure-repos` extractor is configured, ADO resolution stays project name then default.

## Risks / Trade-offs

- [A later property edit re-imports into a different Snyk org while the previous target remains] → Accepted. Cross-org move and ADO target retirement are follow-up work. Sync state stays keyed by GitHub org login plus repository id, so a second import in another Snyk org is not modeled here.
- [Default-org fallback becomes WARN for existing org and project misses too] → Accepted. Operators asked for WARN whenever resolution uses the default org. Explicit mappings stay info.
- [A GitHub lifecycle message that happens to contain `data.newPropertyValues` would use the extractor] → The extractor runs on the received JSON root. Current raw and parsed fixtures have no such path, so they keep org-login lookup. Document the path as relative to the body the worker receives.
- [Conflicting property values dead-letter] → Operators see a bad payload instead of a silent pick. One repeated value is accepted.

## Migration Plan

Deploy the worker after the config gains `propertyExtractors` and `propertyValue` rows. Existing config without those keys keeps current org and project behavior, aside from WARN on default-org fallback. Roll back by deploying the previous image; new config keys would then fail startup, so roll back the config with the image. No sync-state migration.

## Open Questions

None. ADO target deactivation after GitHub import is deferred on purpose.

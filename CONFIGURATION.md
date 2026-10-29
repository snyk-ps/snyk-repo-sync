# Configuration reference

Operator reference for worker configuration, CLI commands, and sync-state schema. For installation, usage, and **[Azure Container App deployment](README.md#deployment)**, see the [README](README.md). For Service Bus provisioning and ADO audit stream / GitHub webhook ingress setup, see **[INGESTION.md](INGESTION.md)**. For layout, tests, OpenSpec, and CI/Docker details, see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

The worker authenticates to Azure with `DefaultAzureCredential` (managed identity in production; `az login` or a service principal locally). Connection strings and shared access keys are **not supported**.

## Operator config file

The worker loads a YAML config file via `--config` (default `data/config.yaml`). In production, mount the file at `/config/config.yaml` (Azure Files).

Copy the example to get started locally:

```bash
cp data/config.yaml.example data/config.yaml
```



### Config schema


| Key                                  | Required | Default         | Description                                                                                             |
| ------------------------------------ | -------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| `messaging.transport`                | No       | `serviceBus`    | `serviceBus` or `kafka`. Snyk recommends `serviceBus`                                                   |
| `serviceBus.fullyQualifiedNamespace` | Yes for `serviceBus` | —     | Service Bus namespace FQDN, e.g. `mynamespace.servicebus.windows.net`. Ignored when transport is `kafka` |
| `serviceBus.queueName`               | Yes for `serviceBus` | —     | Pre-provisioned queue name. Ignored when transport is `kafka`                                          |
| `serviceBus.receiveMaxWaitSeconds`   | No       | `5`             | Maximum seconds to wait for a message on each receive poll; does **not** stop the worker when the queue is idle |
| `storageQueue.queueName`             | Yes for `kafka` | —          | Pre-provisioned storage queue for follow-ups. Must be lowercase, 3–63 characters                       |
| `storageQueue.poisonQueueName`       | No       | `{queueName}-poison` | Pre-provisioned poison queue in the same storage account                                          |
| `storageQueue.receiveMaxWaitSeconds` | No       | `5`             | Idle poll wait for the storage queue. Integer from 1 to 300. Does **not** stop the worker              |
| `storageQueue.visibilityTimeoutSeconds` | No    | `60`            | Lock duration while a storage-queue message is processed. Integer from 1 to 604800                     |
| `http.bindHost`                      | No       | `0.0.0.0`       | Kafka only. HTTP listener bind host                                                                      |
| `http.port`                          | No       | `8080`          | Kafka only. HTTP listener port from 1 through 65535                                                      |
| `http.maxRequestBodyBytes`           | No       | `1048576`       | Kafka only. Positive maximum request-body size                                                           |
| `http.processingConcurrency`         | No       | `1`             | Kafka only. Concurrent request-processing limit from 1 through 100                                      |
| `syncState.storageAccountEndpoint`   | Yes      | —               | Table service URL, e.g. `https://myaccount.table.core.windows.net`. On `kafka`, the queue URL is this host with `.table.` replaced by `.queue.` |
| `syncState.tableName`                | No       | `SnykSyncState` | Sync-state table name                                                                                   |
| `ado.organization`                   | With one or more `scopeMapping.azure-repos` entries | — | ADO organization name used for Git REST enrichment (e.g. `contoso` for `https://dev.azure.com/contoso`) |
| `ado.host`                           | No       | `dev.azure.com` | ADO host; use for Azure DevOps Server when not hosted on `dev.azure.com`                                |


Example:

```yaml
# Required only when scopeMapping.azure-repos is non-empty.
ado:
  organization: contoso

# messaging.transport defaults to serviceBus.
# messaging:
#   transport: serviceBus

serviceBus:
  fullyQualifiedNamespace: mynamespace.servicebus.windows.net
  queueName: repo-sync-events
  # receiveMaxWaitSeconds: 5

syncState:
  storageAccountEndpoint: https://myaccount.table.core.windows.net
  # tableName: SnykSyncState

# Used only when messaging.transport is kafka. The queue lives in the same
# storage account as the table above (https://myaccount.queue.core.windows.net).
# storageQueue:
#   queueName: repo-sync-followups
#   # poisonQueueName: repo-sync-followups-poison
#   # receiveMaxWaitSeconds: 5
#   # visibilityTimeoutSeconds: 60
#
# The event connector sends GitHub events to POST /github-events.
# http:
#   bindHost: 0.0.0.0
#   port: 8080
#   maxRequestBodyBytes: 1048576
#   processingConcurrency: 1

scopeMapping:
  defaultSnykOrgId: "00000000-0000-0000-0000-000000000000"  # optional
  azure-repos:
    - projectName: Contoso-Platform
      snykOrgId: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  github-cloud-app:
    - orgName: contoso
      snykOrgId: "ffffffff-ffff-ffff-ffff-ffffffffffff"
```

Individual settings MAY be overridden by environment variables; **env values take precedence** when set. Scope mapping entries are **config-file only** (no env overrides in v1).

### Message transport (`messaging.transport`)

`serviceBus` (the default) puts GitHub events, ADO events, and internal follow-ups (`import_poll`, `lifecycle_deferred`) on one Service Bus queue.

`kafka` is a GitHub-only deployment path. The event connector reads Kafka and sends provider-native JSON to `POST /github-events`. The worker processes each request synchronously. It returns `204 No Content` only after lifecycle processing and durable scheduling of every requested follow-up succeed. The connector must retry every non-2xx response according to its policy.

The endpoint has no application authentication. Do not expose it publicly. Provide a customer-managed private route that allows only the event connector to reach the configured host and port. TLS termination and network policy are deployment responsibilities.

The endpoint accepts `renamed`, `edited`, `deleted`, and the parsed updated body in `data/fixtures/github_parsed_updated.json`. That body has top-level `repository` and `newPropertyValues` and is the GitHub import. It rejects `created` and ADO payloads.

On `kafka`, `worker run` starts the HTTP listener and the Storage Queue follow-up consumer. It does not open Service Bus. The worker sends `import_poll` and `lifecycle_deferred` follow-ups to `storageQueue.queueName` in the same storage account as `syncState.storageAccountEndpoint`. It derives `https://{account}.queue.{suffix}` from the table URL and does not accept a second account. Provision the queue and poison queue. The worker does not create them, and it never copies inbound GitHub bodies to the Storage Queue.

### Scope mapping (`scopeMapping`)

Maps provider scopes to Snyk organization ids. Top-level keys under `scopeMapping` other than `defaultSnykOrgId`, `propertyExtractors`, and `snykGroupId` MUST be Snyk integration types. Optional `snykIntegrationId` per entry skips integration list API calls; when omitted the worker resolves integration ids via the Snyk API and caches them in process memory.


| Key                 | Required | Description                                                        |
| ------------------- | -------- | ------------------------------------------------------------------ |
| `defaultSnykOrgId`  | No       | Fallback Snyk org id after static rows, org-name match, and a stored org id all miss. Using it logs a warning (`scope_mapping_default`) |
| `snykGroupId`       | When name match is enabled | Snyk group id for `GET /v1/group/{groupId}/orgs`. Not an integration type |
| `propertyExtractors` | No      | One extractor per provider (`github`, `azure-repos`) that reads a property value from the message |
| `azure-repos`       | No       | ADO mappings (Snyk integration type `azure-repos`), as a list or as an object with `entries` and `matchSnykOrgName` |
| `github`            | No       | GitHub mappings for Snyk integration type `github`, as a list or as an object |
| `github-cloud-app`  | No       | GitHub mappings for Snyk integration type `github-cloud-app`       |
| `github-server-app` | No       | GitHub mappings for Snyk integration type `github-server-app`      |
| `github-enterprise` | No       | GitHub mappings for Snyk integration type `github-enterprise`      |


Each `azure-repos` entry (ADO):


| Key                 | Required | Description                                                        |
| ------------------- | -------- | ------------------------------------------------------------------ |
| `projectName`       | One of   | ADO project name — MUST match audit `ProjectName` (case-sensitive). Set this or `propertyValue`, not both |
| `propertyValue`     | One of   | Value read by `propertyExtractors.azure-repos`. Requires that extractor |
| `snykOrgId`         | Yes      | Target Snyk organization id                                        |
| `snykIntegrationId` | No       | Integration id — optional; resolved via API when omitted           |


Each **GitHub integration type** entry (`github`, `github-cloud-app`, `github-server-app`, `github-enterprise`):


| Key                 | Required | Description                                              |
| ------------------- | -------- | -------------------------------------------------------- |
| `orgName`           | One of   | GitHub organization login (case-sensitive). Set this or `propertyValue`, not both |
| `propertyValue`     | One of   | Value read by `propertyExtractors.github`. Requires that extractor |
| `snykOrgId`         | Yes      | Target Snyk organization id                              |
| `snykIntegrationId` | No       | Integration id — optional; resolved via API when omitted |


The integration type for API lookup is determined by the section key (for example `github-cloud-app`), not a per-entry field. The worker matches that value against `GET /v1/org/{org_id}/integrations` to resolve the integration id. It also sends the same value as the `source_types` filter on `GET /rest/orgs/{org_id}/targets`; import itself uses the resolved integration id at `POST /v1/org/{org_id}/integrations/{integration_id}/import`.

An integration section is either a list of those entries or a mapping:

```yaml
github-enterprise:
  entries: []          # optional; same rules as a list. An empty object section still counts as that integration type
  matchSnykOrgName:
    enabled: true      # required boolean when matchSnykOrgName is present
    normalize: true    # required boolean; NFKD, strip accents, and ignore case
```

`enabled: false` leaves name match off and does not call the group API. `enabled: true` requires `snykGroupId`. At most one GitHub section and at most one `azure-repos` section may set `enabled: true`. The enabling section key is the integration type for a name match. `normalize: false` compares trimmed strings exactly. `normalize: true` applies Unicode NFKD, removes nonspacing marks, and casefolds both the candidate and the org name. Spaces and punctuation stay significant, so `Systèmes Centraux` matches `systemes centraux` and does not match `Systemes-Centraux`.

The worker lists orgs with `GET /v1/group/{groupId}/orgs` and caches that list in process memory for 15 minutes. A static row does not call the group API. The token needs permission to list organizations in the group.

**Resolution order:** The worker stops at the first success:

1. Static `propertyValue` when the extractor returns a value, otherwise static `orgName` or `projectName`. An extracted value does not consult `orgName` or `projectName`.
2. Org-name match when `matchSnykOrgName.enabled` is true. One match uses that org id. Zero matches continue. Two or more matches log `scope_mapping_org_name_ambiguous`, write no org id, and perform no Snyk side effects.
3. Non-empty `snykOrgId` stored on the repository sync-state row, with that row's `snykIntegrationType`. A missing or blank `snykOrgId` misses this step.
4. `defaultSnykOrgId` when it is set.

A group-list failure fails the message like any other Snyk API error and does not continue to the stored org or the default org. After a successful resolution, repository upserts store `snykOrgId` and `snykIntegrationType` and replace them when a later event resolves to a different org.

When using `defaultSnykOrgId`, the worker uses `azure-repos` for ADO events. For GitHub events it uses `github` unless exactly one GitHub integration type section is configured, in which case that type is used. That default applies only to the `defaultSnykOrgId` step. An object section with no entries still counts as that configured type.

**Property extractors:** `collectionPath` is a dotted object path from the received JSON root to an array of objects. The worker keeps elements whose `matchField` equals `matchValue` and reads `valueField`. For the GitHub updated fixture the path is `newPropertyValues`, `matchField` is `property_name`, `matchValue` is `azure-devops-project`, and `valueField` is `value`. The same four fields work for `azure-repos` when an operator supplies a path. A non-empty extracted value is the candidate and does not fall through to `orgName` or `projectName`. A missing path, or a null or blank value, uses the name mapping.

**Lookup keys:** When no property value is extracted, ADO events use `ado.projectName` from the normalized audit record and GitHub events use `repository.owner.login`. `scopeId` stays the ADO project id or GitHub org login. Importing a GitHub repository does not deactivate an existing Azure DevOps Snyk target; that retirement is a later change.

**Unmapped scopes:** When static mapping, org-name match, and the stored org id all miss and `defaultSnykOrgId` is set, the worker imports into that org and logs a warning with marker `scope_mapping_default`. When no default org is set, the worker logs a warning with marker `scope_mapping_unmapped` and completes the message without Snyk side effects. A static match, a unique org-name match (`scope_mapping_org_name`), and a stored-org match stay at info and omit both warning markers.

Duplicate `projectName` or `orgName` values within a list cause startup failure.

See `openspec/specs/scope-mapping/spec.md` for the full capability contract.

### Snyk settings (`snyk`)


| Key                                   | Required | Default      | Description                                                                                       |
| ------------------------------------- | -------- | ------------ | ------------------------------------------------------------------------------------------------- |
| `maxConcurrentPendingImports`         | No       | `100`        | Max repository rows with `importStatus=pending` before deferring new imports (per worker process) |
| `targetRemoval.onRename`              | No       | `deactivate` | `deactivate` or `delete` for old target on rename                                                 |
| `targetRemoval.onDefaultBranchChange` | No       | `deactivate` | `deactivate` or `delete` for old target on default branch change                                  |
| `targetRemoval.onRepoDelete`          | No       | `deactivate` | `deactivate` or `delete` when provider repo is deleted                                            |
| `targetRemoval.onIgnore`              | No       | `deactivate` | `deactivate` or `delete` when a repository matches ignore policy                                  |


`delete` is irreversible. Default is `deactivate` for all four removal actions.

**Removal semantics:** Snyk has no target-level deactivate API. When mode is `deactivate`, the worker deactivates **every project** under the target via the v1 Projects API. When mode is `delete`, the worker deletes the target via the REST Targets API (`DELETE /rest/orgs/{org_id}/targets/{target_id}`), which removes associated projects.

**Target id resolution:** Import job polling does not reliably return a target id. After import completes (and on rename, default-branch change, or delete when state is empty), the worker resolves `snykTargetId` via the REST Targets API using ADO project name, repository name, and branch. Resolved ids are persisted on repository state.

With **N** worker replicas, effective pending import capacity is approximately **N × maxConcurrentPendingImports**. Lower the limit or replica count if Snyk rate limits are hit.

Project tagging (`tagApplied=true`) is deferred to a follow-up change; import job completion defines sync success in the current slice.

### Ignore policy (`ignoredRepos`)

When enabled, the worker skips import for ignored repositories and removes active Snyk targets per `snyk.targetRemoval.onIgnore`. Policy is evaluated immediately on every lifecycle event and re-checked by a background reconciliation loop (default every 15 minutes).

| Key | Required | Default | Description |
| --- | -------- | ------- | ----------- |
| `path` | Yes (when section present) | — | Path to ignore policy file (`.yaml`, `.yml`, or `.json`). Relative paths resolve from the directory containing `config.yaml`. |
| `reconciliationIntervalMinutes` | No | `15` | Background reconciliation interval in minutes |

Example operator config:

```yaml
ignoredRepos:
  path: ignored-repos.yaml
  reconciliationIntervalMinutes: 15
```

Mount the policy file on the **same Azure Files share** as `config.yaml` (for example `/config/ignored-repos.yaml`). See `data/ignored-repos.yaml` and `data/ignored-repos.json` for examples.

The policy file is read as **UTF-8** and supports **YAML or JSON** (detected by file extension).

#### Explicit repositories (`repos`)

Each entry MUST include:

| Field | Values | Meaning |
| ----- | ------ | ------- |
| `source` | `azure-repos`, `github` | Provider/integration type |
| `owner` | string | ADO project name or GitHub org login |
| `name` | string | Repository name |

Additional fields (for example `reason`, `ticket`) are for operator documentation only and do not affect matching.

#### Name patterns (`patterns`)

Grouped by operator-defined `id` (for example `Disabled`, `Documentation`). Each group has:

| Field | Values | Description |
| ----- | ------ | ----------- |
| `filterType` | `regex`, `prefix`, `suffix` | How patterns are matched against repository name |
| `patterns` | list of strings | One or more match strings (Python `re` syntax when `filterType` is `regex`) |

A repository is ignored if **any** explicit entry matches or **any** pattern in **any** group matches the repository name.

#### Enforcement

| Trigger | Behavior |
| ------- | -------- |
| Lifecycle event (create, rename, branch change) | Evaluate immediately; skip import; remove active target per `onIgnore` |
| Background reconciliation | Reload policy file; remove stale active targets matching policy |
| Policy reload failure | Log error; continue with last persisted policy from sync state |

When `ignoredRepos.path` is unset, ignore enforcement is disabled. When set and the file is missing at worker startup, the worker exits with a configuration error.

See `openspec/specs/ignored-repos/spec.md` for the full capability contract.

### Environment overrides


| Variable                               | Overrides                            |
| -------------------------------------- | ------------------------------------ |
| `MESSAGING_TRANSPORT`                  | `messaging.transport`                |
| `SERVICEBUS_FULLY_QUALIFIED_NAMESPACE` | `serviceBus.fullyQualifiedNamespace` |
| `SERVICEBUS_QUEUE_NAME`                | `serviceBus.queueName`               |
| `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS`  | `serviceBus.receiveMaxWaitSeconds`   |
| `STORAGE_QUEUE_NAME`                   | `storageQueue.queueName`             |
| `STORAGE_QUEUE_POISON_NAME`            | `storageQueue.poisonQueueName`       |
| `STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS` | `storageQueue.receiveMaxWaitSeconds` |
| `STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS` | `storageQueue.visibilityTimeoutSeconds` |
| `HTTP_BIND_HOST`                       | `http.bindHost`                     |
| `HTTP_PORT`                            | `http.port`                         |
| `HTTP_MAX_REQUEST_BODY_BYTES`          | `http.maxRequestBodyBytes`          |
| `HTTP_PROCESSING_CONCURRENCY`          | `http.processingConcurrency`        |
| `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT`  | `syncState.storageAccountEndpoint`   |
| `SYNC_STATE_TABLE_NAME`                | `syncState.tableName`                |



| Variable           | Required | Description                                                                                               |
| ------------------ | -------- | --------------------------------------------------------------------------------------------------------- |
| `SNYK_TOKEN`       | Yes      | Snyk API token for import, target removal, and integration lookup (secret; never commit)                  |
| `ADO_PAT`          | With one or more `scopeMapping.azure-repos` entries | Azure DevOps PAT for Git REST enrichment when lifecycle events omit default branch (secret; never commit) |
| `ADO_ORGANIZATION` | No       | Overrides `ado.organization` from config                                                                  |
| `ADO_HOST`         | No       | Overrides `ado.host` from config                                                                          |


The worker fails fast at startup when the config file is missing, invalid, lacks required settings after the config/env merge, or when `SNYK_TOKEN` is unset. It also fails at startup when `scopeMapping.azure-repos` is non-empty and either `ado.organization` or `ADO_PAT` is unset. Without `azure-repos` mappings, neither ADO setting is required and no ADO API client is created.

### ADO PAT permissions

`ADO_PAT` is used only to resolve repository default branches when lifecycle events and sync state omit `defaultBranch`. The worker calls:

`GET https://{ado.host}/{ado.organization}/_apis/git/repositories/{repositoryId}?api-version=7.1`

Configure the PAT with the minimum scopes below. Store it in Key Vault or container secrets; never commit it.

If an ADO event is routed through `defaultSnykOrgId` in a deployment without
explicit `azure-repos` mappings, it can proceed when its branch is present in
the event or sync state. If enrichment is required, that message is
dead-lettered with a configuration error rather than guessing a branch or
stopping the worker.


| Setting          | Requirement                                                                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Scope**        | **Code (Read)** — Azure DevOps PAT scope name `Code` → **Read**                                                                                                                             |
| **Organization** | Access to the organization named in `ado.organization`                                                                                                                                      |
| **Projects**     | If the PAT is limited to specific projects, include every ADO project listed in `scopeMapping.azure-repos` (and any project you expect lifecycle events from when using `defaultSnykOrgId`) |


Scopes **not** required for this worker: Build, Release, Work Items, Packaging, Test Management, or other write/admin permissions.

On **Azure DevOps Server** (`ado.host` not `dev.azure.com`), grant the identity **Read** access to Git repositories in the mapped projects (or equivalent permission to call the Git Repositories REST API).

See [Use personal access tokens](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate) and [Get repository](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/repositories/get) in Microsoft documentation.

## RBAC

Assign these built-in roles to the Container App managed identity (production) or local dev principal (`az login` / service principal). Portal walkthrough for identity assignment: **[README § Deployment](README.md#f-managed-identity-and-rbac)**.


| Role                               | Role ID                                | Scope                    | Purpose                                                 |
| ---------------------------------- | -------------------------------------- | ------------------------ | ------------------------------------------------------- |
| **Azure Service Bus Data Owner**   | `090c5cfd-121d-4293-81b3-1665f843147`  | Namespace or queue       | Receive, settle, and send queue messages (data plane)   |
| **Storage Table Data Contributor** | `0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3` | Storage account or table | Create sync-state table if missing; read/write entities |


Least-privilege alternative for Service Bus: **Azure Service Bus Data Receiver** + **Azure Service Bus Data Sender** on the queue scope.

The worker does **not** create Service Bus queues or namespaces. It **does** call `create_table_if_not_exists` for the configured sync-state table on startup.

## CLI commands

Entry point: `src/main.py`

```bash
uv run python src/main.py --help
uv run python src/main.py worker run
uv run python src/main.py worker run --config /config/config.yaml
```


| Command                    | Purpose                                                                                                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `worker run`               | Runs the selected transport: Service Bus consumption, or Kafka-mode GitHub HTTP ingress with Storage Queue follow-up consumption |
| `worker run --config PATH` | Use a custom operator config file path                                                                                                                                           |




## Sync-state table schema

Table name defaults to `SnykSyncState`. Repository state rows use:


| Key            | Value                                                    |
| -------------- | -------------------------------------------------------- |
| `PartitionKey` | `{source}:{scopeId}` — ADO `scopeId` is project id; GitHub `scopeId` is org login |
| `RowKey`       | `{repositoryId}`                                         |


Scope-to-Snyk mapping rules are **not** stored in Table Storage — they live in the operator `scopeMapping` config section per `openspec/specs/scope-mapping/spec.md`. A repository row may store the resolved `snykOrgId` and `snykIntegrationType` from the last successful resolution.

### Repository row

`PartitionKey={source}:{scopeId}`, `RowKey={repositoryId}`


| Property           | Type    | Description                                                    |
| ------------------ | ------- | -------------------------------------------------------------- |
| `repoName`         | string  | Current repository name                                        |
| `snykTargetId`     | string  | Snyk target id                                                 |
| `defaultBranch`    | string  | Default branch name                                            |
| `status`           | string  | Sync status                                                    |
| `desiredStateHash` | string  | Idempotency hash                                               |
| `lastEventId`      | string  | Last processed provider event id                               |
| `tagApplied`       | boolean | Repository id tag applied (`false` until tagging change lands) |
| `importJobId`      | string  | Last Snyk import job id (retained after success for audit)     |
| `importStatus`     | string  | `pending`, `failed`, or `complete`                             |
| `snykOrgId`        | string  | Resolved Snyk org id. Missing or blank means no stored org     |
| `snykIntegrationType` | string | Integration type used with `snykOrgId` (`azure-repos`, `github`, `github-cloud-app`, `github-server-app`, or `github-enterprise`) |


Repository rows are written when import starts (`pending`) and updated when import completes. The table is created on worker startup when missing.

### ADO lifecycle behaviour (mapped scopes)

Snyk import payloads **require** a `branch` value. When the normalized lifecycle event includes `defaultBranch` (for example `repo.created` with audit `DefaultBranch`, or `repo.default_branch_changed`), that value is used. Otherwise the worker uses the branch already in sync state. If neither source has a branch and ADO is configured through an explicit `azure-repos` mapping, the worker calls the ADO Git REST API (`GET .../_apis/git/repositories/{repositoryId}`) with `ADO_PAT` before starting import. Without a configured ADO client, the message is dead-lettered with a configuration error rather than guessing a branch. Sync-state `defaultBranch` is set to the branch used for import, including values resolved via ADO REST.


| Event                           | Actions                                                                                                                                                                          |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **repo.created**                | Resolve import branch → start Snyk import → schedule `import_poll` follow-ups until job completes                                                                                |
| **repo.renamed**                | Resolve old target id → remove old target per `targetRemoval.onRename` (must succeed) → resolve import branch → import new name → poll until job complete and target id resolved |
| **repo.default_branch_changed** | No action if no prior default branch; else resolve old target id → remove old target → import on new default branch → poll                                                       |
| **repo.deleted**                | Resolve target id → remove per `targetRemoval.onRepoDelete`; mark state inactive (DLQ if removal fails)                                                                          |


A repository is synced when `importStatus=complete` and `snykTargetId` is set (via REST target lookup after import when not present in state). Project tagging is deferred.

## Queue message shapes

Queue message bodies are provider-native JSON or internal worker follow-up envelopes on the **same** queue.

### Internal follow-up envelope

Used for async import polling and deferred lifecycle retries. Distinguished by top-level `syncPhase`:


| `syncPhase`          | Purpose                                                   |
| -------------------- | --------------------------------------------------------- |
| `import_poll`        | Poll Snyk import job status                               |
| `lifecycle_deferred` | Retry lifecycle work when pending import limit is reached |


Import poll follow-ups dead-letter with reason `ImportJobFailed` after 5 retries with exponential backoff.

### ADO (Event Grid schema)

Event Grid JSON with audit record under `data`. The worker detects ADO when `eventType == "AzureDevOpsAuditEvent"` **or** `subject == "AzureDevOps/Auditing"`.


| Field                   | Description                                      |
| ----------------------- | ------------------------------------------------ |
| `eventType` / `subject` | ADO message detection                            |
| `data`                  | Audit record passed to normalization             |
| `data.Id`               | Event id                                         |
| `data.ActionId`         | Lifecycle action (`Git.RepositoryCreated`, etc.) |


See `data/fixtures/eventgrid_ado_*.json` and **[INGESTION.md](INGESTION.md)**.

### GitHub (raw webhook, parsed contract, or parsed updated)

Raw webhook JSON has top-level `action` and `repository`. Parsed GitHubHooks events include `deliveryId` and camelCase repository fields. The parsed updated body has top-level `deliveryId`, camelCase `repository`, and `newPropertyValues`. That body normalizes to `repo.created` and is the GitHub import. See `data/fixtures/github_webhook_*.json`, `data/fixtures/github_parsed_*.json`, and `data/fixtures/github_parsed_updated.json`.

See `openspec/specs/event-ingestion/spec.md` for the canonical contract. Step-by-step ingress setup (Service Bus, ADO audit stream, GitHub webhooks): **[INGESTION.md](INGESTION.md)**.

## Normalized lifecycle event (ADO)

After parsing, the worker maps supported ADO audit records into a normalized lifecycle event, resolves scope mapping, performs Snyk lifecycle sync for mapped scopes, and completes or schedules follow-up messages.

## Normalized lifecycle event (GitHub)

GitHub uses the same four `eventType` values. `scopeId` and `github.orgLogin` are the organization login (`repository.owner.login`). `eventId` is `deliveryId` on parsed contract and parsed updated messages. `occurredAt` for the parsed updated body is `repository.updatedAt`. `edited` maps to default-branch change only when `changes.default_branch.from` is present. The parsed updated body maps to `repo.created`.


| Field                           | ADO audit source             | Description                                                                          |
| ------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------ |
| `eventId`                       | `Id`                         | Stable audit event id                                                                |
| `eventType`                     | `ActionId`                   | `repo.created`, `repo.renamed`, `repo.deleted`, or `repo.default_branch_changed`     |
| `scopeId`                       | `ProjectId`                  | ADO project id (sync-state partition key)                                            |
| `repositoryId`                  | `Data.RepoId`                | Repository id                                                                        |
| `occurredAt`                    | `Timestamp`                  | Event time                                                                           |
| `ado.orgId`                     | `ScopeId`                    | ADO organization id                                                                  |
| `ado.orgDisplayName`            | `ScopeDisplayName`           | Organization display name                                                            |
| `ado.projectId`                 | `ProjectId`                  | Same as `scopeId`                                                                    |
| `ado.projectName`               | `ProjectName`                | Project name                                                                         |
| `repository.name`               | `Data.RepoName`              | Repository name                                                                      |
| `payload.defaultBranch`         | `Data.DefaultBranch`         | Optional on create; required on default-branch change (`refs/heads/` stripped)       |
| `payload.previousDefaultBranch` | `Data.PreviousDefaultBranch` | Present when ADO reports a prior default branch; omitted when empty (no sync action) |
| `payload.previousRepoName`      | `Data.PreviousRepoName`      | Required on rename                                                                   |


Supported ADO audit `ActionId` values: `Git.RepositoryCreated`, `Git.RepositoryRenamed`, `Git.RepositoryDeleted`, `Git.RepositoryDefaultBranchChanged`.

## Error handling and logging

- Unparseable or unrecognized queue messages are **dead-lettered** with reason `InvalidMessage`.
- ADO audit records that are unsupported or missing required fields are **dead-lettered** with reason `InvalidNormalization`.
- Valid ADO messages for **mapped** scopes trigger Snyk import/deactivate/delete per lifecycle event; import completion is async via scheduled follow-ups
- Valid ADO messages for **unmapped** scopes log a **warning** and complete without Snyk side effects
- Valid GitHub messages for **mapped** orgs follow the same lifecycle and import deferral contract as ADO
- Valid GitHub messages for **unmapped** orgs, and any scope that falls back to `defaultSnykOrgId` after static mapping, org-name match, and a stored org id all miss, log a **warning** (`scope_mapping_unmapped` or `scope_mapping_default`) and unmapped messages complete without Snyk side effects. A unique org-name match logs `scope_mapping_org_name`. More than one matching org name logs `scope_mapping_org_name_ambiguous` and completes without Snyk side effects
- GitHub `edited` webhooks without a default-branch change complete without sync
- Messages dead-letter with `ImportJobFailed` when import job polling exceeds max retries
- Repeated `target_resolve_failed` warnings after a successful import, with the target visible in Snyk but no projects yet, usually mean the worker listed targets without `exclude_empty=false`. The Snyk REST Targets API defaults to omitting empty targets; upgrade to **`v1.1.1`** or later.
- Logs include parsed source, normalized lifecycle fields for ADO, scope mapping outcome, and queue name.
- Azure SDK connection/link chatter is logged at **WARNING** and above only; application loggers remain at **INFO**.



## Integration tests

Integration tests require a worker config file and Azure credentials (`az login` or service principal with required RBAC). See **[CONTRIBUTING.md § Integration tests](CONTRIBUTING.md#integration-tests)**.

```bash
cp data/config.yaml.example data/config.yaml
# edit data/config.yaml with your dev namespace and storage account
az login
uv run pytest -m integration
```


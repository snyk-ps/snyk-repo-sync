# Configuration reference

Operator reference for worker configuration, CLI commands, and sync-state schema. For installation, usage, and deployment, see the [README](README.md). For Service Bus provisioning and ADO audit stream / GitHub webhook ingress setup, see **[INGESTION.md](INGESTION.md)**. For layout, tests, OpenSpec, and CI/Docker details, see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

The worker authenticates to Azure with **`DefaultAzureCredential`** (managed identity in production; `az login` or a service principal locally). Connection strings and shared access keys are **not supported**.

## Operator config file

The worker loads a YAML config file via `--config` (default **`data/config.yaml`**). In production, mount the file at **`/config/config.yaml`** (Azure Files).

Copy the example to get started locally:

```bash
cp data/config.yaml.example data/config.yaml
```

### Config schema

| Key | Required | Default | Description |
| --- | -------- | ------- | ----------- |
| `serviceBus.fullyQualifiedNamespace` | Yes | — | Service Bus namespace FQDN, e.g. `mynamespace.servicebus.windows.net` |
| `serviceBus.queueName` | Yes | — | Pre-provisioned queue name |
| `syncState.storageAccountEndpoint` | Yes | — | Table service URL, e.g. `https://myaccount.table.core.windows.net` |
| `syncState.tableName` | No | `SnykSyncState` | Sync-state table name |

Example:

```yaml
serviceBus:
  fullyQualifiedNamespace: mynamespace.servicebus.windows.net
  queueName: repo-sync-events

syncState:
  storageAccountEndpoint: https://myaccount.table.core.windows.net
  # tableName: SnykSyncState
```

Individual settings MAY be overridden by environment variables; **env values take precedence** when set.

### Environment overrides

| Variable | Overrides |
| -------- | --------- |
| `SERVICEBUS_FULLY_QUALIFIED_NAMESPACE` | `serviceBus.fullyQualifiedNamespace` |
| `SERVICEBUS_QUEUE_NAME` | `serviceBus.queueName` |
| `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT` | `syncState.storageAccountEndpoint` |
| `SYNC_STATE_TABLE_NAME` | `syncState.tableName` |

Future Snyk API settings (for example `SNYK_TOKEN`) remain environment secrets when Snyk sync is implemented.

Scope-to-Snyk mapping (ADO project name / GitHub org name → Snyk org id) will be added to operator config in a follow-up change. See **`openspec/specs/scope-mapping/spec.md`**.

The worker fails fast at startup when the config file is missing, invalid, or lacks required settings after the config/env merge.

## RBAC

Assign these built-in roles to the Container App managed identity (production) or local dev principal (`az login` / service principal):

| Role | Role ID | Scope | Purpose |
| ---- | ------- | ----- | ------- |
| **Azure Service Bus Data Owner** | `090c5cfd-121d-4293-81b3-1665f843147` | Namespace or queue | Receive, settle, and send queue messages (data plane) |
| **Storage Table Data Contributor** | `0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3` | Storage account or table | Create sync-state table if missing; read/write entities |

Least-privilege alternative for Service Bus: **Azure Service Bus Data Receiver** + **Azure Service Bus Data Sender** on the queue scope.

The worker does **not** create Service Bus queues or namespaces. It **does** call `create_table_if_not_exists` for the configured sync-state table on startup.

## CLI commands

Entry point: **`src/main.py`**

```bash
uv run python src/main.py --help
uv run python src/main.py worker run
uv run python src/main.py worker run --config /config/config.yaml
```

| Command | Purpose |
| ------- | ------- |
| **`worker run`** | Long-running Service Bus consumer; normalizes ADO lifecycle events and completes messages (slice 3; scope mapping and Snyk sync deferred) |
| **`worker run --config PATH`** | Use a custom operator config file path |

## Sync-state table schema

Table name defaults to **`SnykSyncState`**. Repository state rows use:

| Key | Value |
| --- | ----- |
| `PartitionKey` | `{source}:{scopeId}` where `source` is `ado` or `github` |
| `RowKey` | `{repositoryId}` |

Scope-to-Snyk mapping is **not** stored in Table Storage — it will live in operator config per **`openspec/specs/scope-mapping/spec.md`**.

### Repository row

`PartitionKey={source}:{scopeId}`, `RowKey={repositoryId}`

| Property | Type | Description |
| -------- | ---- | ----------- |
| `repoName` | string | Current repository name |
| `snykTargetId` | string | Snyk target id |
| `defaultBranch` | string | Default branch name |
| `status` | string | Sync status |
| `desiredStateHash` | string | Idempotency hash |
| `lastEventId` | string | Last processed provider event id |
| `tagApplied` | boolean | Repository id tag applied |

Repository rows are written after successful Snyk actions in a follow-up change. The table is created on worker startup when missing.

## Queue message shapes

Queue message bodies are provider-native JSON — not wrapped in a transport envelope.

### ADO (Event Grid schema)

Event Grid JSON with audit record under `data`. The worker detects ADO when `eventType == "AzureDevOpsAuditEvent"` **or** `subject == "AzureDevOps/Auditing"`.

| Field | Description |
| ----- | ----------- |
| `eventType` / `subject` | ADO message detection |
| `data` | Audit record passed to normalization |
| `data.Id` | Event id |
| `data.ActionId` | Lifecycle action (`Git.RepositoryCreated`, etc.) |

See `data/fixtures/eventgrid_ado_*.json` and **[INGESTION.md](INGESTION.md)**.

### GitHub (raw webhook JSON)

Top-level webhook body with `action` and `repository`. See `data/fixtures/github_webhook_created.json`.

See `openspec/specs/event-ingestion/spec.md` for the canonical contract. Step-by-step ingress setup (Service Bus, ADO audit stream, GitHub webhooks): **[INGESTION.md](INGESTION.md)**.

## Normalized lifecycle event (ADO)

After parsing, the worker maps supported ADO audit records into a normalized lifecycle event and completes the message. Scope mapping and repository state access are deferred to follow-up changes. GitHub messages are completed without normalization until a follow-up change.

| Field | ADO audit source | Description |
| ----- | ---------------- | ----------- |
| `eventId` | `Id` | Stable audit event id |
| `eventType` | `ActionId` | `repo.created`, `repo.renamed`, `repo.deleted`, or `repo.default_branch_changed` |
| `scopeId` | `ProjectId` | ADO project id (sync-state partition key) |
| `repositoryId` | `Data.RepoId` | Repository id |
| `occurredAt` | `Timestamp` | Event time |
| `ado.orgId` | `ScopeId` | ADO organization id |
| `ado.orgDisplayName` | `ScopeDisplayName` | Organization display name |
| `ado.projectId` | `ProjectId` | Same as `scopeId` |
| `ado.projectName` | `ProjectName` | Project name |
| `repository.name` | `Data.RepoName` | Repository name |
| `payload.defaultBranch` | `Data.DefaultBranch` | Optional on create; required on default-branch change (`refs/heads/` stripped) |
| `payload.previousDefaultBranch` | `Data.PreviousDefaultBranch` | Present when ADO reports a prior default branch; omitted when empty (no sync action) |
| `payload.previousRepoName` | `Data.PreviousRepoName` | Required on rename |

Supported ADO audit `ActionId` values: `Git.RepositoryCreated`, `Git.RepositoryRenamed`, `Git.RepositoryDeleted`, `Git.RepositoryDefaultBranchChanged`.

## Error handling and logging

- Unparseable or unrecognized queue messages are **dead-lettered** with reason `InvalidMessage`.
- ADO audit records that are unsupported or missing required fields are **dead-lettered** with reason `InvalidNormalization`.
- Valid ADO messages are **normalized and completed** without scope mapping, repository state access, or Snyk side effects in the current slice.
- Valid GitHub messages are **completed** without normalization or sync side effects until GitHub normalization is implemented.
- Logs include parsed source, normalized lifecycle fields for ADO, and queue name.
- Azure SDK connection/link chatter is logged at **WARNING** and above only; application loggers remain at **INFO**.

## Integration tests

Integration tests require a worker config file and Azure credentials (`az login` or service principal with required RBAC). See **[CONTRIBUTING.md § Integration tests](CONTRIBUTING.md#integration-tests)**.

```bash
cp data/config.yaml.example data/config.yaml
# edit data/config.yaml with your dev namespace and storage account
az login
uv run pytest -m integration
```

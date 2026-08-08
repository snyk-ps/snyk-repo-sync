# Configuration reference

Operator reference for environment variables and CLI commands. For installation, usage, and deployment, see the [README](README.md). For Service Bus provisioning and ADO audit stream / GitHub webhook ingress setup, see **[INGESTION.md](INGESTION.md)**. For layout, tests, OpenSpec, and CI/Docker details, see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

The worker Container App is configured entirely via environment secrets injected at deployment time. There is no configuration file.

## Environment variables

**Secrets** must come from the Container App secret store or your platform's equivalent. **Never** commit them in source or logs.

| Variable | Required | Secret | Role |
| -------- | -------- | ------ | ---- |
| **`SERVICEBUS_CONNECTION_STRING`** | Yes | Yes | Azure Service Bus namespace connection string for the **existing** queue |
| **`SERVICEBUS_QUEUE_NAME`** | Yes | No | Name of the pre-provisioned queue the worker consumes |
| **`SNYK_TOKEN`** | For Snyk sync (future) | Yes | Snyk API token |

The worker fails fast at startup when `SERVICEBUS_CONNECTION_STRING` or `SERVICEBUS_QUEUE_NAME` is missing or empty.

## CLI commands

Entry point: **`src/main.py`**

```bash
uv run python src/main.py --help
uv run python src/main.py worker run
```

| Command | Purpose |
| ------- | ------- |
| **`worker run`** | Long-running Service Bus consumer; parses native queue messages, normalizes ADO lifecycle events, and completes messages (slice 2; Snyk sync deferred) |

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

After parsing, the worker maps supported ADO audit records into a normalized lifecycle event before completing the message. GitHub messages are completed without normalization until a follow-up change.

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
- Valid ADO messages are **normalized and completed** without sync state access or Snyk side effects in the current slice.
- Valid GitHub messages are **completed** without normalization or sync side effects until GitHub normalization is implemented.
- Logs include parsed source, normalized lifecycle fields for ADO, and queue name — never connection strings or other secrets.
- Azure Service Bus SDK connection/link chatter is logged at **WARNING** and above only; application loggers remain at **INFO**.

## Integration tests

Integration tests require a configured Service Bus namespace and queue. See **[CONTRIBUTING.md § Integration tests](CONTRIBUTING.md#integration-tests)**.

```bash
export SERVICEBUS_CONNECTION_STRING="..."
export SERVICEBUS_QUEUE_NAME="repo-sync-events"
uv run pytest -m integration
```

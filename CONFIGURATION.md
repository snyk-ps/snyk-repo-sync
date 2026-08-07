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
| **`worker run`** | Long-running Service Bus consumer; validates transport envelopes, normalizes ADO lifecycle events, and completes messages (slice 2; Snyk sync deferred) |

## Transport envelope

Queue message bodies MUST be JSON objects with:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `source` | `"ado"` or `"github"` | Event origin |
| `ingressId` | string | Provider event or delivery identifier |
| `receivedAt` | ISO-8601 UTC | When the external ingress path accepted the event |
| `rawPayload` | object | Provider-native event body |

See `openspec/specs/event-ingestion/spec.md` for the canonical contract. Step-by-step ingress setup (Service Bus, ADO audit stream, GitHub webhooks): **[INGESTION.md](INGESTION.md)**.

## Normalized lifecycle event (ADO)

After envelope validation, the worker maps supported ADO audit records into a normalized lifecycle event before completing the message. GitHub envelopes are completed without normalization until a follow-up change.

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
| `payload.previousDefaultBranch` | `Data.PreviousDefaultBranch` | Required on default-branch change |
| `payload.previousRepoName` | `Data.PreviousRepoName` | Required on rename |

Supported ADO audit `ActionId` values: `Git.RepositoryCreated`, `Git.RepositoryRenamed`, `Git.RepositoryDeleted`, `Git.RepositoryDefaultBranchChanged`.

## Error handling and logging

- Malformed transport envelopes are **dead-lettered** with reason `InvalidEnvelope`.
- ADO audit records that are unsupported or missing required fields are **dead-lettered** with reason `InvalidNormalization`.
- Valid ADO envelopes are **normalized and completed** without sync state access or Snyk side effects in the current slice.
- Valid GitHub envelopes are **completed** without normalization or sync side effects until GitHub normalization is implemented.
- Logs include `source`, `ingress_id`, normalized lifecycle fields for ADO, and queue name — never connection strings or other secrets.

## Integration tests

Integration tests require a configured Service Bus namespace and queue. See **[CONTRIBUTING.md § Integration tests](CONTRIBUTING.md#integration-tests)**.

```bash
export SERVICEBUS_CONNECTION_STRING="..."
export SERVICEBUS_QUEUE_NAME="repo-sync-events"
uv run pytest -m integration
```

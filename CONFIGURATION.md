# Configuration reference

Operator reference for environment variables and CLI commands. For installation, usage, and deployment, see the [README](README.md). For layout, tests, OpenSpec, and CI/Docker details, see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

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
| **`worker run`** | Long-running Service Bus consumer; validates transport envelopes and completes messages (slice 1; normalization deferred) |

## Transport envelope

Queue message bodies MUST be JSON objects with:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `source` | `"ado"` or `"github"` | Event origin |
| `ingressId` | string | Provider event or delivery identifier |
| `receivedAt` | ISO-8601 UTC | When the external ingress path accepted the event |
| `rawPayload` | object | Provider-native event body |

See `openspec/specs/event-ingestion/spec.md` for the canonical contract.

## Error handling and logging

- Malformed transport envelopes are **dead-lettered** with reason `InvalidEnvelope`.
- Valid envelopes are **completed** without normalization or Snyk side effects in the current implementation slice.
- Logs include `source`, `ingress_id`, and queue name only — never connection strings or other secrets.

## Integration tests

Integration tests require a configured Service Bus namespace and queue. See **[CONTRIBUTING.md § Integration tests](CONTRIBUTING.md#integration-tests)**.

```bash
export SERVICEBUS_CONNECTION_STRING="..."
export SERVICEBUS_QUEUE_NAME="repo-sync-events"
uv run pytest -m integration
```

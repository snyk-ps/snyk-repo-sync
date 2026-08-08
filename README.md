# Snyk Azure Repo Sync

Queue-driven worker that consumes repository lifecycle events from Azure Service Bus and syncs Snyk targets for Azure DevOps and GitHub repositories.

External systems (ADO audit stream via Event Grid, GitHub webhooks) publish native JSON to an **existing** Service Bus queue. This application runs as a **worker Container App** that reads from that queue. The current implementation slice parses queue messages, normalizes ADO audit lifecycle events, ensures the sync-state table exists, and completes messages; scope mapping, repository state writes, and Snyk sync follow in subsequent changes.

**Operators:** queue and ingress setup (Service Bus, ADO audit stream, GitHub webhooks) are documented in **[INGESTION.md](INGESTION.md)**. ADO audit events are batched and typically arrive within ~30 minutes.

## Table of contents

- [Installation and setup](#installation-and-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Features](#features)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Deployment](#deployment)
- [More documentation](#more-documentation) — includes [INGESTION.md](INGESTION.md) for Service Bus and ADO ingress

## Installation and setup

### Prerequisites

- **Python** 3.12+ and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**
- Pre-provisioned **Azure Service Bus queue** and **storage account** (the worker does not create queue infrastructure)
- Azure credentials with required RBAC roles (`az login` locally; managed identity in production)

### Development / local installation

1. **Clone** the repository and install dependencies:

```bash
uv sync --dev
```

2. **Configure the worker** — copy the example config and fill in your Azure resource names:

```bash
cp data/config.yaml.example data/config.yaml
```

Edit `data/config.yaml` with your Service Bus namespace, queue name, and Table Storage endpoint. Authenticate with `az login` (or a service principal with the RBAC roles listed in **[CONFIGURATION.md](CONFIGURATION.md)**).

3. **Verify** the install:

```bash
uv run python src/main.py --help
uv run pytest -m "not integration"
```

Optional: build and run the root **`Dockerfile`** locally to mirror production (mount config at `/config/config.yaml`):

```bash
docker build -t snyk-azure-repo-sync .
docker run -v "$(pwd)/data/config.yaml:/config/config.yaml" snyk-azure-repo-sync
```

### Deployment / production installation

1. **Image:** build from this repo's **`Dockerfile`**, or pull a release image from **ghcr.io** after release workflows are enabled (see **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**).
2. **Managed identity:** assign **Azure Service Bus Data Owner** and **Storage Table Data Contributor** to the Container App identity.
3. **Config mount:** mount operator YAML at `/config/config.yaml` (Azure Files).
4. **Entrypoint:** the container runs `python src/main.py worker run --config /config/config.yaml`.

## Configuration

The worker loads **`data/config.yaml`** by default (or **`/config/config.yaml`** in production). Settings may be overridden by environment variables. Full reference: **[CONFIGURATION.md](CONFIGURATION.md)**.

| Setting | Config key | Env override |
| ------- | ---------- | ------------ |
| Service Bus namespace | `serviceBus.fullyQualifiedNamespace` | `SERVICEBUS_FULLY_QUALIFIED_NAMESPACE` |
| Service Bus queue | `serviceBus.queueName` | `SERVICEBUS_QUEUE_NAME` |
| Table Storage endpoint | `syncState.storageAccountEndpoint` | `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT` |
| Table name | `syncState.tableName` | `SYNC_STATE_TABLE_NAME` |

## Usage

Start the worker consumer:

```bash
uv run python src/main.py worker run
```

Or with an explicit config path:

```bash
uv run python src/main.py worker run --config data/config.yaml
```

### VS Code / Cursor debugging

`.vscode/launch.json` includes a **Worker: run** configuration. Ensure `data/config.yaml` exists and you are logged in with `az login`.

## Features

- Consumes native queue messages from a pre-provisioned Service Bus queue (Event Grid JSON for ADO; raw webhook JSON for GitHub)
- Authenticates with `DefaultAzureCredential` and Azure RBAC (no connection strings)
- Parses provider-native message shapes and normalizes ADO audit lifecycle events into a provider-neutral model
- Ensures the sync-state table exists on startup (repository rows written in a follow-up change)
- Scope-to-Snyk mapping via operator config is specified in **`openspec/specs/scope-mapping/spec.md`** (implementation deferred)
- Passes GitHub messages through without normalization (GitHub mapper deferred); Snyk sync deferred

## Testing

**Unit tests** (no Azure credentials required):

```bash
uv run pytest -m "not integration"
```

**Integration tests** (require `data/config.yaml` and `az login`):

```bash
uv run pytest -m integration
```

Fixtures live under `data/fixtures/`. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for test layout and integration test setup.

## Troubleshooting

| Symptom | Likely cause |
| ------- | ------------- |
| Worker exits immediately with config error | `data/config.yaml` missing or incomplete — see **[CONFIGURATION.md](CONFIGURATION.md)** |
| Azure authentication failure | Run `az login` locally or verify managed identity RBAC assignments |
| Integration tests skipped | Config file missing or invalid |
| Messages dead-lettered with `InvalidMessage` | Queue message body is not valid Event Grid JSON (ADO) or GitHub webhook JSON |
| Messages dead-lettered with `InvalidNormalization` | ADO audit record missing required fields or unsupported `ActionId` |

## Deployment

Deploy as an Azure Container App with a managed identity, RBAC role assignments, and config file mount at `/config/config.yaml`. Multiple worker replicas may run independently; each reads and processes messages from the same queue.

The Docker image entrypoint is `python src/main.py worker run --config /config/config.yaml`. Sizing, Dockerfile stages, and GitHub Actions: **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**.

## More documentation

| Document | Audience |
| -------- | -------- |
| **[INGESTION.md](INGESTION.md)** | Service Bus, ADO audit stream, and GitHub webhook ingress setup |
| **[CONFIGURATION.md](CONFIGURATION.md)** | Operator config, RBAC, table schema, CLI commands |
| **[openspec/specs/scope-mapping/spec.md](openspec/specs/scope-mapping/spec.md)** | Scope-to-Snyk mapping (upcoming) |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Project layout, OpenSpec workflow, tests, CI/Docker |
| **[openspec/SPEC.md](openspec/SPEC.md)** | Capability specifications |

# Snyk Azure Repo Sync

Queue-driven worker that consumes repository lifecycle events from Azure Service Bus and syncs Snyk targets for Azure DevOps and GitHub repositories.

External systems (ADO service hooks, GitHub webhooks, Event Grid) publish transport messages to an **existing** Service Bus queue. This application runs as a **worker Container App** that reads from that queue. The current implementation slice validates transport envelopes and completes messages; normalization and Snyk sync follow in a subsequent change.

**Operators:** queue and ingress setup (Service Bus, ADO service hooks, Event Grid audit stream) are documented in **[INGESTION.md](INGESTION.md)**.

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
- Access to an **existing** Azure Service Bus queue (this worker does not provision queue infrastructure)

### Development / local installation

1. **Clone** the repository and install dependencies:

```bash
uv sync --dev
```

2. **Configure local secrets** — copy the template and fill in your Service Bus values:

```bash
cp data/.env.example data/.env
```

Edit `data/.env` with your connection string and queue name. This file is gitignored; never commit real credentials.

3. **Verify** the install:

```bash
uv run python src/main.py --help
uv run pytest -m "not integration"
```

Optional: build and run the root **`Dockerfile`** locally to mirror production:

```bash
docker build -t snyk-azure-repo-sync .
docker run --env-file data/.env snyk-azure-repo-sync
```

### Deployment / production installation

1. **Image:** build from this repo's **`Dockerfile`**, or pull a release image from **ghcr.io** after release workflows are enabled (see **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**).
2. **Secrets:** inject `SERVICEBUS_CONNECTION_STRING` and `SERVICEBUS_QUEUE_NAME` via the Container App secret store.
3. **Entrypoint:** the container runs `python src/main.py worker run`.

## Configuration

The worker is configured entirely via environment variables — there is no config file in production.

| Variable | Required | Role |
| -------- | -------- | ---- |
| `SERVICEBUS_CONNECTION_STRING` | Yes | Service Bus namespace connection string (**secret**) |
| `SERVICEBUS_QUEUE_NAME` | Yes | Name of the pre-provisioned queue |

For local development, set these in **`data/.env`**. Full reference: **[CONFIGURATION.md](CONFIGURATION.md)**.

## Usage

Start the worker consumer:

```bash
uv run python src/main.py worker run
```

Or with explicit env vars:

```bash
export SERVICEBUS_CONNECTION_STRING="Endpoint=sb://..."
export SERVICEBUS_QUEUE_NAME="repo-sync-events"
uv run python src/main.py worker run
```

### VS Code / Cursor debugging

`.vscode/launch.json` includes a **Worker: run** configuration that loads env vars from `data/.env`. Select it from the Run and Debug panel after filling in `data/.env`.

## Features

- Consumes transport messages from a pre-provisioned Service Bus queue
- Validates the shared transport envelope (`source`, `ingressId`, `receivedAt`, `rawPayload`)
- Completes valid messages; dead-letters malformed envelopes
- Supports ADO and GitHub message sources (normalization and Snyk sync deferred)

## Testing

**Unit tests** (no Service Bus required):

```bash
uv run pytest -m "not integration"
```

**Integration tests** (require `data/.env` or exported env vars):

```bash
uv run pytest -m integration
```

Fixtures live under `data/fixtures/`. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for test layout and integration test setup.

## Troubleshooting

| Symptom | Likely cause |
| ------- | ------------- |
| Worker exits immediately with config error | `SERVICEBUS_CONNECTION_STRING` or `SERVICEBUS_QUEUE_NAME` missing — check `data/.env` or Container App secrets |
| Integration tests skipped | Service Bus env vars not set |
| Messages dead-lettered with `InvalidEnvelope` | Queue message body missing required transport fields — see **[CONFIGURATION.md](CONFIGURATION.md)** |

## Deployment

Deploy as an Azure Container App (or equivalent) with Service Bus env secrets. Multiple worker replicas may run independently; each reads and processes messages from the same queue.

The Docker image entrypoint is `python src/main.py worker run`. Sizing, Dockerfile stages, and GitHub Actions: **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**.

## More documentation

| Document | Audience |
| -------- | -------- |
| **[INGESTION.md](INGESTION.md)** | Service Bus, ADO service hooks, and Event Grid / audit stream setup |
| **[CONFIGURATION.md](CONFIGURATION.md)** | Environment variables, CLI commands, transport envelope schema |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Project layout, OpenSpec workflow, tests, CI/Docker |
| **[openspec/SPEC.md](openspec/SPEC.md)** | Capability specifications |

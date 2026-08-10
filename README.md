# Snyk Azure Repo Sync

Queue-driven worker that consumes repository lifecycle events from Azure Service Bus and syncs Snyk targets for Azure DevOps and GitHub repositories.

External systems (ADO audit stream via Event Grid, GitHub webhooks) publish native JSON to an **existing** Service Bus queue. This application runs as a **worker Container App** that reads from that queue, normalizes ADO lifecycle events, syncs mapped repositories to Snyk via async import jobs, and persists sync state in Azure Table Storage. Project tagging is deferred to a follow-up change.

**Operators:** queue and ingress setup (Service Bus, ADO audit stream, GitHub webhooks) are documented in **[INGESTION.md](INGESTION.md)**. ADO audit events are batched and typically arrive within ~30 minutes.

## Table of contents

- [Installation and setup](#installation-and-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Features](#features)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Deployment](#deployment)
  - [Minimum requirements](#minimum-requirements-azure-container-apps)
  - [Azure Container Apps: portal walkthrough](#azure-container-apps-portal-walkthrough)
  - [Optional: KEDA Service Bus scaling](#optional-keda-service-bus-scaling)
  - [Logs and observability](#logs-and-observability)
  - [Deployment troubleshooting](#deployment-troubleshooting)
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

Edit `data/config.yaml` with your Service Bus namespace, queue name, Table Storage endpoint, and optional `scopeMapping` entries. Authenticate with `az login` (or a service principal with the RBAC roles listed in **[CONFIGURATION.md](CONFIGURATION.md)**).

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

Complete **[INGESTION.md](INGESTION.md)** (Service Bus queue, ADO audit stream, GitHub webhooks) **before** deploying the worker. Then follow **[Deployment](#deployment)** for the Azure Container App runbook.

1. **Image:** build from this repo's **`Dockerfile`**, or pull a release image from **ghcr.io** after release workflows are enabled (see **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**).
2. **Managed identity:** assign **Azure Service Bus Data Owner** and **Storage Table Data Contributor** to the Container App identity (see **[CONFIGURATION.md § RBAC](CONFIGURATION.md#rbac)**).
3. **Config mount:** mount operator YAML at `/config/config.yaml` (Azure Files).
4. **Secrets:** inject **`SNYK_TOKEN`** and **`ADO_PAT`** via Container Apps secrets or Key Vault references — never in the image or YAML.
5. **Entrypoint:** the container runs `python src/main.py worker run --config /config/config.yaml` (image default).

## Configuration

The worker loads **`data/config.yaml`** by default (or **`/config/config.yaml`** in production). Settings may be overridden by environment variables. Full reference: **[CONFIGURATION.md](CONFIGURATION.md)**.

| Setting | Config key | Env override |
| ------- | ---------- | ------------ |
| Service Bus namespace | `serviceBus.fullyQualifiedNamespace` | `SERVICEBUS_FULLY_QUALIFIED_NAMESPACE` |
| Service Bus queue | `serviceBus.queueName` | `SERVICEBUS_QUEUE_NAME` |
| Table Storage endpoint | `syncState.storageAccountEndpoint` | `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT` |
| Table name | `syncState.tableName` | `SYNC_STATE_TABLE_NAME` |
| Scope mapping | `scopeMapping` | — (config file only) |

See **[CONFIGURATION.md](CONFIGURATION.md)** for the full `scopeMapping` schema.

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
- Resolves ADO project name → Snyk org id from operator `scopeMapping` config (optional `snykIntegrationId`, optional `defaultSnykOrgId`)
- Syncs mapped ADO repos to Snyk: import with async job polling, configurable target removal (`deactivate` or `delete`), sync-state tracking
- Schedules internal follow-up messages on the same queue for import polling and concurrency backpressure
- Requires `SNYK_TOKEN` in the environment; project tagging deferred
- Passes GitHub messages through without normalization (GitHub mapper deferred)

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
| Worker exits immediately with config error | `data/config.yaml` missing or incomplete, or `SNYK_TOKEN` unset — see **[CONFIGURATION.md](CONFIGURATION.md)** |
| Azure authentication failure | Run `az login` locally or verify managed identity RBAC assignments |
| Integration tests skipped | Config file missing or invalid |
| Messages dead-lettered with `InvalidMessage` | Queue message body is not valid Event Grid JSON (ADO) or GitHub webhook JSON |
| Messages dead-lettered with `InvalidNormalization` | ADO audit record missing required fields or unsupported `ActionId` |
| Log warnings for unmapped ADO project | Add a `scopeMapping.azure-repos` entry for the project name or set `defaultSnykOrgId` — see **[CONFIGURATION.md](CONFIGURATION.md)** |

## Deployment

This section is the **Azure-oriented runbook** for production: sizing, managed identity, config mount, secrets, and a **[portal walkthrough](#azure-container-apps-portal-walkthrough)** for a **queue-driven worker** on **[Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/overview)**.

Deploy the worker as a **Container App** (long-running `worker run` consumer) — **not** a Container App Job. Complete queue and ingress setup in **[INGESTION.md](INGESTION.md)** first. **No Bicep/Terraform** is required in this repo. Image build and release workflow: **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**.

### Minimum requirements (Azure Container Apps)

| Area | Recommendation |
| ---- | -------------- |
| **Process model** | Long-running **`worker run`** receive loop (image default **`worker run --config /config/config.yaml`**) |
| **CPU / memory** | Start around **0.5 vCPU** and **1 GiB**; increase if processing is slow or OOM |
| **Replicas** | **Min replicas: 1** for first production deploy (always consuming). Multiple replicas may run independently on the same queue |
| **Networking** | Outbound **HTTPS** to Snyk API, **`dev.azure.com`** (or your `ado.host`), and your Table Storage endpoint |
| **Secrets** | **`SNYK_TOKEN`** and **`ADO_PAT`** via Key Vault references / Container Apps secrets, not the image or YAML |
| **Identity** | Managed identity with **Azure Service Bus Data Owner** and **Storage Table Data Contributor** — see **[CONFIGURATION.md § RBAC](CONFIGURATION.md#rbac)** |
| **Config** | Non-secret operator YAML mounted at **`/config/config.yaml`** (Azure Files) |

### Azure Container Apps: portal walkthrough

Use a **Container App** (continuous worker), not a Container App Job. The steps below follow the [Quickstart: Deploy your first container app](https://learn.microsoft.com/en-us/azure/container-apps/quickstart-portal) flow and this repo's image default **`worker run --config /config/config.yaml`**. Portal wording varies by version.

#### A. Prepare config in Azure Storage (do this first)

1. In the portal, open **Storage accounts** → **+ Create**.
2. **Basics:** pick subscription, resource group, region, a **globally unique** name, **Performance** Standard, **Redundancy** LRS (or per policy). **Kind** StorageV2 is fine.
3. **Advanced:** ensure **Allow storage account key access** stays **enabled** if you will use the **account key** for the ACA file share link (common for SMB).
4. Create the account, then open it.
5. Under **Data storage** → **File shares** → **+ File share:** create a share (e.g. `snyk-repo-sync-config`).
6. Open the share → **Upload** your **`config.yaml`** (non-secret policy only — `serviceBus`, `syncState`, `ado`, `scopeMapping`, etc.).  
   The object in the share must end up as **`config.yaml`** at the **root** of the share so the mounted path **`/config/config.yaml`** is correct.
7. Under **Security + networking** → **Access keys:** copy **key1** (or **key2**) — you'll paste it when wiring the environment **Volume mount**.

**Networking:** If the storage account uses a **restricted firewall** or **public network access** disabled, SMB mounts from Container Apps can fail (for example **`VolumeMountFailure`** / **`mount error(13): Permission denied`**). The account must be **reachable** from your Container Apps environment. See [Use storage mounts in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts).

#### B. Create the Container Apps environment (with file share link)

You can create the environment **inside** the Container App wizard (**Basics**) or **first** as its own resource. Either way you need one Container Apps environment.

1. Portal search: **Container Apps environments** → open your environment (or create it from the app wizard via **Create new**).
2. Open the environment → **Settings** → **Volume mounts** (or **Storage** / **Azure Files**, depending on portal wording).
3. **Add** a volume mount:
   - **Protocol:** SMB (default for standard Azure Files).
   - **Name:** a short logical name you will reuse on the app (e.g. `configshare`). This is the **environment storage name**, not the Azure share name.
   - **Storage account:** select the account from step **A**.
   - **File share:** select the share that contains **`config.yaml`**.
   - **Access key:** paste the key from step **A** (if the UI asks).
   - **Access mode:** **Read only** is enough if the worker only reads config.
4. **Save** so the environment now lists this Azure Files mount.

#### C. Create the Container App

1. Portal top search: **Container Apps** → **Create**.

**Basics**

- Subscription, **Resource group**
- **Container app name:** e.g. `snyk-repo-sync-worker` (must follow ACA naming rules).
- **Region:** same as the environment (and typically the same as the storage account region).
- **Container Apps environment:** select the environment from **B** (or **Create new**; **Consumption** workload profile is usually fine).

**Container** (main step)

- **Container name:** e.g. `main`
- **Image source:** **Docker Hub or other registries** (or **Azure Container Registry** if you use ACR).
- **Image:** build from this repo's **`Dockerfile`** locally, or after release workflows are enabled pull from **`ghcr.io/<owner>/<repository>:<tag>`** (see **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**). Pin a **tag** or **digest**.
- **CPU and memory:** e.g. **0.5 CPU**, **1.0 Gi** (matches [minimum requirements](#minimum-requirements-azure-container-apps) above).

**Scaling** (or **Scale** step)

- **Min replicas:** **1** (recommended for first deploy).
- **Max replicas:** start with **1–3** unless you enable KEDA scaling (see [Optional: KEDA Service Bus scaling](#optional-keda-service-bus-scaling)).

**Do not** override **ENTRYPOINT** / **command** unless you know you need to; the image default is already **`worker run --config /config/config.yaml`**.

#### D. Secrets and environment variables (portal)

On the app's container configuration (wording varies by blade version). The **create** wizard may not expose **Secrets**; if not, open the deployed **Container App** → **Settings** → **Secrets**, then reference those secrets from **Environment variables** on the container template (same idea as [Manage secrets in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets?tabs=azure-portal)).

**Secrets** (app-level): add at least:

| Secret name | Value |
| ----------- | ----- |
| `snyk-token` | Snyk API token |
| `ado-pat` | Azure DevOps PAT (**Code: Read** — see **[CONFIGURATION.md § ADO PAT permissions](CONFIGURATION.md#ado-pat-permissions)**) |

**Environment variables** for the container:

| Variable | Source |
| -------- | ------ |
| `SNYK_TOKEN` | Reference secret `snyk-token` |
| `ADO_PAT` | Reference secret `ado-pat` |

**Key Vault:** if your org requires it, use Key Vault references on Container Apps secrets instead of pasting values.

#### E. Mount the file share on the app at `/config`

The environment link exists from **B**; the app still needs a **volume + mount** so the file appears as **`/config/config.yaml`**.

1. In the **Container** step (or **Volumes** / **Advanced**), **add a volume:**
   - **Type:** **Azure Files** (backed by the environment mount you named, e.g. `configshare`).
2. **Mount** that volume on the main container:
   - **Mount path:** **`/config`**
   - No **`subPath`** needed if **`config.yaml`** is at the **root** of the share.

If the **create** wizard does not offer volumes, finish **Create**, then open the app → **Containers** / **Revision** / **Edit**, add the **Azure Files** volume and **`/config`** mount, then **save** so a new revision applies.

#### F. Managed identity and RBAC

1. On the **Container App** resource: **Identity** → turn on **System assigned** (or user-assigned per policy).
2. On the **Service Bus** namespace or queue: **Access Control (IAM)** → **Add role assignment** → **Azure Service Bus Data Owner** → assign to the app's identity.
3. On the **Table** storage account: **Access Control (IAM)** → **Add role assignment** → **Storage Table Data Contributor** → assign to the app's identity.
4. Ensure **`serviceBus`**, **`syncState`**, and **`ado`** settings in mounted **`config.yaml`** match your Azure resources — see **[CONFIGURATION.md](CONFIGURATION.md)**.

The worker uses **`DefaultAzureCredential`**; connection strings are **not** supported.

#### G. Deploy, test, logs

1. **Review + create** on the app.
2. Open the app → **Log stream** (or **Monitoring** → **Logs**) and confirm the worker starts without config or auth errors.
3. Publish a test message to the queue (or wait for ADO/GitHub ingress) and verify processing — see [Logs and observability](#logs-and-observability).

**Where to click:** **Log stream** on the Container App; for longer retention, use **Monitoring** → **Logs** on the **Container Apps environment** or **Log Analytics** (`ContainerAppConsoleLogs_CL`).

#### H. If something fails

See [Deployment troubleshooting](#deployment-troubleshooting) below.

### Optional: KEDA Service Bus scaling

After the worker runs reliably with **min replicas = 1**, you may add a **KEDA** scaler on the Container App to scale replica count based on **Service Bus queue depth** (including scale-to-zero with **min replicas = 0**).

1. Open the Container App → **Scale** (or **Scaling rules**).
2. Add a rule with type **Azure Service Bus** (or **Custom** / KEDA scaler, depending on portal version).
3. Configure:
   - **Namespace:** your `serviceBus.fullyQualifiedNamespace` value (without `https://`).
   - **Queue name:** your `serviceBus.queueName`.
   - **Message count threshold:** e.g. `5` active messages per replica (tune to your volume).
   - **Authentication:** managed identity with **Azure Service Bus Data Owner** (or Receiver + Sender) on the queue.
4. Set **max replicas** to handle bursts (e.g. `3–10`). Keep **min replicas = 1** until you have validated scaler behavior; only then consider **min replicas = 0** for cost savings (accept cold-start latency).

See [KEDA scalers in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/monitor-keda-scalers) and [Azure Service Bus scaler](https://keda.sh/docs/latest/scalers/azure-service-bus/).

Multiple replicas safely share one queue; the worker completes or dead-letters messages per Service Bus semantics.

### Logs and observability

The worker emits structured logs to **stdout** (JSON-friendly operational fields: source, scope, repository, event type, import status). In Azure Container Apps:

- **Log stream:** [Container App log streaming](https://learn.microsoft.com/en-us/azure/container-apps/log-streaming) on the app resource.
- **Log Analytics:** query workspace linked to the ACA environment; console output often appears in **`ContainerAppConsoleLogs_CL`**.

For application-level troubleshooting (auth, dead-letter reasons, unmapped scopes), see **[CONFIGURATION.md § Error handling and logging](CONFIGURATION.md#error-handling-and-logging)** and [Troubleshooting](#troubleshooting) above. Dynatrace alerting is defined in `openspec/specs/observability/spec.md` and is out of scope for this runbook.

Recommend **`PYTHONUNBUFFERED=1`** on the container for timely log shipping.

### Deployment troubleshooting

| Issue | What to check |
| ----- | ------------- |
| **Worker exits on startup (config error)** | Mounted share contains **`config.yaml`** at **`/config/config.yaml`**; required keys present — see **[CONFIGURATION.md](CONFIGURATION.md)** |
| **Missing config / file not found** | Mount path is exactly **`/config`**; share root contains **`config.yaml`** |
| **Volume mount / Permission denied** | Storage account **firewall** / **public network access**, wrong **access key** on the environment volume — see step **A** and [Use storage mounts in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts) |
| **Azure authentication failure** | Managed identity enabled; **Service Bus Data Owner** and **Table Data Contributor** assigned at correct scope |
| **Snyk or ADO auth errors** | **`SNYK_TOKEN`** and **`ADO_PAT`** secrets mapped correctly; PAT has **Code (Read)** for mapped ADO projects |
| **No messages processed** | Queue and ingress configured per **[INGESTION.md](INGESTION.md)**; `serviceBus` settings in config match the queue; ADO audit latency (~30 min) is expected |
| **Pull image failed** | **`ghcr.io`** visibility and registry credentials; or build and push your own image per **[CONTRIBUTING.md](CONTRIBUTING.md)** |
| **Messages dead-lettered** | See [Troubleshooting](#troubleshooting) — `InvalidMessage`, `InvalidNormalization`, `ImportJobFailed` |

## More documentation

| Document | Audience |
| -------- | -------- |
| **[INGESTION.md](INGESTION.md)** | Service Bus, ADO audit stream, and GitHub webhook ingress setup |
| **[CONFIGURATION.md](CONFIGURATION.md)** | Operator config, RBAC, table schema, CLI commands |
| **[openspec/specs/scope-mapping/spec.md](openspec/specs/scope-mapping/spec.md)** | Scope-to-Snyk mapping contract |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Project layout, OpenSpec workflow, tests, CI/Docker |
| **[openspec/SPEC.md](openspec/SPEC.md)** | Capability specifications |

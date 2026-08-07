# Event ingestion setup

Operator guide for provisioning **customer-owned queue infrastructure** and **event ingress** that delivers repository lifecycle events to the shared Service Bus queue. The worker in this repository only **consumes** that queue; it does not create Service Bus resources or Event Grid topics.

For worker configuration (`SERVICEBUS_CONNECTION_STRING`, transport envelope schema), see **[CONFIGURATION.md](CONFIGURATION.md)**. Canonical requirements live in `openspec/specs/event-ingestion/spec.md` and `openspec/specs/ado-provisioning/spec.md`.

## Architecture

Repository lifecycle events reach **one pre-provisioned Service Bus queue** via ADO audit stream and GitHub organization webhooks. The worker normalizes queue messages and performs Snyk sync.

```mermaid
flowchart LR
  subgraph ado [Azure DevOps org]
    AS[Audit stream<br/>Git repo lifecycle]
  end

  subgraph gh [GitHub org]
    GHW[Org webhooks]
  end

  subgraph ingress [Customer-owned ingress]
    GWR[GitHub webhook receiver]
    FN[Event Grid handler]
  end

  EG[Event Grid topic]
  SB[(Service Bus queue)]
  W[Worker Container App]

  AS --> EG
  EG --> FN
  GHW --> GWR
  FN -->|transport envelope| SB
  GWR -->|transport envelope| SB
  SB --> W
```

> **Latency note:** ADO audit events are batched by Azure DevOps and typically delivered within **30 minutes or less**. This is expected behavior, not a misconfiguration. GitHub webhook delivery remains near-real-time.

| ADO lifecycle event | Audit `ActionId` | Path | Scope |
| ------------------- | ---------------- | ---- | ----- |
| Repository created | `Git.RepositoryCreated` | Audit stream → Event Grid → ingress → Service Bus | Organization |
| Repository renamed | `Git.RepositoryRenamed` | Audit stream → Event Grid → ingress → Service Bus | Organization |
| Repository deleted | `Git.RepositoryDeleted` | Audit stream → Event Grid → ingress → Service Bus | Organization |
| Default branch changed | `Git.RepositoryDefaultBranchChanged` | Audit stream → Event Grid → ingress → Service Bus | Organization |

All ADO Git repository lifecycle events use the **audit stream** exclusively. GitHub default branch changes use organization webhooks (see `openspec/specs/github-webhook-ingestion/spec.md`).

---

## 1. Service Bus setup

Provision queue infrastructure **outside this repository** before deploying the worker or ingress.

### Create namespace and queue

**Azure Portal**

1. Create an **Azure Service Bus** namespace (Standard or Premium tier).
2. Under **Entities → Queues**, create a queue (for example `repo-sync-events`).
3. Recommended queue settings:
   - **Max delivery count**: `10` (align with worker retry policy when implemented).
   - **Lock duration**: default (`60` seconds) unless messages require longer processing.
   - **Dead-lettering on message expiration**: enabled.
4. Under **Shared access policies**, create or use policies with least privilege:
   - **Audit-stream ingress handler**: `Send` only.
   - **GitHub webhook ingress**: `Send` only.
   - **Worker**: `Listen` (and `Manage` if the worker dead-letters messages).

**Azure CLI**

```bash
RESOURCE_GROUP=rg-snyk-repo-sync
LOCATION=eastus
NAMESPACE=snyk-repo-sync-sb
QUEUE=repo-sync-events

az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

az servicebus namespace create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$NAMESPACE" \
  --location "$LOCATION" \
  --sku Standard

az servicebus queue create \
  --resource-group "$RESOURCE_GROUP" \
  --namespace-name "$NAMESPACE" \
  --name "$QUEUE" \
  --max-delivery-count 10 \
  --enable-dead-lettering-on-message-expiration true
```

### Connection strings

Retrieve connection strings from **Settings → Shared access policies** (or via CLI):

```bash
az servicebus namespace authorization-rule keys list \
  --resource-group "$RESOURCE_GROUP" \
  --namespace-name "$NAMESPACE" \
  --name RootManageSharedAccessKey \
  --query primaryConnectionString \
  --output tsv
```

Store secrets in Key Vault or your Container App secret store. **Never** commit connection strings to source control.

| Consumer | Variables / secrets |
| -------- | ------------------- |
| Worker | `SERVICEBUS_CONNECTION_STRING`, `SERVICEBUS_QUEUE_NAME` |
| Audit-stream ingress handler | Send-capable connection string and queue name |
| GitHub webhook ingress | Send-capable connection string and queue name |

---

## 2. Transport envelope

All queue messages MUST use the shared transport envelope. Ingress wraps provider-native payloads; the worker unwraps and normalizes them.

| Field | Type | Description |
| ----- | ---- | ----------- |
| `source` | `"ado"` or `"github"` | Event origin |
| `ingressId` | string | Audit record `Id` (ADO) or GitHub delivery GUID |
| `receivedAt` | ISO-8601 UTC | When ingress accepted the event |
| `rawPayload` | object | Audit record (ADO) or GitHub webhook body |

**ADO audit stream example** (see `data/fixtures/transport_envelope_ado.json`):

```json
{
  "source": "ado",
  "ingressId": "2516162638822006204;00000064-0000-8888-8000-000000000000;c8cf06d1-d056-4643-807e-38720b986dca",
  "receivedAt": "2026-08-06T17:21:57.799Z",
  "rawPayload": {
    "Id": "2516162638822006204;00000064-0000-8888-8000-000000000000;c8cf06d1-d056-4643-807e-38720b986dca",
    "ActionId": "Git.RepositoryDefaultBranchChanged",
    "ProjectId": "da9734d4-a91a-4f03-814b-ecc721fe24d1",
    "ProjectName": "snykDemoProject",
    "Timestamp": "2026-08-06T17:21:57.7993795Z",
    "Data": {
      "RepoId": "90bd6b5e-0fbd-4edc-a10e-6604fe76027d",
      "RepoName": "juice-shop.git",
      "DefaultBranch": "refs/heads/develop",
      "PreviousDefaultBranch": "refs/heads/master"
    }
  }
}
```

Use the audit record **`Id`** field as `ingressId`. Put the audit fields (not the Event Grid wrapper) in `rawPayload`.

Supported ADO audit `ActionId` values:

| Lifecycle event | `ActionId` |
| --------------- | ---------- |
| Repository created | `Git.RepositoryCreated` |
| Repository renamed | `Git.RepositoryRenamed` |
| Repository deleted | `Git.RepositoryDeleted` |
| Default branch changed | `Git.RepositoryDefaultBranchChanged` |

---

## 3. ADO audit stream and Event Grid

All ADO repository lifecycle events are detected via the **audit stream** (organization scope).

### Prerequisites

- ADO organization backed by **Microsoft Entra ID**
- **Auditing enabled**: Organization settings → **Policies** → enable audit logging (`Policy.LogAuditEvents`)
- Permissions: **Manage audit streams** (Project Collection Administrator or granted explicitly)
- Azure Event Grid **custom topic** using **Event Grid Schema** (not CloudEvents)

### Step 1: Create Event Grid topic

**Azure Portal**

1. **Create a resource** → **Event Grid Topic** (custom topic).
2. On the **Advanced** tab, set **Event Schema** to **Event Grid Schema** (required by ADO).
3. After deployment, copy **Topic Endpoint** and **Access Key 1**.

**Azure CLI**

```bash
az eventgrid topic create \
  --name ado-audit-events \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --input-schema EventGridSchema
```

### Step 2: Connect ADO audit stream to Event Grid

1. Go to `https://dev.azure.com/{organization}` → **Organization settings** → **Auditing**.
2. Open the **Streams** tab → **New stream** → **Event Grid**.
3. Paste the **Topic Endpoint** and **Access Key**.
4. Select **Set up**.

Audit events are **batched** and typically arrive within **30 minutes or less**. An org can have at most **two streams per target type**.

Microsoft reference: [Create audit streaming for Azure DevOps](https://learn.microsoft.com/en-us/azure/devops/organizations/audit/auditing-streaming?view=azure-devops).

### Step 3: Event Grid subscription with filter

Create a subscription on the topic that forwards **Git repository lifecycle events**.

| Setting | Value |
| ------- | ----- |
| Event schema | Event Grid Schema |
| Filter type | Advanced filters |
| Key | `data.ActionId` |
| Operator | String in |
| Values | `Git.RepositoryCreated`, `Git.RepositoryRenamed`, `Git.RepositoryDeleted`, `Git.RepositoryDefaultBranchChanged` |

Optional additional filter for a single ADO project:

| Key | Value |
| --- | ----- |
| `data.ProjectId` | `{project-guid}` |

**Azure CLI**

```bash
TOPIC_ID=$(az eventgrid topic show \
  --name ado-audit-events \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

az eventgrid event-subscription create \
  --name ado-lifecycle-to-function \
  --source-resource-id "$TOPIC_ID" \
  --endpoint-type azurefunction \
  --endpoint "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Web/sites/{app}/functions/{name}" \
  --advanced-filter data.ActionId StringIn Git.RepositoryCreated Git.RepositoryRenamed Git.RepositoryDeleted Git.RepositoryDefaultBranchChanged
```

Replace the endpoint with your Azure Function, webhook, or Logic App URL.

### Step 4: Forward to Service Bus (ingress handler)

Event Grid delivers messages in **Event Grid schema** (`eventType: AzureDevOpsAuditEvent`, audit fields nested under `data`). A direct Event Grid → Service Bus subscription does **not** produce transport envelopes.

Use an ingress component (recommended: **Azure Function** with Event Grid trigger) that:

1. Receives the Event Grid event.
2. Confirms `data.ActionId` is one of the four supported Git repository lifecycle values (defense in depth if the subscription filter is misconfigured).
3. Builds the transport envelope:
   - `source`: `"ado"`
   - `ingressId`: audit record `data.Id`
   - `receivedAt`: current UTC timestamp
   - `rawPayload`: the audit record object from `data` (same shape as the ADO audit log export)
4. Sends the envelope JSON to the Service Bus queue.

**Audit fields used downstream**

| Field | Use |
| ----- | --- |
| `ScopeId` | ADO org id → normalized `ado.orgId` |
| `ScopeDisplayName` | ADO org display name → normalized `ado.orgDisplayName` |
| `ProjectId` | ADO project id → normalized `scopeId` / `ado.projectId` |
| `ProjectName` | ADO project name → normalized `ado.projectName` |
| `Data.RepoId` | Repository id → normalized `repositoryId` |
| `Data.RepoName` | Repository name → normalized `repository.name` |
| `Data.PreviousRepoName` | Previous repo name on rename → normalized `payload.previousRepoName` |
| `Data.DefaultBranch` | New default branch (`refs/heads/...`) → normalized `payload.defaultBranch` |
| `Data.PreviousDefaultBranch` | Previous default branch → normalized `payload.previousDefaultBranch` |
| `Timestamp` | Event time → normalized `occurredAt` |

See **[CONFIGURATION.md](CONFIGURATION.md)** for the full normalized lifecycle event schema.

### Verify end-to-end

1. Trigger a lifecycle action in ADO (create/rename/delete repo or change default branch).
2. Confirm the event appears in **Organization settings → Auditing** with the expected `ActionId`.
3. Within ~30 minutes, check Event Grid topic **Metrics → Publish Success Count**.
4. Confirm your subscription endpoint receives the filtered event.
5. Confirm a transport envelope message appears on the Service Bus queue.
6. Confirm the worker logs receipt (or run integration tests — see **[CONFIGURATION.md § Integration tests](CONFIGURATION.md#integration-tests)**).

---

## Troubleshooting

| Symptom | Likely cause |
| ------- | ------------- |
| Lifecycle change in audit log but not on queue yet | **Normal batch delay** — wait up to ~30 minutes before investigating further |
| Event on queue hours after the action | Audit stream disabled or Event Grid subscription misconfigured (not latency alone) |
| Audit stream disabled | Auditing policy off; stream access key rotated without updating ADO |
| No Event Grid publishes | Stream not enabled; wrong Event Grid schema (must be Event Grid Schema) |
| Subscription never delivers | Advanced filter key wrong — use `data.ActionId`, not `ActionId` |
| Lifecycle change in audit log but never on queue | Event Grid subscription missing; ingress handler not republishing |
| Worker dead-letters with `InvalidEnvelope` | Queue message missing `source`, `ingressId`, `receivedAt`, or `rawPayload` |
| Worker dead-letters with `InvalidNormalization` | ADO audit record unsupported or missing required org/project/repo/branch fields |

---

## Related documentation

| Document | Content |
| -------- | ------- |
| **[CONFIGURATION.md](CONFIGURATION.md)** | Worker env vars, CLI, envelope validation |
| **[README.md](README.md)** | Worker install, run, deploy |
| **`openspec/specs/event-ingestion/spec.md`** | Canonical ingress contract |
| **`openspec/specs/ado-provisioning/spec.md`** | ADO audit stream provisioning requirements |
| **`data/fixtures/transport_envelope_ado.json`** | Sample ADO audit transport envelope |

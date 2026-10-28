# Event ingestion setup

Operator guide for provisioning customer-owned event ingress and queue infrastructure. Service Bus is the default and recommended transport. Kafka deployments use private connector-pushed HTTP ingress and an Azure Storage Queue for internal follow-ups.

For worker configuration (operator config file, RBAC, queue message shapes), see **[CONFIGURATION.md](CONFIGURATION.md)**. After queue and ingress are ready, deploy the worker per **[README § Deployment](README.md#deployment)**. Canonical requirements live in `openspec/specs/event-ingestion/spec.md` and `openspec/specs/ado-provisioning/spec.md`.

## Architecture

Repository lifecycle events reach the worker through the selected transport. Service Bus carries ADO, GitHub, and internal follow-up messages. On the Kafka path, an event connector sends GitHub events to the worker over HTTP, and an Azure Storage Queue carries internal follow-ups.

```mermaid
flowchart LR
  subgraph ado["Azure DevOps Organization"]
    AS["Audit stream<br/>Git repo lifecycle"]
  end

  subgraph ingress["Azure Event Grid"]
    EG["Custom topic"]
    SUB["Subscription<br/>subject and ActionId filters"]
  end

  subgraph gh["GitHub Organization"]
    GHW["Organization webhooks"]
  end

  subgraph kafka_path["Kafka path"]
    K{{"Kafka topic"}}
    EC["Event connector"]
    SQ[("Storage Queue<br/>internal follow-ups")]
  end

  GWR["GitHub webhook receiver"]
  SB[("Service Bus queue")]
  W["Worker Container App"]

  AS --> EG
  EG --> SUB
  SUB -->|"Event Grid JSON"| SB
  GHW --> GWR
  GWR -->|"webhook JSON"| SB
  SB --> W
  K --> EC
  EC -->|"private POST /github-events"| W
  W -->|"schedule and consume follow-ups"| SQ
```

> **Latency note:** ADO audit events are batched by Azure DevOps and typically delivered within **30 minutes or less**. This is expected behavior, not a misconfiguration. GitHub webhook delivery remains near-real-time.

| ADO lifecycle event | Audit `ActionId` | Path | Scope |
| ------------------- | ---------------- | ---- | ----- |
| Repository created | `Git.RepositoryCreated` | Audit stream → Event Grid → Service Bus | Organization |
| Repository renamed | `Git.RepositoryRenamed` | Audit stream → Event Grid → Service Bus | Organization |
| Repository deleted | `Git.RepositoryDeleted` | Audit stream → Event Grid → Service Bus | Organization |
| Default branch changed | `Git.RepositoryDefaultBranchChanged` | Audit stream → Event Grid → Service Bus | Organization |

All ADO Git repository lifecycle events use the **audit stream** exclusively. GitHub default branch changes use organization webhooks (see `openspec/specs/github-webhook-ingestion/spec.md`).

### Alternate path: Kafka events and a storage queue

Some GitHub deployments set `messaging.transport: kafka`. On that path:

- The event connector reads GitHub lifecycle events from Kafka and sends the provider-native JSON body to `POST /github-events`.
- The worker returns `204 No Content` only after synchronous lifecycle processing and durable follow-up scheduling succeed. The connector must retry every non-2xx response.
- `import_poll` and `lifecycle_deferred` messages go to a pre-provisioned Azure Storage queue in the **same storage account** as the sync-state table. Provision that queue and a poison queue (`{queueName}-poison` unless overridden). The worker does not create them.
- ADO audit ingestion stays on the Service Bus path above.
- The worker does not publish to Kafka or copy inbound GitHub bodies to the Storage Queue.

The endpoint has no application authentication. Do not create a public route. Configure customer-managed private networking so only the event connector can reach the configured `http.bindHost` and `http.port`. Terminate TLS and enforce source restrictions in the deployment network. Set the connector request timeout longer than the worker's initial synchronous processing time.

The endpoint accepts `renamed`, `edited`, `deleted`, and the parsed updated body in `data/fixtures/github_parsed_updated.json`. That body has top-level `repository` and `newPropertyValues` and is the GitHub import. It selects the Snyk org from `scopeMapping` property values when `collectionPath` is `newPropertyValues`. It rejects `created` and ADO payloads. Importing from this event does not deactivate an existing Azure DevOps Snyk target.

Assign the worker identity **Storage Queue Data Contributor** on the storage account and **Storage Table Data Contributor** on the table or account. Configure `storageQueue` and `http` as described in **[CONFIGURATION.md](CONFIGURATION.md)**. Keep minimum replicas at one because this guide does not define a Storage Queue scaler.

The rest of this document is the Service Bus path.

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

### Worker authentication (RBAC)

The worker uses **`DefaultAzureCredential`** and operator config — not Service Bus connection strings. Assign the Container App managed identity:

| Role | Scope |
| ---- | ----- |
| **Azure Service Bus Data Owner** | Service Bus namespace or queue |
| **Storage Table Data Contributor** | Storage account |

Mount operator config at `/config/config.yaml` with `serviceBus.fullyQualifiedNamespace`, `serviceBus.queueName`, and `syncState.storageAccountEndpoint`. See **[CONFIGURATION.md](CONFIGURATION.md)**. Deploy the worker Container App after ingress is live — **[README § Deployment](README.md#deployment)**.

Local development: `az login` with the same RBAC roles on your dev namespace and storage account.

### GitHub webhook ingress credentials

GitHub webhook ingress (customer-owned) may use a send-capable Service Bus connection string or RBAC, depending on your ingress implementation. Store credentials in Key Vault or your ingress secret store. **Never** commit secrets to source control.

---

## 2. Queue message shapes

The worker consumes **provider-native JSON** from Service Bus. There is no transport envelope wrapper.

### ADO (Event Grid schema)

Event Grid delivers audit events directly to the Service Bus queue. The message body is Event Grid JSON; the audit record is nested under `data`.

| Field | Use |
| ----- | --- |
| `eventType` | ADO detection (`AzureDevOpsAuditEvent`) |
| `subject` | ADO detection (`AzureDevOps/Auditing`) |
| `data` | Audit record passed to normalization |
| `data.Id` | Event id |
| `data.ActionId` | Lifecycle action |
| `data.ScopeId`, `data.ProjectId`, `data.Data.*` | Normalized org/project/repo/branch |

**Example** (see `data/fixtures/eventgrid_ado_default_branch_changed.json`):

```json
{
  "subject": "AzureDevOps/Auditing",
  "eventType": "AzureDevOpsAuditEvent",
  "data": {
    "Id": "acf86b70-4ec3-4052-9e0b-fbcdd5109c1f",
    "ActionId": "Git.RepositoryDefaultBranchChanged",
    "ScopeId": "c638432a-7f35-450f-984f-372b9d46a376",
    "ScopeDisplayName": "torstencannell (Organization)",
    "ProjectId": "da9734d4-a91a-4f03-814b-ecc721fe24d1",
    "ProjectName": "snykDemoProject",
    "Timestamp": "2026-08-06T17:31:52.3273845Z",
    "Data": {
      "RepoId": "90bd6b5e-0fbd-4edc-a10e-6604fe76027d",
      "RepoName": "juice-shop.git",
      "DefaultBranch": "refs/heads/master",
      "PreviousDefaultBranch": "refs/heads/develop"
    }
  }
}
```

Supported ADO audit `ActionId` values:

| Lifecycle event | `ActionId` |
| --------------- | ---------- |
| Repository created | `Git.RepositoryCreated` |
| Repository renamed | `Git.RepositoryRenamed` |
| Repository deleted | `Git.RepositoryDeleted` |
| Default branch changed | `Git.RepositoryDefaultBranchChanged` |

### GitHub (three supported JSON shapes)

The worker detects raw webhook and parsed lifecycle JSON by top-level `repository` and `action`. It detects the updated import when `repository` is an object, `newPropertyValues` is an array, and `action` is not a non-empty string. That check runs before the parsed-contract `deliveryId` rule.

| Shape | Detection | Idempotency `eventId` |
| ----- | --------- | --------------------- |
| Parsed updated | `repository` object, `newPropertyValues` array, no `action` | `deliveryId` |
| Parsed contract | top-level `deliveryId` | `deliveryId` |
| Raw webhook | otherwise | `repository.updated_at`-based fallback or ingress metadata |

**Scope:** `repository.owner.login` when `owner.type` is `Organization` (sync-state partition `github:{orgLogin}`). Snyk org selection can use a configured property value instead of the org login. For the updated fixture the extractor path is `newPropertyValues`. See **[CONFIGURATION.md](CONFIGURATION.md)**.

**Actions:**

| Inbound signal | Normalized lifecycle |
| -------------- | -------------------- |
| Parsed updated body | `repo.created` (the import for this contract). `occurredAt` is `repository.updatedAt` |
| `created` | `repo.created` for existing raw webhook and parsed lifecycle fixtures |
| `renamed` | `repo.renamed` (`changes.repository.name.from` → previous name when present) |
| `deleted` | `repo.deleted` |
| `edited` | `repo.default_branch_changed` only when `changes.default_branch.from` is set; otherwise no sync |

Fixtures: `data/fixtures/github_webhook_*.json`, `data/fixtures/github_parsed_*.json`, including `github_parsed_updated.json`.

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

Create a subscription on the topic that forwards **Git repository lifecycle events** directly to the Service Bus queue.

| Setting | Value |
| ------- | ----- |
| Event schema | Event Grid Schema |
| Endpoint type | Service Bus queue |
| Filter type | Advanced filters |
| Filter 1 key | `subject` |
| Filter 1 operator | String in |
| Filter 1 values | `AzureDevOps/Auditing` |
| Filter 2 key | `data.ActionId` |
| Filter 2 operator | String in |
| Filter 2 values | `Git.RepositoryCreated`, `Git.RepositoryRenamed`, `Git.RepositoryDeleted`, `Git.RepositoryDefaultBranchChanged` |

Do **not** set `includedEventTypes`; advanced filters alone limit delivery.

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
  --name ado-lifecycle-to-servicebus \
  --source-resource-id "$TOPIC_ID" \
  --endpoint-type servicebusqueue \
  --endpoint "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.ServiceBus/namespaces/{ns}/queues/{queue}" \
  --advanced-filter subject StringIn AzureDevOps/Auditing \
  --advanced-filter data.ActionId StringIn \
    Git.RepositoryCreated \
    Git.RepositoryRenamed \
    Git.RepositoryDeleted \
    Git.RepositoryDefaultBranchChanged
```

Replace the endpoint with your Service Bus namespace and queue resource ID.

### Step 4: Audit fields used downstream

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
5. Confirm an Event Grid JSON message appears on the Service Bus queue.
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
| Lifecycle change in audit log but never on queue | Event Grid subscription missing or filters misconfigured |
| Worker dead-letters with `InvalidMessage` | Queue message is not valid Event Grid JSON (ADO) or GitHub webhook JSON |
| Worker dead-letters with `InvalidNormalization` | ADO audit record unsupported or missing required org/project/repo/branch fields |

---

## Related documentation

| Document | Content |
| -------- | ------- |
| **[CONFIGURATION.md](CONFIGURATION.md)** | Worker env vars, CLI, queue message shapes |
| **[README.md](README.md)** | Worker install, run, deploy |
| **`openspec/specs/event-ingestion/spec.md`** | Canonical ingress contract |
| **`openspec/specs/ado-provisioning/spec.md`** | ADO audit stream provisioning requirements |
| **`data/fixtures/eventgrid_ado_default_branch_changed.json`** | Sample ADO Event Grid queue message |

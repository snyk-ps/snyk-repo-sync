## Context

- Worker entrypoint: `python src/main.py worker run --config /config/config.yaml` (Dockerfile default).
- Long-running Service Bus consumer; schedules internal follow-up messages (`import_poll`, `lifecycle_deferred`) on the same queue.
- Auth: `DefaultAzureCredential` + RBAC (no connection strings).
- Secrets: `SNYK_TOKEN`, `ADO_PAT` (env / Key Vault → Container Apps secrets).
- Policy: non-secret YAML at `/config/config.yaml` (Azure Files mount).
- Ingress (Service Bus queue, Event Grid, webhooks) is customer-owned — documented in INGESTION.md; worker docs assume queue already exists.
- Reference template: `data/tmp_context/README.md` (Azure Boards Integration) — adapt structure, not the scheduled Job deployment model.

## Goals / Non-Goals

**Goals:**

- Operators can deploy the worker to Azure Container Apps without reading source code.
- Document **Container App only** with optional **KEDA Service Bus scaler**.
- Portal walkthrough parity with the Boards integration doc quality bar.

**Non-Goals:**

- Container App Job deployment (scheduled or event-triggered).
- IaC samples, multi-region, private VNet-only topologies (mention constraints only).
- Documenting ingress provisioning (stays in INGESTION.md).

## Decisions

### Azure Container App only

Deploy the worker as a **Container App** (not a Container App Job):

| Aspect | Guidance |
|--------|----------|
| Resource type | Container App in a Container Apps environment |
| Process | `worker run --config /config/config.yaml` (image default) — long-running receive loop |
| Scaling | Min replicas `1` for first deploy; optional KEDA Service Bus scaler for scale-out / scale-to-zero |
| Identity | Managed identity + RBAC (Service Bus Data Owner, Table Data Contributor) |
| Config | Azure Files → `/config/config.yaml` |
| Secrets | `SNYK_TOKEN`, `ADO_PAT` via Container Apps secrets or Key Vault references |

Container App Jobs are **not** in scope — this worker is a continuous queue consumer, not a batch or scheduled job.

### Scaling: min replicas 1 first, KEDA optional

Document **min replicas = 1** as the recommended first production deploy (always consuming, simplest ops). Add an optional subsection for KEDA Service Bus scaling (min `0`, scale on active message count) after operators validate behavior.

**Alternative rejected:** KEDA-only from day one — cold-start latency and scaler misconfiguration risk make `min replicas = 1` safer for initial rollout.

### Documentation structure (README.md)

Adapt sections from `data/tmp_context/README.md`:

| Section | Adaptation for repo-sync |
|---------|--------------------------|
| Deployment intro | Queue-driven worker on Container App; link INGESTION.md for queue setup |
| Minimum requirements | CPU/memory (start 0.5 vCPU / 1 GiB), outbound HTTPS (Snyk, ADO, Table), min/max replicas |
| Portal walkthrough | **Container App** create flow (not Job): environment + file share, app create, secrets, volume mount, identity, RBAC |
| Azure Files config mount | Same A→E pattern as tmp_context (storage account, share, environment volume, mount `/config`) |
| Managed identity + RBAC | Service Bus Data Owner + Table Data Contributor; link CONFIGURATION.md |
| Secrets table | `SNYK_TOKEN`, `ADO_PAT` |
| Sizing / replicas | KEDA message-count scaling as optional; note multiple replicas share one queue safely |
| Logs | ACA log stream / Log Analytics; structured stdout |
| Troubleshooting table | Auth, missing config, volume mount, RBAC, image pull — worker-specific |

Remove from template: cron expressions, replica timeout for batch sync, work-item sizing heuristics, Boards-specific terminology.

### Cross-links

- **CONFIGURATION.md:** Deployment section pointer; RBAC table already references "Container App managed identity".
- **INGESTION.md:** "Deploy worker after queue + ingress" ordering note.
- **CONTRIBUTING.md:** Keep CI/Docker details; avoid duplicating portal steps.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Operators copy Boards **scheduled Job** walkthrough from tmp_context | Explicit callout: create **Container App**, not Container App Job; step C uses App wizard |
| KEDA misconfiguration leaves queue unprocessed | Document min replicas `1` as safe default; KEDA as optional enhancement |
| Portal UI drift | Link Microsoft quickstarts; label steps "wording varies by portal version" |
| ghcr.io image not yet published | Document build-from-Dockerfile path; link CONTRIBUTING.md for release workflow |

## Open Questions

_None — min replicas `1` default and Container App-only scope adopted per proposal review._

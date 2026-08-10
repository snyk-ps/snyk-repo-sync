## Why

Operators can provision ingress and configure the worker locally, but production deployment guidance is still a single paragraph in README.md. The sibling **Azure Boards Integration** documents a full Azure Container Apps runbook (portal walkthrough, config mount, secrets, identity, sizing). This repo needs equivalent operator documentation adapted for a **queue-driven worker** on Azure Container Apps — not a scheduled batch job.

## What Changes

- Expand **README.md** `Deployment` into a full Azure-oriented runbook: minimum requirements, managed identity + RBAC, config mount at `/config/config.yaml`, secrets (`SNYK_TOKEN`, `ADO_PAT`), networking, sizing, and log locations.
- Add an **Azure Container Apps portal walkthrough** (adapted from `data/tmp_context/README.md`) for deploying the worker image with default `worker run --config /config/config.yaml`.
- Document **KEDA Service Bus scaling** as the optional scale-out / scale-to-zero pattern for queue depth.
- Cross-link from **CONFIGURATION.md** (RBAC, secrets, env vars) and **INGESTION.md** (ingress completes before worker deploy).
- No application code, Dockerfile, or infrastructure-as-code changes.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-worker`: Add requirement that operator documentation describes Azure Container App deployment (identity, config mount, secrets, queue-driven scaling) in README.md.

## Impact

- **Docs only:** README.md (primary), minor cross-links in CONFIGURATION.md and INGESTION.md.
- **Reference material:** `data/tmp_context/README.md` as a structural template; replace Boards/scheduled-Job specifics with repo-sync worker/Container App/KEDA specifics.
- **No code, dependencies, or CI changes.**

## Non-goals

- Bicep, Terraform, or ARM templates in this repo.
- Container App Job deployment (scheduled or event-triggered) — not documented in this change.
- Dynatrace / Log Analytics alert rule authoring (observability spec defers to Dynatrace; docs may note stdout → ACA logs).
- GitHub Container Registry release workflow documentation beyond existing CONTRIBUTING.md pointers.
- Changing worker startup model (env-only config, batch mode, etc.).

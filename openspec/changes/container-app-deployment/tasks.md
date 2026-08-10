## 1. README.md — Deployment runbook

- [ ] 1.1 Replace brief Deployment section with full Azure-oriented runbook intro (queue-driven worker, link INGESTION.md)
- [ ] 1.2 Add **Minimum requirements** table (CPU/memory, networking, replicas, secrets, identity)
- [ ] 1.3 Add portal walkthrough adapted from `data/tmp_context/README.md`:
  - [ ] 1.3.a Azure Storage + file share for `config.yaml`
  - [ ] 1.3.b Container Apps environment volume mount
  - [ ] 1.3.c Create **Container App** (not Container App Job): image, resources, default command
  - [ ] 1.3.d Secrets and env vars (`SNYK_TOKEN`, `ADO_PAT`)
  - [ ] 1.3.e Mount `/config` from Azure Files
  - [ ] 1.3.f Managed identity + RBAC assignment steps
  - [ ] 1.3.g Optional KEDA Service Bus scaling configuration
  - [ ] 1.3.h Deploy, verify logs, troubleshooting table
- [ ] 1.4 Add **Logs and observability** pointer (stdout, ACA log stream, link CONFIGURATION.md troubleshooting)
- [ ] 1.5 Update Table of contents and **Deployment / production installation** cross-links

## 2. Cross-document updates

- [ ] 2.1 **CONFIGURATION.md:** add deployment pointer at top / RBAC section → README Deployment
- [ ] 2.2 **INGESTION.md:** note deploy worker after queue + ingress; link README Deployment
- [ ] 2.3 **CONTRIBUTING.md:** ensure no duplicate portal content; keep Docker/CI reference only

## 3. Quality

- [ ] 3.1 Review all doc links (internal anchors, Microsoft Learn URLs)
- [ ] 3.2 Remove any leftover Boards-integration-specific terminology (work items, cron, `sync` command)
- [ ] 3.3 Confirm no Container App Job references remain in deployment docs
- [ ] 3.4 Peer review: operator without repo access can follow walkthrough

## 4. OpenSpec archive

- [ ] 4.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/container-app-deployment/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive container-app-deployment` after review and merge

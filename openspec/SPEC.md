# OpenSpec Capabilities

Canonical specifications for this project. Each capability has a dedicated spec under `openspec/specs/`.

| Capability | Path | Description |
| --- | --- | --- |
| ado-provisioning | `openspec/specs/ado-provisioning/spec.md` | Provision ADO audit stream with Event Grid subscription filters and direct Service Bus delivery for Git repository lifecycle events (operator guide in INGESTION.md). |
| event-ingestion | `openspec/specs/event-ingestion/spec.md` | Deliver ADO Event Grid JSON and GitHub webhook JSON to a single Service Bus queue; no transport envelope; lifecycle normalization owned by the worker. |
| github-provisioning | `openspec/specs/github-provisioning/spec.md` | Provision GitHub organization webhooks so repository lifecycle events reach the webhook ingress endpoint. |
| github-webhook-ingestion | `openspec/specs/github-webhook-ingestion/spec.md` | Receive GitHub organization repository webhooks on customer-owned ingress, validate authenticity, deduplicate deliveries, and publish raw webhook JSON to the Service Bus queue. |
| ignored-repos | `openspec/specs/ignored-repos/spec.md` | Ignore-policy file (YAML/JSON) with explicit repos and name patterns; event-time enforcement and background reconciliation. |
| observability | `openspec/specs/observability/spec.md` | Structured logging to Dynatrace and alerting on dead-letter queue and unrecoverable failures. |
| repo-lifecycle | `openspec/specs/repo-lifecycle/spec.md` | Event-to-action handlers for repository create, rename, default branch change, and delete across ADO and GitHub sources. |
| snyk-target-sync | `openspec/specs/snyk-target-sync/spec.md` | Snyk Import, target deactivation, project tagging, import-job polling, and rate-limit backoff for ADO and GitHub repository lifecycle sync. |
| sync-state | `openspec/specs/sync-state/spec.md` | Azure Table Storage schema for per-repository sync state (idempotency and target tracking). |
| scope-mapping | `openspec/specs/scope-mapping/spec.md` | Config-based ADO project / GitHub org to Snyk org mapping and Snyk API integration resolution. |
| sync-worker | `openspec/specs/sync-worker/spec.md` | Queue-driven worker that normalizes provider events, validates state, routes repo lifecycle events by source, enforces idempotency, and handles retries and dead-lettering. |

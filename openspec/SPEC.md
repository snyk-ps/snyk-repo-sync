# OpenSpec Capabilities

Canonical specifications for this project. Each capability has a dedicated spec under `openspec/specs/`.

| Capability | Path | Description |
| --- | --- | --- |
| ado-provisioning | `openspec/specs/ado-provisioning/spec.md` | Provision ADO audit stream for all Git repository lifecycle events (operator guide in INGESTION.md). |
| event-ingestion | `openspec/specs/event-ingestion/spec.md` | Deliver ADO audit stream and GitHub webhook events to a single Service Bus queue via customer-owned ingress; raw payloads only, no lifecycle normalization. |
| github-provisioning | `openspec/specs/github-provisioning/spec.md` | Provision GitHub organization webhooks so repository lifecycle events reach the webhook ingress endpoint. |
| github-webhook-ingestion | `openspec/specs/github-webhook-ingestion/spec.md` | Receive GitHub organization repository webhooks on customer-owned ingress, validate authenticity, deduplicate deliveries, and publish raw payloads to the Service Bus queue. |
| ignored-repos | `openspec/specs/ignored-repos/spec.md` | Ignore-list and name-prefix regex policy with scheduled deactivation of matching Snyk targets. |
| observability | `openspec/specs/observability/spec.md` | Structured logging to Dynatrace and alerting on dead-letter queue and unrecoverable failures. |
| repo-lifecycle | `openspec/specs/repo-lifecycle/spec.md` | Event-to-action handlers for repository create, rename, default branch change, and delete across ADO and GitHub sources. |
| snyk-target-sync | `openspec/specs/snyk-target-sync/spec.md` | Snyk Import, target deactivation, project tagging, import-job polling, and rate-limit backoff for ADO and GitHub repository lifecycle sync. |
| sync-state | `openspec/specs/sync-state/spec.md` | Azure Table Storage schema and access patterns for scope metadata (ADO project or GitHub org) and per-repository sync state. |
| sync-worker | `openspec/specs/sync-worker/spec.md` | Queue-driven worker that normalizes provider events, validates state, routes repo lifecycle events by source, enforces idempotency, and handles retries and dead-lettering. |

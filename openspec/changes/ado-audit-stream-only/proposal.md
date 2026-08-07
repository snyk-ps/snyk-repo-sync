## Why

ADO repository lifecycle events (create, rename, delete, default branch change) will be detected exclusively via the organization audit stream. Service hooks added operational complexity (per-project subscriptions, dual queue message shapes, separate ingress paths) without covering default branch changes. A single audit-stream path simplifies provisioning, ingress, normalization, operator documentation, and architecture diagrams.

## What Changes

- **BREAKING:** Remove ADO service hook provisioning and ingestion; decommission per-project service hook subscriptions.
- Expand audit stream coverage to all four ADO Git repository lifecycle events (`Git.RepositoryCreated`, `Git.RepositoryRenamed`, `Git.RepositoryDeleted`, `Git.RepositoryDefaultBranchChanged`).
- Remove service hook references from specs, `README.md`, `INGESTION.md`, `CONFIGURATION.md`, and `openspec/SPEC.md`.
- Replace architecture diagram(s) in `INGESTION.md` with audit-only ADO ingress (GitHub webhook path unchanged).
- Document audit stream batch latency (~30 minutes) as an accepted operational characteristic.
- Replace ADO transport fixture and tests that use service-hook-shaped `rawPayload` with audit-record payloads.
- Update spec capability descriptions in `openspec/SPEC.md`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ado-provisioning`: Remove service hook pipeline requirement; audit stream is the sole ADO event source; operator-provisioned per INGESTION.md.
- `event-ingestion`: Remove ADO service hook ingress scenario; all ADO messages are audit records in transport envelopes.
- `sync-worker`: Remove ADO service hook normalization scenario; normalize all ADO events from audit `ActionId` values; remove PS ownership wording.
- `repo-lifecycle`: Explicitly tie ADO create, rename, and delete scenarios to audit stream.
- `github-webhook-ingestion`: Remove PS ownership wording for normalization ownership.

## Impact

- **Specs:** `ado-provisioning`, `event-ingestion`, `sync-worker`, `repo-lifecycle`, `openspec/SPEC.md`
- **Docs/diagrams:** `INGESTION.md` mermaid architecture diagram; latency note in Architecture and Troubleshooting
- **Tests/fixtures:** `data/fixtures/transport_envelope_ado.json`, `tests/worker/test_envelope.py`, `tests/worker/test_consumer.py`, `tests/integration/test_worker_service_bus.py`
- **`src/`:** No hook-specific logic exists; update test inline payloads only
- **Out of scope:** GitHub webhook path; Event Grid ingress handler implementation in this repo; worker normalization implementation (unless already in flight elsewhere)

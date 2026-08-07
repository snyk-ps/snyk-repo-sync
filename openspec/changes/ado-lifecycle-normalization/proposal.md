## Why

Slice 1 validates transport envelopes and completes messages without further processing. Before sync state or Snyk actions land, the worker needs a stable, provider-neutral lifecycle event model that maps ADO audit records into the four repo lifecycle actions defined in `repo-lifecycle`. Real audit payloads confirm org scope (`ScopeId`, `ScopeDisplayName`), project, repository, and branch fields that downstream Snyk mapping and ADO REST enrichment will need.

GitHub webhook normalization will use the same model in a follow-up change. This change settles the normalized structure and implements ADO mapping only.

## What Changes

- Define the normalized lifecycle event schema: core fields, nested `ado` scope (org + project), `repository`, and event-specific `payload` (including branch fields).
- Document ADO audit → normalized field mapping for all four supported `ActionId` values, validated against real Event Grid audit records.
- Implement ADO normalization in the worker after envelope validation (slice 2).
- Replace slice-1 “validate and complete” behavior with slice-2 “validate → normalize (ADO) → log → complete”.
- Add ADO audit fixtures (one per lifecycle action) and unit tests for normalization.
- Update operator/dev docs (`CONFIGURATION.md`, `README.md`, `INGESTION.md`) to describe the normalized model and current slice boundary (normalization only, no sync).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-worker`: Expand normalization requirement with concrete schema (org, project, repo, branch), ADO audit field mapping for four `ActionId` values, slice-2 ADO normalization behavior; remove slice-1 “complete without normalization”; defer GitHub normalization implementation while retaining the provider-neutral model.

## Impact

- **Code:** `src/worker/normalize.py` (or similar), handler wiring, tests under `tests/worker/`.
- **Fixtures:** Update `data/fixtures/transport_envelope_ado.json` with org scope fields; add fixtures for create, rename, and delete audit actions.
- **Docs:** `CONFIGURATION.md`, `README.md`, `INGESTION.md` (audit fields used downstream).
- **Specs:** `openspec/changes/ado-lifecycle-normalization/specs/sync-worker/spec.md` delta only.
- **Out of scope:** GitHub mapper implementation, Table Storage, Snyk import/deactivate, ignore policy, unknown-scope DLQ alerts.

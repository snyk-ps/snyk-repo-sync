## Why

GitHub org repository webhooks reach the shared queue as raw JSON, but the worker still completes GitHub messages without normalization or Snyk lifecycle actions. ADO normalization and lifecycle sync are implemented; canonical specs already describe GitHub outcomes once normalization exists. Operators also receive GitHubHooks parsed repository events (Kafka topic `ENVLOG_GitHub_Repository_Event`) that must be supported alongside raw webhooks. The normalized event model still requires a mandatory ADO scope object, which blocks a GitHub normalizer and downstream lifecycle code that assumes `event.ado`.

## What Changes

- Extend `NormalizedEvent` with optional `GitHubScope` and source-discriminated provider scope (`ado` for ADO, `github` for GitHub); add provider-neutral scope lookup helpers.
- Implement GitHub normalization for **two message shapes**: raw GitHub webhook JSON and GitHubHooks **parsed contract** (discriminated by top-level `deliveryId`).
- Map four webhook actions (`created`, `renamed`, `deleted`, `edited`) to lifecycle `eventType` values; treat `edited` as default-branch change only when `changes.default_branch.from` is present.
- Wire the worker handler to normalize GitHub messages, resolve scope by org login (`repository.owner.login`), and run the same lifecycle path as ADO for mapped orgs.
- GitHub sync-state partition and `scopeId` use **org login** (not numeric org id), aligned with scope mapping and the parsed contract.
- GitHub target lookup and import use the mapped GitHub integration `source_types`; single-target assumption for default-branch re-import (no multi-branch SCM).
- Rename previous name: `changes.repository.name.from` when present, else sync-state `repoName` (same `repository.id`); if still unknown, import under new name and log (no DLQ).
- Remove slice-5 GitHub pass-through (complete without normalization).
- Fixtures and unit tests for both shapes and all four actions; update ingestion docs.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `event-ingestion`: Allow GitHub queue bodies as raw webhook JSON or GitHubHooks parsed repository event JSON.
- `sync-worker`: Dual-shape GitHub parsing and normalization; remove GitHub deferral; GitHub lifecycle for mapped orgs.
- `sync-state`: GitHub partition key uses org login as `scopeId`.
- `repo-lifecycle`: GitHub import branch from webhook/repo projection (no ADO REST); GitHub default-branch and rename resolution rules.
- `snyk-target-sync`: GitHub target REST lookup scoped to mapped GitHub integration type; GitHub import source type from scope resolution.

## Impact

- **Code:** `src/worker/normalize.py`, `message.py`, `handler.py`, `lifecycle.py`, `target_resolve.py`, `import_branch.py`, `snyk/client.py`, deferred-message rehydration, tests under `tests/worker/`.
- **Fixtures:** `data/fixtures/github_parsed_*.json`, extend raw GitHub fixtures for rename/edited/deleted.
- **Docs:** `INGESTION.md`, `CONFIGURATION.md` (GitHub message shapes and field mapping).
- **Out of scope:** Project tagging, GitHub REST enrichment client, Kafka consumer in this repo (body shape only), description-based rename parsing.

## Non-goals

- Supporting non-`repository` GitHub webhook types or user-owned repos (`owner.type != Organization`) beyond completing without sync.
- Multi-branch / custom default-branch SCM in Snyk for one repository.
- Reintroducing the transport envelope (`source`, `ingressId`, `rawPayload`).

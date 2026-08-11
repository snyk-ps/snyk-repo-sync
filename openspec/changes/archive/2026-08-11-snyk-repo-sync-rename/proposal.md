## Why

Production Container Apps crash on startup with `NameError: name 'ScopeMappingSettings' is not defined` in `src/config/scope_mapping.py` when running Python 3.12 (Docker image). The bug is masked locally on Python 3.14 due to deferred annotation evaluation and must be fixed by adding `from __future__ import annotations`.

The GitHub repository has already been renamed to **snyk-repo-sync**. Remaining work aligns the codebase and docs with that rename: product display name **Snyk Repo Sync**, Python package name, container image `ghcr.io/snyk-ps/snyk-repo-sync:<version>`, and doc links to the new repo URL.

README structure currently buries production deployment below local install steps. Operators deploying to Azure Container Apps should see the deployment runbook and canonical GHCR image reference first; local development belongs near the bottom.

## What Changes

- **Bug fix:** Add `from __future__ import annotations` to `src/config/scope_mapping.py` so the worker imports cleanly on Python 3.12.
- **Rebrand:** Rename the application display name from **Snyk Azure Repo Sync** to **Snyk Repo Sync** across user-facing docs and metadata.
- **Package / image naming:** Rename Python project in `pyproject.toml` to `snyk-repo-sync`; update `uv.lock`. Align release workflow and docs with **`ghcr.io/snyk-ps/snyk-repo-sync:<tag>`** (matches renamed GitHub repo).
- **README restructure:** Move **Deployment** section near the top (after intro + TOC). Move **local development / installation** to the bottom. Remove duplicate production pointers from the old install block.
- **Deployment docs:** Replace generic `ghcr.io/<owner>/<repository>:<tag>` with **`ghcr.io/snyk-ps/snyk-repo-sync:<version>`** in README Deployment section and cross-links in CONTRIBUTING.md.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `scope-mapping`: Scope mapping config module MUST import successfully on Python 3.12 (production container runtime).
- `sync-worker`: Operator deployment documentation MUST reference the canonical GHCR image `ghcr.io/snyk-ps/snyk-repo-sync:<version>` and place deployment guidance before local development instructions in README.md.

## Impact

- **Code:** `src/config/scope_mapping.py` (add `from __future__ import annotations`).
- **Metadata:** `pyproject.toml`, `uv.lock`.
- **CI:** `.github/workflows/release.yml` (explicit GHCR image name).
- **Docs:** `README.md` (reorder + rebrand + GHCR URL), `CONTRIBUTING.md`, `data/DESIGN.md`.
- **Breaking:** Image pull URL changes for operators using a locally built tag `snyk-azure-repo-sync`. Document migration note in README Deployment. No config or API breaking changes.

## Non-goals

- Adding a full CI test matrix on Python 3.12 (optional follow-up).
- Functional changes to scope mapping, worker behavior, or ingress.
- Bicep/Terraform or Azure resource renames in customer subscriptions.

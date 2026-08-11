## Context

- **Production runtime:** `python:3.12-slim-bookworm` (Dockerfile final stage).
- **Local dev:** `uv run` may use Python 3.14+, which implements PEP 649 lazy annotations and masks forward-reference bugs in class bodies.
- **Failure site:** `ScopeMappingSettings.empty()` return annotation `-> ScopeMappingSettings` is evaluated while the class is still being defined on Python 3.12.
- **Fix:** Not yet applied — add `from __future__ import annotations` as the first line of `scope_mapping.py`.
- **Project convention:** Most modules under `src/` use `from __future__ import annotations`; `scope_mapping.py` is missing it.
- **GitHub repo:** Already renamed to `snyk-ps/snyk-repo-sync` on GitHub; local clone and docs may still reference the old name.
- **Release workflow:** `.github/workflows/release.yml` may still use `ghcr.io/${{ github.repository }}:<tag>` — after repo rename this resolves to `ghcr.io/snyk-ps/snyk-repo-sync:<tag>`, but docs and any remaining hardcoded old names must be updated.

## Goals / Non-Goals

**Goals:**

- Worker starts successfully in Azure Container Apps on the current Docker image (Python 3.12).
- Consistent product naming: **Snyk Repo Sync** / **`snyk-repo-sync`** image.
- README optimized for operators: deploy first, develop locally second.
- Canonical GHCR reference in Deployment section.

**Non-Goals:**

- Python version pin file (`.python-version`) unless team wants it later.
- Functional changes to scope mapping, worker behavior, or ingress.

## Decisions

### Fix: `from __future__ import annotations` in `scope_mapping.py`

Add `from __future__ import annotations` as the **first line** of `src/config/scope_mapping.py`.

| Option | Verdict |
|--------|---------|
| `from __future__ import annotations` | **Chosen** — matches `ado_settings.py` and rest of codebase |
| Quoted return type `"ScopeMappingSettings"` | Works but inconsistent |
| `typing.Self` | Valid for `empty()` only; doesn't fix module-wide consistency |

**Alternative rejected:** Bump Dockerfile to Python 3.14 — production should track stable LTS; fix the code instead.

### Rebrand scope

| Artifact | Old | New |
|----------|-----|-----|
| Display name | Snyk Azure Repo Sync | **Snyk Repo Sync** |
| Python project (`pyproject.toml`) | `snyk-azure-repo-sync` | `snyk-repo-sync` |
| Local Docker tag (docs) | `snyk-azure-repo-sync` | `snyk-repo-sync` |
| GHCR image | `ghcr.io/snyk-ps/snyk-azure-repo-sync:<tag>` (implicit) | **`ghcr.io/snyk-ps/snyk-repo-sync:<tag>`** (explicit) |

Update README title, intro paragraph, docker examples, CONTRIBUTING.md references, and `data/DESIGN.md` title and GitHub links to `github.com/snyk-ps/snyk-repo-sync`.

### Release workflow image name

Confirm `release.yml` publishes to `ghcr.io/snyk-ps/snyk-repo-sync:<tag>`. With the repo renamed on GitHub, `ghcr.io/${{ github.repository }}:<tag>` already resolves correctly; update any hardcoded old repo/image references in docs. Optionally keep an explicit image name in the workflow for clarity.

Do **not** rename Azure resource examples already using `snyk-repo-sync-worker` (already correct).

### README structure

1. Title + one-paragraph intro (multi-provider: ADO + GitHub)
2. Table of contents
3. **Deployment** (full runbook — moved up)
4. Configuration
5. Usage
6. Features
7. Testing
8. Troubleshooting
9. **Local development** (renamed from "Installation and setup"; dev install, `uv sync`, local Docker — moved down)
10. More documentation

Remove the **Deployment / production installation** numbered list from the old install section; replace with a single link to **Deployment** at the top. Keep **INGESTION.md** prerequisite callout in Deployment intro.

### GHCR reference in Deployment

Use explicit form throughout Deployment (minimum requirements, portal walkthrough step C, troubleshooting):

```text
ghcr.io/snyk-ps/snyk-repo-sync:<version>
```

Example: `ghcr.io/snyk-ps/snyk-repo-sync:v0.1.0`. Note that `<version>` matches the git release tag. Link CONTRIBUTING.md for auth when pulling private packages.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Operators pinned to old GHCR path | Note in README: image renamed; update Container App image reference |
| Local Python 3.14 still hides future 3.12-only bugs | Optional follow-up: CI job running tests in Docker (Python 3.12) |
| `uv.lock` churn from package rename | Run `uv lock` after `pyproject.toml` name change |
| GitHub repo URL stale in docs | Update `data/DESIGN.md` and any hardcoded `snyk-azure-repo-sync` links to `snyk-ps/snyk-repo-sync` |

## Migration Plan

1. Merge this change (import fix, rebrand, docs, release workflow alignment).
2. Tag a release (e.g. `v0.1.0`) so `ghcr.io/snyk-ps/snyk-repo-sync:v0.1.0` is published.
3. Operators update Container App image reference from any local/old tag to the new GHCR path.

**Rollback:** Revert to previous image tag; no config changes required.

## Open Questions

_None._

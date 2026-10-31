## Why

Importing the new default branch deactivates the previous branch's projects before ignore migration runs. The v1 ignores API still returns those ignores, but the worker skips every deactivated project, so the copy never starts and the migration is logged as skipped.

## What Changes

- On default branch change, read v1 project ignores from projects whose `target_reference` is the previous branch even when those projects are already deactivated.
- Keep destination matching limited to active projects on the new branch.
- Leave rename and parsed GitHub updated copies unchanged: those sources stay limited to projects that are not deactivated.
- Document that a default-branch source is still read after Snyk has deactivated the previous branch.

## Capabilities

### New Capabilities

### Modified Capabilities

- `snyk-project-ignore-migration`: Default-branch source projects are eligible for the v1 ignore read and for project matching when they are deactivated. Destination projects, and sources for rename and GitHub updated, remain active-only.
- `repo-lifecycle`: A default-branch change still copies v1 ignores from the previous `target_reference` when that import has already deactivated those projects.

## Impact

- **Code:** Source selection and project matching in `src/worker/ignore_migration.py` and `src/worker/project_match.py`, and the default-branch source filter in `src/worker/lifecycle.py`.
- **APIs:** The existing `GET /v1/org/{orgId}/project/{projectId}/ignores` call is made for deactivated previous-branch projects. No new endpoint.
- **Docs:** `CONFIGURATION.md` default-branch ignore copy describes deactivated previous-branch projects as a valid source.

## Context

Snyk Open Source scanned `/Users/torsten-snyk/projects/snyk-repo-sync` against `uv.lock` on 2026-10-27 with `/Users/torsten-snyk/projects/snyk-repo-sync/.venv/bin/python3` (Python 3.12.13) and `severity_threshold=high`. The lockfile requires Python `>=3.12`. The scan reported 13 high or critical findings, all transitive.

| Package | Locked | Findings | Minimum fixed version | Python support of the fix | Path |
| --- | --- | --- | --- | --- | --- |
| `pyjwt` | 2.13.0 | 7 critical, 3 high | 2.15.0 | 2.15.0 and 2.15.1 require `>=3.9` | `azure-identity` 1.25.3 → `msal` 1.37.0 → `pyjwt` |
| `urllib3` | 2.7.0 | 2 high | 2.8.0 | 2.8.0 requires `>=3.10` | `azure-data-tables` 12.7.0 → `azure-core` 1.41.0 → `requests` 2.34.2 → `urllib3` |
| `certifi` | 2026.7.22 | 1 critical | 2026.10.19 | 2026.10.19 and 2026.10.23 require `>=3.7` | `azure-data-tables` 12.7.0 → `azure-core` 1.41.0 → `requests` 2.34.2 → `certifi` |

`pyjwt` 2.14.0 clears 9 of the 10 PyJWT findings. `SNYK-PYTHON-PYJWT-20245319` (CVE-2026-102275, high) is fixed only in 2.15.0, so the floor is 2.15.0. The other floors are `urllib3` 2.8.0 and `certifi` 2026.10.19.

Parent ranges already allow those floors:

- `msal` 1.37.0 depends on `PyJWT[crypto]>=1.0.0,<3` and itself requires Python `>=3.9`.
- `requests` 2.34.2 depends on `urllib3>=1.26,<3` and `certifi>=2023.5.7`, and requires Python `>=3.10`.

`requests` is pulled by `azure-core` and `msal` only. No direct Azure package pins these three transitives to the vulnerable versions.

## Goals / Non-Goals

**Goals:**

- Resolve `pyjwt>=2.15.0`, `urllib3>=2.8.0`, and `certifi>=2026.10.19` in `uv.lock`.
- Keep every selected release compatible with Python 3.12.
- Leave the four direct Azure packages on their current lower bounds.
- Confirm the new lockfile has no high or critical Snyk Open Source findings and that `uv sync --locked` plus the unit tests pass on Python 3.12.

**Non-Goals:**

- Upgrading `azure-data-tables`, `azure-identity`, `azure-servicebus`, or `azure-storage-queue` for this finding set.
- Moving packages that are not required to reach the three fixed versions.
- Raising `requires-python` above 3.12, or selecting a release that drops 3.12.
- Changing worker behavior.

## Decisions

### Constrain the three transitive packages

Add these entries to `[tool.uv] constraint-dependencies`:

```toml
[tool.uv]
constraint-dependencies = [
    "pyjwt>=2.15.0",
    "urllib3>=2.8.0",
    "certifi>=2026.10.19",
]
```

Do not add them to `[project] dependencies`. Then regenerate the lock with the project Python 3.12 environment (`uv lock`).

Current releases uv can select, all of which include Python 3.12, are `pyjwt` 2.15.1, `urllib3` 2.8.0, and `certifi` 2026.10.23. The constraints are lower bounds, so a newer 3.12-compatible release is acceptable. Reject a resolution whose `requires-python` does not include 3.12, and add an upper bound only if a newer release drops 3.12.

| Option | Verdict |
| --- | --- |
| `constraint-dependencies` at the scanned minimum fixes | **Chosen** — parent ranges already allow the fixes, and the fixes support Python 3.12 |
| Bump direct Azure packages to latest | Rejected — the scan does not require a new direct Azure release |
| Stop at `pyjwt` 2.14.0 | Rejected — CVE-2026-102275 remains until 2.15.0 |
| Add the three packages as direct application dependencies | Rejected — the worker does not import them |

### Keep the project on Python 3.12

`requires-python` stays `>=3.12`. Run `uv lock` and `uv sync --locked` with the existing 3.12 interpreter. `uv sync` fails if a selected distribution excludes 3.12, which is the compatibility check for this change.

### Verify with a second scan

After the lockfile changes, run Snyk Open Source again at high severity with the same Python 3.12 interpreter. The Azure tree must report zero high and critical findings. Run `uv run pytest -m "not integration"`. Update a test only when an upgraded library changes an asserted call or response.

## Risks / Trade-offs

- [A newer `pyjwt`, `urllib3`, or `certifi` release drops Python 3.12 before implementation] → Keep the lower bounds and add an upper bound below the first release that excludes 3.12. Confirm with `uv sync` on Python 3.12.
- [`uv lock` moves packages other than the three targets] → Keep only the changes required to satisfy the constraints.
- [The new resolution introduces another high or critical finding] → Constrain that package as well, still requiring Python 3.12, and scan again.
- [An SDK behavior change breaks a unit test] → Adjust the assertion only. Do not relax the version floors.

## Migration Plan

No operator config, schema, or queue migration. The next image build installs the updated lockfile. Rollback is reverting `pyproject.toml` and `uv.lock`.

## Open Questions

_None._ The upgrade floors come from the 2026-10-27 scan, and each minimum fix supports Python 3.12.

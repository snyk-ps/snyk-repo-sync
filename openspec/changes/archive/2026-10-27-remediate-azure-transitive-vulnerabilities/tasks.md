## 1. Constraints

- [x] 1.1 Add `[tool.uv] constraint-dependencies` for `pyjwt>=2.15.0`, `urllib3>=2.8.0`, and `certifi>=2026.10.19` without adding those packages to `[project] dependencies`
- [x] 1.2 Leave the direct Azure lower bounds unchanged: `azure-data-tables>=12.7.0`, `azure-identity>=1.25.3`, `azure-servicebus>=7.12.0`, and `azure-storage-queue>=12.18.0`

## 2. Lockfile

- [x] 2.1 Regenerate `uv.lock` with the project Python 3.12 interpreter
- [x] 2.2 Confirm the resolution is at least `pyjwt` 2.15.0, `urllib3` 2.8.0, and `certifi` 2026.10.19, and that each selected release includes Python 3.12
- [x] 2.3 If a selected release excludes Python 3.12, cap that constraint below the first incompatible release and lock again (not needed: `uv lock` resolved within `requires-python = ">=3.12"` without conflict, selecting `pyjwt` 2.15.1, `urllib3` 2.8.0, `certifi` 2026.10.23)
- [x] 2.4 Review the lockfile diff and drop upgrades that are not required to satisfy the three constraints (diff touches only `certifi`, `pyjwt`, `urllib3`, plus the new `[manifest] constraints` block)

## 3. Verification

- [x] 3.1 Run `uv sync --locked` and `uv run pytest -m "not integration"` on Python 3.12, updating a test only when an upgraded library changes an asserted call or response (`uv sync --locked` succeeded; 244 passed, 4 deselected, no test changes required)
- [x] 3.2 Re-scan `uv.lock` with Snyk Open Source at high severity using the Python 3.12 interpreter and confirm no high or critical Azure-tree findings remain (2026-10-27 re-scan: `issueCount: 0`)
- [x] 3.3 Run Snyk Code and fix any high finding introduced by a call-site change (no call sites changed; Snyk Code scan reports `issueCount: 0` at high severity)

## 4. Archive

- [x] 4.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/remediate-azure-transitive-vulnerabilities/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive remediate-azure-transitive-vulnerabilities` to fold deltas into canonical specs

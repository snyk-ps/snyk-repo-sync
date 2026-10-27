## 1. Constraints

- [ ] 1.1 Add `[tool.uv] constraint-dependencies` for `pyjwt>=2.15.0`, `urllib3>=2.8.0`, and `certifi>=2026.10.19` without adding those packages to `[project] dependencies`
- [ ] 1.2 Leave the direct Azure lower bounds unchanged: `azure-data-tables>=12.7.0`, `azure-identity>=1.25.3`, `azure-servicebus>=7.12.0`, and `azure-storage-queue>=12.18.0`

## 2. Lockfile

- [ ] 2.1 Regenerate `uv.lock` with the project Python 3.12 interpreter
- [ ] 2.2 Confirm the resolution is at least `pyjwt` 2.15.0, `urllib3` 2.8.0, and `certifi` 2026.10.19, and that each selected release includes Python 3.12
- [ ] 2.3 If a selected release excludes Python 3.12, cap that constraint below the first incompatible release and lock again
- [ ] 2.4 Review the lockfile diff and drop upgrades that are not required to satisfy the three constraints

## 3. Verification

- [ ] 3.1 Run `uv sync --locked` and `uv run pytest -m "not integration"` on Python 3.12, updating a test only when an upgraded library changes an asserted call or response
- [ ] 3.2 Re-scan `uv.lock` with Snyk Open Source at high severity using the Python 3.12 interpreter and confirm no high or critical Azure-tree findings remain
- [ ] 3.3 Run Snyk Code and fix any high finding introduced by a call-site change

## 4. Archive

- [ ] 4.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/remediate-azure-transitive-vulnerabilities/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive remediate-azure-transitive-vulnerabilities` to fold deltas into canonical specs

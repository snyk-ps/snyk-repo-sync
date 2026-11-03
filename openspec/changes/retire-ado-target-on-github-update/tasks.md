## 1. Config

- [ ] 1.1 Parse `snyk.targetRemoval.onUpdate` as `none`, `deactivate`, or `delete`, default `none`, in `src/config/snyk_settings.py`. Keep the other removal keys on `deactivate` or `delete`, default `deactivate`. An invalid `onUpdate` value fails startup.
- [ ] 1.2 Unit-test the default, both retirement modes, and an invalid value in `tests/config/test_snyk_settings.py`.

## 2. Retirement

- [ ] 2.1 Teach `retire_migration_source` to retire kind `updated` with the same whole-target path as rename when the mode is `deactivate` or `delete`. `none` and a blank target id do not call Snyk. HTTP 404 stays already gone.
- [ ] 2.2 After the updated ignore copy or skip, resolve the Azure DevOps target with `resolve_updated_source_target_id` and retire that id when `onUpdate` is `deactivate` or `delete`. A missing target skips retirement. A copy failure does not retire. A retirement failure reschedules `ignore_migration` and does not start another import. Do not retire the GitHub target, and do not leave the Azure DevOps target id on the GitHub row.
- [ ] 2.3 Unit-test copy-then-delete, skip-then-deactivate, `none`, a missing target, copy failure blocking retirement, and retirement retry.

## 3. Documentation

- [ ] 3.1 Update `CONFIGURATION.md` settings, removal semantics, the project-ignore section, and the lifecycle table for `onUpdate`. Update `INGESTION.md` so a parsed GitHub updated import retires the Azure DevOps target only per that setting. Show `onUpdate: none` in `data/config.yaml.example`.

## 4. Archive

- [ ] 4.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/retire-ado-target-on-github-update/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive retire-ado-target-on-github-update` (or project equivalent) to fold deltas into canonical specs.

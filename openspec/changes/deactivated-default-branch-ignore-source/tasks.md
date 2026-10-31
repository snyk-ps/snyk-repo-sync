## 1. Default-branch source selection

- [ ] 1.1 Include deactivated projects whose `target_reference` is the previous branch in the default-branch source list. Keep the destination list limited to projects that are not deactivated. Unit-test both lists.
- [ ] 1.2 Read v1 project ignores for a deactivated previous-branch source and copy them onto the active new-branch project. A deactivated rename source still produces no ignores request. Unit-test both.

## 2. Project matching

- [ ] 2.1 Match a deactivated source project to an active destination by `type` and `target_file`. Do not match a deactivated destination. Unit-test the default-branch success and the deactivated-destination failure.

## 3. Documentation

- [ ] 3.1 Update `CONFIGURATION.md` so the default-branch ignore copy states that previous-branch projects are read even when they are already deactivated, and that destination projects are not deactivated.

## 4. Archive

- [ ] 4.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/deactivated-default-branch-ignore-source/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive deactivated-default-branch-ignore-source` (or project equivalent) to fold deltas into canonical specs.

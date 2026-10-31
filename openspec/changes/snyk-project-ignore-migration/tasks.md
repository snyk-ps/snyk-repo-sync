## 1. Sync state

- [ ] 1.1 Add `ignoreMigrationKind`, `ignoreMigrationStatus`, `ignoreSourceOrgId`, `ignoreSourceTargetId`, and `ignoreSourceTargetReference` to the repository entity, including round-trip tests.
- [ ] 1.2 Clear those five properties only after the migration attempt finishes, and only after source retirement when the event requires it.

## 2. Snyk client

- [ ] 2.1 List projects for a target with `type`, `target_file`, `target_reference`, and deactivated status, with unit tests.
- [ ] 2.2 Read and create v1 project ignores (`GET` and `POST`), skipping an issue id and path already present on the destination, with unit tests.
- [ ] 2.3 Delete one project via `DELETE /rest/orgs/{org_id}/projects/{project_id}` for default-branch `delete` mode, with a unit test.

## 3. Normalized updated marker

- [ ] 3.1 Record on the normalized event that the body was a parsed updated import, while keeping `eventType` as `repo.created`, with a normalizer test for `github_parsed_updated.json`.
- [ ] 3.2 Treat a parsed updated body as not desired-state current when the stored `snykOrgId` or `snykIntegrationType` is non-empty and differs from the resolution. A blank stored org must not force a new import.

## 4. Snapshot and follow-up

- [ ] 4.1 Before import overwrites `snykTargetId` or `defaultBranch`, persist the migration kind and any known source target for rename, default branch change, and parsed updated.
- [ ] 4.2 Add `syncPhase: ignore_migration`. When an import job succeeds and a kind is set, schedule that phase and complete `import_poll`.
- [ ] 4.3 Retry `ignore_migration` up to 5 times, then dead-letter or poison-settle with reason `IgnoreMigrationFailed`. Do not retire the source while status is `pending`.

## 5. Copy

- [ ] 5.1 Match eligible projects on `type` and `target_file`, with the empty-file and same-branch tie rules, and fail the copy when a source project with ignores has no unique match. Unit-test the matcher.
- [ ] 5.2 Copy v1 ignore fields except `ignoredBy` and `created`. Do not call code-consistent ignore APIs.
- [ ] 5.3 On rename, copy from the previous target, then deactivate that target or delete it per `onRename`.
- [ ] 5.4 On default branch change, copy from the previous `target_reference` to the new one, then deactivate or delete only those previous-branch projects. Leave the target in place.
- [ ] 5.5 On parsed updated, look up the `azure-repos` target by the extracted `azure-devops-project` value, GitHub repository name, and import branch. Copy when it exists. Skip when it does not. Do not deactivate the ADO target or the previous GitHub target.

## 6. Logging and documentation

- [ ] 6.1 Log migration skipped, succeeded, and failed with `source`, scope id, repository id, `ignoreMigrationKind`, and outcome. Omit secrets and ignore reason text.
- [ ] 6.2 Update the `CONFIGURATION.md` lifecycle table and state schema for the new order, default-branch project retirement, the updated ADO copy, v1-only scope, and token ownership of new ignores.

## 7. Archive

- [ ] 7.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/snyk-project-ignore-migration/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive snyk-project-ignore-migration` (or project equivalent) to fold deltas into canonical specs.

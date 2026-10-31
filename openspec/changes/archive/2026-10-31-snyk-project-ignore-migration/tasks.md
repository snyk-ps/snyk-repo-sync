## 1. Configuration

- [x] 1.1 Parse `snyk.migrateIgnores` as a boolean, default `true` when the key or the `snyk` section is absent. A non-boolean value fails startup. Cover the default, `true`, `false`, and invalid value in unit tests.
- [x] 1.2 Show `migrateIgnores: true` in `data/config.yaml.example`.

## 2. Sync state

- [x] 2.1 Add `ignoreMigrationKind`, `ignoreMigrationStatus`, `ignoreSourceOrgId`, `ignoreSourceTargetId`, and `ignoreSourceTargetReference` to the repository entity, including round-trip tests.
- [x] 2.2 Clear those five properties only after the migration attempt finishes, and only after source retirement when the event requires it.

## 3. Snyk client

- [x] 3.1 List projects for a target with `type`, `target_file`, `target_reference`, and deactivated status, with unit tests.
- [x] 3.2 Read and create v1 project ignores (`GET` and `POST`), skipping an issue id and path already present on the destination, with unit tests.
- [x] 3.3 Delete one project via `DELETE /rest/orgs/{org_id}/projects/{project_id}` for default-branch `delete` mode, with a unit test.

## 4. Normalized updated marker

- [x] 4.1 Record on the normalized event that the body was a parsed updated import, while keeping `eventType` as `repo.created`, with a normalizer test for `github_parsed_updated.json`.
- [x] 4.2 Treat a parsed updated body as not desired-state current when the stored `snykOrgId` or `snykIntegrationType` is non-empty and differs from the resolution. A blank stored org must not force a new import.

## 5. Snapshot and follow-up

- [x] 5.1 Before import overwrites `snykTargetId` or `defaultBranch`, persist the migration kind and any known source target for rename, default branch change, and parsed updated.
- [x] 5.2 Add `syncPhase: ignore_migration`. When an import job succeeds and a kind is set, schedule that phase and complete `import_poll`.
- [x] 5.3 Retry `ignore_migration` up to 5 times, then dead-letter or poison-settle with reason `IgnoreMigrationFailed`. Do not retire the source while status is `pending`.

## 6. Copy

- [x] 6.1 Match eligible projects on `type` and `target_file`, with the empty-file and same-branch tie rules, and fail the copy when a source project with ignores has no unique match. Unit-test the matcher.
- [x] 6.2 Copy v1 ignore fields except `ignoredBy` and `created` when `snyk.migrateIgnores` is `true`. When it is `false`, skip the copy without calling the v1 ignore APIs, and still retire the source for rename and default branch change.
- [x] 6.3 Do not call code-consistent ignore APIs.
- [x] 6.4 On rename, copy from the previous target when migration is enabled, then deactivate that target or delete it per `onRename`.
- [x] 6.5 On default branch change, copy from the previous `target_reference` to the new one when migration is enabled, then deactivate or delete only those previous-branch projects. Leave the target in place.
- [x] 6.6 On parsed updated, look up the `azure-repos` target by the extracted `azure-devops-project` value, GitHub repository name, and import branch. Copy when it exists and migration is enabled. Skip when it does not, or when migration is disabled. Do not deactivate the ADO target or the previous GitHub target.

## 7. Logging and documentation

- [x] 7.1 Log migration skipped, succeeded, and failed with `source`, scope id, repository id, `ignoreMigrationKind`, and outcome. A configured skip is a skip. Omit secrets and ignore reason text.
- [x] 7.2 Update the `CONFIGURATION.md` lifecycle table and state schema for the new order, default-branch project retirement, the updated ADO copy, v1-only scope, token ownership of new ignores, and `snyk.migrateIgnores` defaulting to `true`.

## 8. Archive

- [ ] 8.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/snyk-project-ignore-migration/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive snyk-project-ignore-migration` (or project equivalent) to fold deltas into canonical specs.

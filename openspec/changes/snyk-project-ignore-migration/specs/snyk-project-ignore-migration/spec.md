## ADDED Requirements

### Requirement: v1 project ignore copy
After the destination import has completed, its Snyk target id is known, and `snyk.migrateIgnores` is `true`, the worker MUST copy v1 project ignores from the source projects onto the matching destination projects. The worker MUST read ignores with `GET /v1/org/{orgId}/project/{projectId}/ignores` and MUST add each missing ignore with `POST /v1/org/{orgId}/project/{projectId}/ignore/{issueId}`.

Each copied ignore MUST preserve issue id, ignore path, reason, reason type, `disregardIfFixable`, and expiry. The worker MUST NOT send `ignoredBy` or `created`.

The worker MUST read the destination project's ignores first and MUST NOT create a second ignore for an issue id and ignore path already present.

The worker MUST NOT call code-consistent ignore APIs.

#### Scenario: Ignore copied onto the matching project
- **WHEN** a source project has a v1 ignore and the destination has one matching project with no ignore for that issue id and path
- **THEN** the worker creates that ignore on the destination project through the v1 project-ignores API

#### Scenario: Retry does not duplicate an ignore
- **WHEN** the destination project already has an ignore for the same issue id and ignore path
- **THEN** the worker leaves that ignore in place and does not create another

#### Scenario: Code consistent ignores stay in place
- **WHEN** a migration runs for a repository that also has code consistent ignores
- **THEN** the worker does not read or write those ignores

### Requirement: Project match
The worker MUST match a source project to a destination project by Snyk project `type` and `target_file`. The worker MUST consider only projects that are not deactivated.

A source project with an empty `target_file` MUST match on `type` only when exactly one eligible source project and one eligible destination project have that type and an empty `target_file`.

A source project with no ignores MUST NOT require a match. A source project with one or more ignores and no unique match MUST fail the migration.

When several source projects share a `type` and `target_file`, and one of them has `target_reference` equal to the destination import branch, the worker MUST select that project. A remaining tie MUST fail the migration.

#### Scenario: Manifest match across branches
- **WHEN** the source and destination projects have the same `type` and `target_file` and different `target_reference` values
- **THEN** the worker treats them as a match

#### Scenario: Unmatched project with ignores fails the copy
- **WHEN** a source project has one or more ignores and no unique destination project of the same `type` and `target_file`
- **THEN** the migration fails and the worker does not retire the source

#### Scenario: Empty source project is skipped
- **WHEN** a source project has no v1 ignores
- **THEN** the worker does not require a destination match for that project

### Requirement: Configured skip
The worker MUST load `snyk.migrateIgnores` as a boolean. When the key is absent, the value MUST be `true`. A non-boolean value MUST fail startup.

When `snyk.migrateIgnores` is `true`, the worker MUST copy v1 project ignores. When it is `false`, the worker MUST skip the copy, MUST NOT call the v1 project-ignores API, and MUST still retire the source for rename and default branch change after the import completes.

#### Scenario: Default is to migrate
- **WHEN** operator config omits `snyk.migrateIgnores`
- **THEN** the worker copies v1 project ignores for rename, default branch change, and GitHub updated

#### Scenario: Disabled copy still retires the previous target
- **WHEN** `snyk.migrateIgnores` is `false` and a repo-renamed event finishes importing the new name
- **THEN** the worker does not call the v1 project-ignores API and removes the previous target per `snyk.targetRemoval.onRename`

#### Scenario: Invalid value fails startup
- **WHEN** `snyk.migrateIgnores` is a string
- **THEN** the worker exits at startup with a configuration error

### Requirement: Migration failure blocks retirement
A failed migration MUST be retried on follow-up phase `ignore_migration` up to the import retry budget of 5. The worker MUST NOT retire the source while `ignoreMigrationStatus` is `pending`. After the retry budget, the worker MUST dead-letter or poison-settle with reason `IgnoreMigrationFailed` and MUST leave the source projects active.

A missing source target, and a source whose eligible projects have no ignores, MUST be a successful skip.

#### Scenario: Copy failure leaves the source active
- **WHEN** the v1 ignore API fails during migration for a rename or default-branch change
- **THEN** the worker reschedules `ignore_migration` and does not deactivate or delete the source

#### Scenario: Nothing to copy still allows retirement
- **WHEN** a rename has a resolved previous target and that target's projects have no v1 ignores
- **THEN** the worker marks the migration skipped and retires the previous target per the configured removal mode

#### Scenario: Migration retry exhausted
- **WHEN** an `ignore_migration` follow-up reaches retry count 5
- **THEN** the message is dead-lettered or poison-settled with reason `IgnoreMigrationFailed` and the source projects remain active

### Requirement: Operator documentation for project ignore migration
`CONFIGURATION.md` MUST describe, for rename, default branch change, and GitHub updated: when v1 project ignores are copied, which projects are the source and destination, and when the source is retired. It MUST document `snyk.migrateIgnores`, including the default `true` and that `false` skips the copy. It MUST state that code consistent ignores are unchanged, that the new ignore is owned by the `SNYK_TOKEN` user, and that a GitHub updated import does not deactivate the Azure DevOps target. `data/config.yaml.example` MUST show `migrateIgnores: true`.

#### Scenario: Operator reads the lifecycle table
- **WHEN** an operator reads the lifecycle behavior in `CONFIGURATION.md` after this change
- **THEN** rename and default branch change show import, then v1 ignore copy, then source retirement, and updated shows the ADO copy without retirement

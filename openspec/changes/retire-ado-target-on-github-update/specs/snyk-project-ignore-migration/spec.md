## MODIFIED Requirements

### Requirement: Configured skip
The worker MUST load `snyk.migrateIgnores` as a boolean. When the key is absent, the value MUST be `true`. A non-boolean value MUST fail startup.

When `snyk.migrateIgnores` is `true`, the worker MUST copy v1 project ignores. When it is `false`, the worker MUST skip the copy, MUST NOT call the v1 project-ignores API, and MUST still retire the source for rename and default branch change after the import completes. For a parsed GitHub updated import, that skip MUST still retire the Azure DevOps target when `snyk.targetRemoval.onUpdate` is `deactivate` or `delete`, and MUST NOT retire it when `onUpdate` is `none`.

#### Scenario: Default is to migrate
- **WHEN** operator config omits `snyk.migrateIgnores`
- **THEN** the worker copies v1 project ignores for rename, default branch change, and GitHub updated

#### Scenario: Disabled copy still retires the previous target
- **WHEN** `snyk.migrateIgnores` is `false` and a repo-renamed event finishes importing the new name
- **THEN** the worker does not call the v1 project-ignores API and removes the previous target per `snyk.targetRemoval.onRename`

#### Scenario: Invalid value fails startup
- **WHEN** `snyk.migrateIgnores` is a string
- **THEN** the worker exits at startup with a configuration error

#### Scenario: Disabled copy still retires the ADO target
- **WHEN** `snyk.migrateIgnores` is `false`, `snyk.targetRemoval.onUpdate` is `delete`, and a parsed GitHub updated import finishes with a matching Azure DevOps target
- **THEN** the worker does not call the v1 project-ignores API and deletes that Azure DevOps target

### Requirement: Migration failure blocks retirement
A failed migration MUST be retried on follow-up phase `ignore_migration` up to the import retry budget of 5. The worker MUST NOT retire the source while `ignoreMigrationStatus` is `pending`. After the retry budget, the worker MUST dead-letter or poison-settle with reason `IgnoreMigrationFailed` and MUST leave the source projects active.

A missing source target, and a source whose eligible projects have no ignores, MUST be a successful skip. For a parsed GitHub updated import, a missing Azure DevOps target MUST skip retirement. A source whose eligible projects have no ignores MUST still allow retirement when `snyk.targetRemoval.onUpdate` is `deactivate` or `delete`.

#### Scenario: Copy failure leaves the source active
- **WHEN** the v1 ignore API fails during migration for a rename, default-branch change, or parsed GitHub updated import
- **THEN** the worker reschedules `ignore_migration` and does not deactivate or delete the source

#### Scenario: Nothing to copy still allows retirement
- **WHEN** a rename has a resolved previous target and that target's projects have no v1 ignores
- **THEN** the worker marks the migration skipped and retires the previous target per the configured removal mode

#### Scenario: Migration retry exhausted
- **WHEN** an `ignore_migration` follow-up reaches retry count 5
- **THEN** the message is dead-lettered or poison-settled with reason `IgnoreMigrationFailed` and the source projects remain active

#### Scenario: Nothing to copy still retires the ADO target
- **WHEN** `snyk.targetRemoval.onUpdate` is `deactivate` and the matching Azure DevOps target's eligible projects have no v1 ignores
- **THEN** the worker marks the migration skipped and deactivates every project on that Azure DevOps target

### Requirement: Operator documentation for project ignore migration
`CONFIGURATION.md` MUST describe, for rename, default branch change, and GitHub updated: when v1 project ignores are copied, which projects are the source and destination, and when the source is retired. It MUST document `snyk.migrateIgnores`, including the default `true` and that `false` skips the copy. It MUST document `snyk.targetRemoval.onUpdate` with values `deactivate`, `delete`, and `none`, and that the default `none` does not retire the Azure DevOps target. It MUST state that code consistent ignores are unchanged, that the new ignore is owned by the `SNYK_TOKEN` user, and that `deactivate` or `delete` retires the Azure DevOps target only after the copy succeeds or is skipped. It MUST state that a default-branch copy reads v1 ignores from the previous branch's projects even when those projects are already deactivated, and that the destination projects are projects that are not deactivated. `INGESTION.md` MUST state that a parsed GitHub updated import retires the Azure DevOps target only per `snyk.targetRemoval.onUpdate`, and that the default leaves that target in place. `data/config.yaml.example` MUST show `migrateIgnores: true` and `onUpdate: none`.

#### Scenario: Operator reads the lifecycle table
- **WHEN** an operator reads the lifecycle behavior in `CONFIGURATION.md` after this change
- **THEN** rename, default branch change, and GitHub updated show import, then v1 ignore copy, then source retirement, and updated retirement follows `targetRemoval.onUpdate` with default `none`

#### Scenario: Operator reads default-branch source eligibility
- **WHEN** an operator reads the project-ignore section in `CONFIGURATION.md`
- **THEN** it states that previous-branch projects are read even when they are already deactivated, and that destination projects are not deactivated

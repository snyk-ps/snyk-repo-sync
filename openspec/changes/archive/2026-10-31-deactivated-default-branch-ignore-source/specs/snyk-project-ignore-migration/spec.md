## MODIFIED Requirements

### Requirement: Project match
The worker MUST match a source project to a destination project by Snyk project `type` and `target_file`. The worker MUST consider a destination project only when that project is not deactivated.

For rename and parsed GitHub updated, the worker MUST consider a source project only when that project is not deactivated.

For default branch change, the worker MUST consider a source project whose `target_reference` is the previous branch whether or not that project is deactivated, and MUST read its v1 project ignores with `GET /v1/org/{orgId}/project/{projectId}/ignores`.

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

#### Scenario: Deactivated previous branch is still a source
- **WHEN** a default-branch source project is deactivated, its `target_reference` is the previous branch, and the v1 ignores API returns one or more ignores
- **THEN** the worker reads those ignores and matches the project to an active destination project of the same `type` and `target_file`

#### Scenario: Deactivated destination is not a match
- **WHEN** the only project on the new branch with the same `type` and `target_file` is deactivated
- **THEN** the worker does not copy ignores onto that project

#### Scenario: Rename still skips a deactivated source
- **WHEN** a rename source project is deactivated
- **THEN** the worker does not read v1 project ignores from that project

### Requirement: Operator documentation for project ignore migration
`CONFIGURATION.md` MUST describe, for rename, default branch change, and GitHub updated: when v1 project ignores are copied, which projects are the source and destination, and when the source is retired. It MUST document `snyk.migrateIgnores`, including the default `true` and that `false` skips the copy. It MUST state that code consistent ignores are unchanged, that the new ignore is owned by the `SNYK_TOKEN` user, and that a GitHub updated import does not deactivate the Azure DevOps target. It MUST state that a default-branch copy reads v1 ignores from the previous branch's projects even when those projects are already deactivated, and that the destination projects are projects that are not deactivated. `data/config.yaml.example` MUST show `migrateIgnores: true`.

#### Scenario: Operator reads the lifecycle table
- **WHEN** an operator reads the lifecycle behavior in `CONFIGURATION.md` after this change
- **THEN** rename and default branch change show import, then v1 ignore copy, then source retirement, and updated shows the ADO copy without retirement

#### Scenario: Operator reads default-branch source eligibility
- **WHEN** an operator reads the project-ignore section in `CONFIGURATION.md`
- **THEN** it states that previous-branch projects are read even when they are already deactivated, and that destination projects are not deactivated

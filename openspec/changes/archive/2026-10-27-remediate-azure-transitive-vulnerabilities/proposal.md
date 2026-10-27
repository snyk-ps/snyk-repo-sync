## Why

A Snyk Open Source scan of the committed `uv.lock` on 2026-10-27, using the project interpreter Python 3.12.13, reported 13 high or critical findings. All of them are transitive packages in the Azure dependency tree. The direct Azure packages do not need a version bump: their existing dependency ranges already allow the fixed releases, and those releases still support Python 3.12.

## What Changes

- Constrain the three vulnerable transitive packages in `[tool.uv] constraint-dependencies`, without adding them to `[project] dependencies`:
  - `pyjwt>=2.15.0` (locked 2.13.0; 10 findings, highest fix is 2.15.0)
  - `urllib3>=2.8.0` (locked 2.7.0; 2 high findings)
  - `certifi>=2026.10.19` (locked 2026.7.22; 1 critical finding)
- Leave the direct Azure bounds unchanged. `msal` 1.37.0 already allows `PyJWT[crypto]>=1.0.0,<3`, and `requests` 2.34.2 already allows `urllib3>=1.26,<3` and `certifi>=2023.5.7`.
- Regenerate `uv.lock` on Python 3.12. Current PyPI releases that satisfy the constraints and include 3.12 are `pyjwt` 2.15.1 (`requires-python >=3.9`), `urllib3` 2.8.0 (`>=3.10`), and `certifi` 2026.10.23 (`>=3.7`; 2026.10.19 is the minimum fix and also allows 3.12).
- Re-scan the new lockfile and keep the unit tests passing.

## Capabilities

### New Capabilities

_None._ The version floors live in `pyproject.toml` and `uv.lock`. The bar against high and critical dependency findings is the project guideline, not a new capability.

### Modified Capabilities

_None._ Existing capability requirements stay the same. Azure Table Storage, identity, Service Bus, and Storage Queue behavior is unchanged.

## Impact

- **Dependencies:** `pyproject.toml` and `uv.lock` only. Direct packages stay at `azure-data-tables>=12.7.0` (locked 12.7.0), `azure-identity>=1.25.3` (locked 1.25.3), `azure-servicebus>=7.12.0` (locked 7.14.3), and `azure-storage-queue>=12.18.0` (locked 12.18.0).
- **Vulnerable paths:**
  - `azure-identity` 1.25.3 → `msal` 1.37.0 → `pyjwt` 2.13.0
  - `azure-data-tables` 12.7.0 → `azure-core` 1.41.0 → `requests` 2.34.2 → `urllib3` 2.7.0
  - `azure-data-tables` 12.7.0 → `azure-core` 1.41.0 → `requests` 2.34.2 → `certifi` 2026.7.22
- **Python:** the project stays on `requires-python >=3.12`. The chosen fixes declare `requires-python` ranges that include 3.12.
- **Code:** no application changes expected. Tests that pin Azure client behavior must stay green.
- **Breaking:** none.

## Non-goals

- Bumping direct Azure packages when a transitive constraint already selects a fixed version.
- Remediating findings outside these three packages unless the new resolution introduces a new high or critical finding.
- Changing worker, ingress, or provisioning behavior.
- Selecting a release whose `requires-python` excludes 3.12.

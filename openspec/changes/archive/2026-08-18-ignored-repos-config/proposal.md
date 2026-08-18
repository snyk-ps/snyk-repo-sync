## Why

Operators need to exclude repositories from Snyk sync without relying on provider events alone. Some repos should never be imported; others may already exist in Snyk and must be cleaned up when added to policy. The existing `ignored-repos` spec sketches JSON-in-repo plus a prefix regex in `config.yaml`, but it is unimplemented and does not match how operators mount config in Azure (Files share alongside `config.yaml`).

## What Changes

- Add an operator ignore-policy file (YAML or JSON, UTF-8) co-located with `config.yaml` on the Azure Files mount (e.g. `/config/ignored-repos.yaml`).
- Add `ignoredRepos.path` to operator config pointing at that file (relative to the config file directory or absolute).
- Two ignore mechanisms in the policy file:
  1. **Explicit repos** — required `source` (`azure-repos` or `github`), `owner`, and `name`; optional extra fields for operator context (ignored by matching logic).
  2. **Pattern groups** — named groups (`id`) with `filterType` (`regex` | `prefix` | `suffix`) and a list of patterns matched against repository name.
- Worker short-circuit: ignored repos are not imported; ignore policy is evaluated immediately on every lifecycle event (create, rename, default branch change).
- Background reconciliation: reload policy on a configurable interval (default 15 minutes); remove active synced targets matching policy per `snyk.targetRemoval.onIgnore` (default `deactivate`).
- Add `snyk.targetRemoval.onIgnore` (`deactivate` | `delete`, default `deactivate`).
- Add examples: `data/ignored-repos.yaml` and `data/ignored-repos.json`.
- Update **CONFIGURATION.md**, **README.md**, **data/DESIGN.md**, and **data/config.yaml.example**.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ignored-repos`: Replace JSON-in-repo and config regex with mounted policy file (YAML/JSON), explicit + pattern matching, event-time enforcement, and background reconciliation.
- `sync-state`: Update ignore-policy persistence wording and behavior (policy file, not JSON-in-repo).
- `sync-worker`: Evaluate ignore policy before lifecycle actions; load policy from configured path; run reconciliation loop.
- `snyk-target-sync`: Add `targetRemoval.onIgnore` for ignored-repository target removal.
- `repo-lifecycle`: Immediate ignore evaluation on rename and default-branch change (including rename into ignore policy).

## Impact

- **Code:** new `src/config/ignored_repos.py` (parse/validate/match); worker lifecycle integration; background reconciliation in worker process; sync-state meta row for persisted policy; `snyk.targetRemoval.onIgnore` in settings parser.
- **Dependencies:** stdlib + existing `pyyaml` (JSON via stdlib).
- **Docs:** CONFIGURATION.md, README.md, data/DESIGN.md, data/config.yaml.example.
- **Breaking:** none if `ignoredRepos.path` is omitted — ignore enforcement remains off.

## Non-goals

- Per-entry `delete` override in the ignore file (removal mode is global via `snyk.targetRemoval.onIgnore` only).
- Ignoring by branch, path, or language.
- GitHub-specific ignore file hosted in GitHub (policy file lives with operator config).
- Migrating issue ignores when deactivating ignored targets.
- Additional `source` values beyond `azure-repos` and `github` in v1 (GitHub Enterprise Server variants use umbrella `github` for ignore matching).

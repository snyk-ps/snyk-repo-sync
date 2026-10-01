## 1. Normalized event schema

- [ ] 1.1 Add `GitHubScope` and make `ado` / `github` optional on `NormalizedEvent` with source invariant
- [ ] 1.2 Add `scope_lookup_key()` and `owner_name()` helpers in `normalize.py`
- [ ] 1.3 Update all test builders and fixtures that construct `NormalizedEvent`

## 2. GitHub adapters and normalizer

- [ ] 2.1 Implement shape detection (`deliveryId` ⇒ parsed contract)
- [ ] 2.2 Implement `adapt_github_raw_webhook()` and `adapt_github_parsed_contract()` to a canonical struct
- [ ] 2.3 Implement `normalize_github_repository_event()` with action mapping and `edited` branch-only rule
- [ ] 2.4 Reject or no-op non-Organization owners per spec
- [ ] 2.5 Add unit tests in `tests/worker/test_normalize_github.py` for raw and parsed fixtures

## 3. Queue parsing and handler

- [ ] 3.1 Set `QueueMessage.event_id` from `deliveryId` or documented SB property for raw webhooks
- [ ] 3.2 Remove GitHub defer path in `handler.py`; normalize and route to lifecycle
- [ ] 3.3 Extend `tests/worker/test_message.py` for parsed contract shape
- [ ] 3.4 Update `tests/worker/test_handler.py` for mapped GitHub lifecycle

## 4. Lifecycle and Snyk wiring

- [ ] 4.1 Replace `event.ado.project_name` usages with scope lookup helpers across lifecycle, target_resolve, import_branch, deferred messages
- [ ] 4.2 GitHub branch resolution in `import_branch.py` (no ADO REST for GitHub)
- [ ] 4.3 Pass GitHub `source_types` from scope resolution in `find_target_id` and `start_import`
- [ ] 4.4 Relax payload-only previous-default-branch guard for `source: github` in lifecycle
- [ ] 4.5 Implement GitHub rename previous-name fallback chain per spec

## 5. Fixtures and docs

- [ ] 5.1 Add `data/fixtures/github_parsed_{created,renamed,deleted,edited_branch,edited_description}.json`
- [ ] 5.2 Add raw GitHub fixtures for rename, deleted, edited where missing
- [ ] 5.3 Update `INGESTION.md` and `CONFIGURATION.md` with dual GitHub message shapes and field mapping

## 6. Archive

- [ ] 6.1 Merge `openspec/specs/` only when archiving: run `openspec archive github-lifecycle-normalization`; do not manually merge change deltas into canonical specs during implementation

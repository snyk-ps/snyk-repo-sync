## 1. Fixture

- [x] 1.1 Replace `data/fixtures/github_parsed_updated.json` with the top-level data object: `deliveryId`, `repository`, `oldPropertyValues`, `newPropertyValues`, and `sender`. Remove the CloudEvents wrapper fields, including `type`, `time`, and the wrapping `data` object. Keep `deliveryId` `b2c3d4e5-f6a7-8901-bcde-f12345678901`, `repository.updatedAt` `2026-09-02T12:00:00Z`, and `azure-devops-project` / `sample-project`.

## 2. Accept and normalize the data object

- [x] 2.1 Classify a GitHub body as parsed updated when `repository` is an object, `newPropertyValues` is an array, and `action` is not a non-empty string. Run that check before the parsed-contract `deliveryId` rule in `src/worker/message.py` and `src/worker/normalize.py`. The provider payload is the body. `event_id` is top-level `deliveryId`.
- [x] 2.2 Accept that body in `src/worker/http_ingress.py` so `POST /github-events` does not return 422. Keep ADO rejection and `action: created` rejection. Keep `renamed`, `edited`, and `deleted` acceptance.
- [x] 2.3 Normalize the body to `repo.created` from top-level `deliveryId` and top-level `repository`. Set `occurredAt` from `repository.updatedAt` (`2026-09-02T12:00:00Z` for the fixture).

## 3. Property path

- [x] 3.1 Use `collectionPath: newPropertyValues` for fixture-backed GitHub extraction and in `data/config.yaml.example`. On `github_parsed_updated.json`, that path yields `sample-project`. `collectionPath: data.newPropertyValues` yields no value and resolution continues with org login `sample-org`. Leave the generic dotted-path walker unchanged.
- [x] 3.2 If a gitignored local config sets GitHub `collectionPath` to `data.newPropertyValues`, change it to `newPropertyValues`. Do not commit that file.

## 4. Tests

- [x] 4.1 Update unit tests so the updated fixture parses as GitHub, normalizes to `repo.created` with `occurredAt` `2026-09-02T12:00:00Z`, returns 204 from `/github-events`, and resolves lookup key `sample-project` when `collectionPath` is `newPropertyValues`. Assert the `data.newPropertyValues` path misses on this fixture. Keep current outcomes for raw webhook, parsed lifecycle, and ADO fixtures.

## 5. Documentation

- [x] 5.1 Update `README.md`, `CONFIGURATION.md`, and `INGESTION.md` so the import body, detection rule, `eventId`, `occurredAt`, and GitHub `collectionPath` match the data object.

## 6. Archive

- [ ] 6.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/fix-github-updated-data-body/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive fix-github-updated-data-body` (or project equivalent) to fold deltas into canonical specs.

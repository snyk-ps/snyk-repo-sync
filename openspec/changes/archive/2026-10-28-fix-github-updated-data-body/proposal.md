## Why

`data/fixtures/github_parsed_updated.json` and the worker treat the GitHub import as a CloudEvents document (`type: ENVLOG.GitHub.custom_property_values.updated` with repository fields under `data`). The connector posts only that inner data object. The body has `repository` and `newPropertyValues` and no `action`, so `POST /github-events` returns 422 and the repository is not imported.

## What Changes

- Replace `data/fixtures/github_parsed_updated.json` with the data object the connector sends: top-level `deliveryId`, `repository`, `oldPropertyValues`, `newPropertyValues`, and `sender`. Remove the CloudEvents wrapper fields (`id`, `specversion`, `type`, `version`, `source`, `datacontenttype`, `time`, `iaspecversion`, `correlationid`, `env`, and the wrapping `data` object).
- Accept that body as the GitHub import on the Service Bus path and on `POST /github-events`. A successful import returns 204. Do not require CloudEvents `type` or a GitHub `action`.
- Recognize the import from the fields on that body, before the parsed-contract `deliveryId` rule: `repository` is an object and `newPropertyValues` is an array. The updated body also has `deliveryId` and no `action`, so a `deliveryId`-only rule classifies it as a parsed lifecycle message and then rejects it.
- Read `eventId` from top-level `deliveryId` and repository fields from top-level `repository`. `occurredAt` is `repository.updatedAt`. In the fixture that is `2026-09-02T12:00:00Z`. CloudEvents `time` (`2026-10-01T12:00:00Z`) is not on this body.
- The GitHub property extractor path for this body is `newPropertyValues`, not `data.newPropertyValues`. With `collectionPath: data.newPropertyValues` the path misses, `sample-project` is ignored, and scope lookup falls back to org login `sample-org`.
- Update `README.md` where it names this import. Update `CONFIGURATION.md`, `INGESTION.md`, and `data/config.yaml.example`, which describe the same wrapper and the `data.newPropertyValues` path.
- Keep current outcomes for raw webhook, parsed lifecycle, and ADO fixtures. The import still normalizes to `repo.created` and still does not deactivate an Azure DevOps Snyk target.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `event-ingestion`: The parsed updated queue and connector body is the data object in `data/fixtures/github_parsed_updated.json`, with `repository` and `newPropertyValues` at the top level.
- `github-events-http-ingress`: Accept that body on `POST /github-events` and return 204 after successful import processing. Do not return 422 for it.
- `sync-worker`: Classify and normalize the data object to `repo.created`. `eventId` is top-level `deliveryId`. `occurredAt` is `repository.updatedAt`.
- `scope-mapping`: The GitHub sample `collectionPath` for this body is `newPropertyValues`.

## Impact

- **Code:** GitHub message identification in `src/worker/message.py`, shape detection and normalization in `src/worker/normalize.py`, and the HTTP boundary in `src/worker/http_ingress.py`. Unit tests that load the updated fixture or assert `data.newPropertyValues` and envelope time.
- **Fixture:** `data/fixtures/github_parsed_updated.json`.
- **Configuration:** `data/config.yaml.example` GitHub `collectionPath` becomes `newPropertyValues`. A gitignored local config that still uses `data.newPropertyValues` misses `sample-project` on this body and falls back to org login `sample-org`.
- **Documentation:** `README.md`, `CONFIGURATION.md`, and `INGESTION.md`.
- **Dependencies:** None.

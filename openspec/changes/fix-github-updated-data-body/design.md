## Context

The GitHub import fixture and the worker treat `github_parsed_updated.json` as a CloudEvents document. Identification requires `type: ENVLOG.GitHub.custom_property_values.updated` and reads repository fields from `data`. `POST /github-events` returns 422 unless that wrapper is present and `data.repository` is an object, or the body has `action` of `renamed`, `edited`, or `deleted`.

The connector posts the inner object only: `deliveryId`, `repository`, `oldPropertyValues`, `newPropertyValues`, and `sender`. That object has no `action` and no CloudEvents `type`. Queue parsing rejects it as unrecognized, and the HTTP boundary returns 422.

Two fields move with that body:

- Property extraction is rooted at the received JSON. `collectionPath: data.newPropertyValues` does not find the array, so `sample-project` is ignored and scope lookup uses org login `sample-org`. The path that matches is `newPropertyValues`.
- CloudEvents `time` (`2026-10-01T12:00:00Z`) is not on the body. `occurredAt` comes from `repository.updatedAt` (`2026-09-02T12:00:00Z`). `repository.pushedAt` is not the event time.

`scopeId` and `github.orgLogin` stay the organization login. The extracted property value is only the Snyk org lookup key.

## Goals / Non-Goals

**Goals:**

- Make `data/fixtures/github_parsed_updated.json` the data object the connector sends.
- Accept that body on the queue and on `POST /github-events`, normalize it to `repo.created`, and return 204 after successful processing.
- Classify it from `repository` and `newPropertyValues` before the parsed-contract `deliveryId` rule.
- Set `eventId` from top-level `deliveryId` and `occurredAt` from `repository.updatedAt`.
- Document and exemplify GitHub `collectionPath: newPropertyValues` so the fixture resolves `sample-project`.
- Update `README.md`, `CONFIGURATION.md`, and `INGESTION.md` to the same contract.

**Non-Goals:**

- New capabilities.
- Changing raw webhook, parsed lifecycle, or ADO outcomes.
- Changing dotted-path extractor syntax. A configured path is still resolved from the received JSON root.
- Deactivating an Azure DevOps Snyk target when this import runs.
- Treating a CloudEvents wrapper as this import body.

## Decisions

### 1. The fixture is the data object

Replace `github_parsed_updated.json` with the object that is currently under `data`. Drop `id`, `specversion`, `type`, `version`, `source`, `datacontenttype`, `time`, `iaspecversion`, `correlationid`, `env`, and the wrapping `data` key.

`deliveryId` remains `b2c3d4e5-f6a7-8901-bcde-f12345678901`. `repository.updatedAt` remains `2026-09-02T12:00:00Z`. `newPropertyValues` still contains `azure-devops-project` / `sample-project`.

### 2. Recognition uses the fields on that body

Classify a GitHub body as parsed updated when all of the following hold:

- `repository` is an object
- `newPropertyValues` is an array
- `action` is not a non-empty string

Run that check before the parsed-contract rule (non-empty top-level `deliveryId`). The updated body has `deliveryId` and no `action`. A `deliveryId` check first selects the parsed lifecycle adapter, which requires `action` and then fails.

Apply the same predicate in:

- `src/worker/message.py`, so the body is a GitHub queue message and `event_id` is top-level `deliveryId`. The provider payload is the body itself.
- `detect_github_message_shape` in `src/worker/normalize.py`.
- `_validate_github_boundary` in `src/worker/http_ingress.py`, so the body proceeds to processing instead of returning 422. ADO detection stays first. `action: created` stays rejected on this endpoint. `renamed`, `edited`, and `deleted` stay accepted.

A non-empty `action` stays on the parsed-contract or raw-webhook path, so a lifecycle fixture that also carried `newPropertyValues` would keep its action mapping.

### 3. Normalization reads the top-level object

`adapt_github_parsed_updated` reads `deliveryId`, `repository`, owner, and `repository.updatedAt` from the body. It still maps the body to `action: created` and `eventType: repo.created`. It does not read a wrapper `time` or a nested `data` object.

For the fixture, `occurredAt` is `2026-09-02T12:00:00Z`.

### 4. The sample extractor path is `newPropertyValues`

The walker stays a dotted path from the received JSON root. Fixture-backed GitHub extraction, `data/config.yaml.example`, and the operator docs use `collectionPath: newPropertyValues` with the existing `matchField`, `matchValue`, and `valueField`.

`collectionPath: data.newPropertyValues` on this fixture yields no value. Resolution then uses org login `sample-org` when that name is mapped. No code path special-cases the string `data.newPropertyValues`.

### 5. Docs state this body

`README.md` names this import as the data object, not a CloudEvents `type`. `CONFIGURATION.md` and `INGESTION.md` use the same detection rule, top-level `deliveryId`, `repository.updatedAt`, and `collectionPath: newPropertyValues`.

## Risks / Trade-offs

- [Deployed config still sets `collectionPath: data.newPropertyValues`] → The message is accepted and the import runs, but the lookup key is the org login. Ship the example and docs with `newPropertyValues`, and change operator config in the same release. A gitignored local config in this checkout uses the old path and needs the same edit; do not commit that file.
- [Parsed updated is classified after `deliveryId`] → The updated predicate runs first. A body with `deliveryId` and no `action` is the import only when `repository` and `newPropertyValues` match.
- [`repository.updatedAt` is earlier than the removed wrapper `time`] → Idempotency uses `deliveryId`. Event time for this fixture is `2026-09-02T12:00:00Z`. Tests that assert October 1 must follow `repository.updatedAt`.

## Migration Plan

1. Set GitHub `scopeMapping.propertyExtractors.github.collectionPath` to `newPropertyValues` in deployed config and in `data/config.yaml.example`.
2. Deploy the worker that accepts the data object.
3. Post `github_parsed_updated.json` to `/github-events` and confirm 204, `repo.created`, `occurredAt` of `2026-09-02T12:00:00Z`, and Snyk org lookup key `sample-project`.

Rolling back the worker restores 422 for this body, because the connector already sends the data object.

## Open Questions

None.

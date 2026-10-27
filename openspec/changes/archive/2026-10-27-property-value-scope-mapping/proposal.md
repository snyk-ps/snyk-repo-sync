## Why

GitHub `custom_property_values.updated` carries the value that decides which Snyk organization a repository belongs to. Operators need a config-defined way to read that value from the message and map it to a Snyk org id, including the same kind of lookup for Azure payloads, while existing org and project mappings keep working.

## What Changes

- Add fixture `data/fixtures/github_parsed_updated.json` for the CloudEvents envelope `ENVLOG.GitHub.custom_property_values.updated`. Keep every current GitHub and ADO fixture valid.
- Treat that updated envelope as the GitHub import for this contract. Normalize it to `repo.created` and run the existing import path. `action: created` is not the import signal for this contract. Existing Service Bus `created` fixtures continue to normalize as they do today.
- Add one property extractor per provider under `scopeMapping`. The extractor walks a configured path to an array, selects the object whose match field equals a configured name (for the sample, `property_name` / `azure-devops-project`), and reads the value field. Each `propertyValue` row maps that extracted string to a `snykOrgId` inside an existing integration-type section.
- Keep `orgName` and `projectName` mappings. When the extractor returns a non-empty value, that value is the lookup key. When the path is missing or the matched value is null or blank, resolution uses the existing org or project key.
- When no mapping matches and `defaultSnykOrgId` is set, import into that org and log **WARN**. When no mapping matches and no default org is set, log **WARN** and complete the message with no Snyk side effects.
- Accept the updated envelope on Service Bus and on `POST /github-events`. `/github-events` continues to reject GitHub `created` and ADO payloads.
- Update `README.md`, `CONFIGURATION.md`, `INGESTION.md`, and `data/config.yaml.example` so they describe the updated contract and property mapping.

Deactivating a previous Azure DevOps Snyk target after the GitHub import is a follow-up change. This change does not record a link from the GitHub repository to an ADO target and does not remove or deactivate an ADO target.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `scope-mapping`: Provider property extractors, `propertyValue` entries, resolution order, and WARN logs for default-org fallback and unmapped scopes.
- `event-ingestion`: Accept the updated CloudEvents envelope as a GitHub queue and connector body alongside existing raw webhook and parsed lifecycle JSON.
- `sync-worker`: Normalize `ENVLOG.GitHub.custom_property_values.updated` to `repo.created` and resolve scope from the extracted property value when present.
- `github-events-http-ingress`: Accept the updated envelope on `POST /github-events` and return 204 after successful processing.
- `observability`: WARN logs for default-org fallback and unmapped scope include source, scope id, repository id, event id, and the extracted value when present.

## Impact

- **Code:** Scope-mapping parse and resolution, GitHub message classification and normalization, HTTP ingress boundary checks, and scope-resolution logging.
- **Configuration:** Optional `scopeMapping.propertyExtractors` and `propertyValue` rows. Existing `orgName` and `projectName` rows stay valid.
- **Fixtures:** `data/fixtures/github_parsed_updated.json`. Azure extractor behavior is covered with a synthetic payload in unit tests; no new ADO fixture.
- **Documentation:** `README.md`, `CONFIGURATION.md`, `INGESTION.md`, and `data/config.yaml.example`.
- **Dependencies:** None.

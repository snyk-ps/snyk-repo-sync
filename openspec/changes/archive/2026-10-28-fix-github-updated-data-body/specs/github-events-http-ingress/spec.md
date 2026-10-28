## MODIFIED Requirements

### Requirement: Kafka GitHub event boundary
The intended Kafka endpoint event set MUST be GitHub `updated`, `renamed`, `edited`, and `deleted`. GitHub `created` MUST NOT be part of this endpoint contract. The endpoint MUST process already-supported `renamed`, `edited`, and `deleted` payload shapes through the existing normalizer.

The endpoint MUST accept the parsed updated body in `data/fixtures/github_parsed_updated.json`. That body has top-level `repository` and `newPropertyValues` and no `action`. It is the import event for this contract. The endpoint MUST pass it to lifecycle processing. A successful import MUST return 204 under the synchronous acknowledgement requirement. The endpoint MUST NOT return 422 for that body.

ADO/Azure Repos payloads MUST return non-2xx and MUST NOT enter lifecycle processing on this endpoint.

#### Scenario: Existing renamed shape
- **WHEN** the connector posts an already-supported GitHub `renamed` payload
- **THEN** the endpoint processes the rename and returns 204 after successful processing

#### Scenario: Parsed updated body is the import
- **WHEN** the connector posts the `github_parsed_updated.json` body
- **THEN** the endpoint normalizes it for import and returns 204 after successful processing

#### Scenario: Created is not a Kafka endpoint event
- **WHEN** the connector posts a GitHub payload with `action: created`
- **THEN** the endpoint returns non-2xx and performs no create lifecycle action

#### Scenario: ADO payload posted
- **WHEN** the connector posts an ADO Event Grid or audit payload to `/github-events`
- **THEN** the endpoint returns non-2xx and performs no ADO lifecycle action

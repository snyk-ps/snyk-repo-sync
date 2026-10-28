## MODIFIED Requirements

### Requirement: Provider property extractor
Operators MAY configure `scopeMapping.propertyExtractors` with at most one extractor for `github` and at most one extractor for `azure-repos`. Each configured extractor MUST include non-empty `collectionPath`, `matchField`, `matchValue`, and `valueField`.

`collectionPath` MUST be a dotted path of non-empty object keys from the received JSON root to an array of objects. The worker MUST reject paths that contain empty segments, `..`, brackets, or filter syntax at startup. Unknown `propertyExtractors` keys MUST cause startup failure.

The worker MUST select array elements whose `matchField` equals `matchValue` and MUST read `valueField`. A missing path, a missing matching element, or a null or blank matched value MUST yield no extracted value. Two matching elements with the same non-empty value MUST yield that value. Two matching elements with different non-empty values MUST fail the message as invalid normalization. A present path whose intermediate or final node has the wrong JSON type MUST fail the message as invalid normalization.

#### Scenario: GitHub sample property extracted
- **WHEN** `propertyExtractors.github` uses `collectionPath: newPropertyValues`, `matchField: property_name`, `matchValue: azure-devops-project`, and `valueField: value`, and the message is `data/fixtures/github_parsed_updated.json`
- **THEN** scope resolution uses `sample-project` as the extracted lookup value

#### Scenario: GitHub updated path under data misses
- **WHEN** `propertyExtractors.github` uses `collectionPath: data.newPropertyValues` and the message is `data/fixtures/github_parsed_updated.json`
- **THEN** extraction yields no value and resolution continues with the GitHub organization login `sample-org`

#### Scenario: Existing fixture has no property path
- **WHEN** a current GitHub raw webhook or parsed lifecycle fixture is processed and the configured collection path is absent
- **THEN** extraction yields no value and resolution continues with the GitHub organization login

#### Scenario: Conflicting property values
- **WHEN** two array elements match the configured field and name and their non-empty values differ
- **THEN** the worker fails the message as invalid normalization and does not perform Snyk side effects

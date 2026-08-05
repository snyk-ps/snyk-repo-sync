## Purpose

Receive GitHub organization repository webhooks, validate authenticity, deduplicate deliveries, normalize payloads to the shared multi-source envelope, and publish to the Service Bus queue.

## Requirements

### Requirement: Webhook signature validation
The ingress endpoint MUST validate `X-Hub-Signature-256` using the configured webhook secret before accepting or enqueueing a payload.

#### Scenario: Valid signature
- **WHEN** GitHub delivers a webhook with a valid HMAC-SHA256 signature
- **THEN** the payload is accepted for normalization and queue publish

#### Scenario: Invalid or missing signature
- **WHEN** the signature is missing or does not match the payload
- **THEN** the request is rejected with HTTP 401/403 and no message is published

### Requirement: Delivery deduplication
The ingress path MUST deduplicate by GitHub delivery ID (`X-GitHub-Delivery`) before publishing to the queue.

#### Scenario: Duplicate delivery
- **WHEN** the same delivery ID is received more than once
- **THEN** only the first accepted delivery is published; subsequent duplicates are acknowledged without re-publishing

### Requirement: Normalized envelope publish
GitHub-derived events MUST be published to the same Service Bus queue using the shared envelope with `source: "github"`, `eventId` (delivery GUID), `eventType`, `scopeId` (org ID), `repositoryId` (numeric repo ID when applicable), `occurredAt`, and a provider-specific `payload`.

#### Scenario: Repository created webhook
- **WHEN** GitHub sends `repository` with action `created`
- **THEN** one normalized message with `eventType: repo.created` is published to the queue

#### Scenario: Repository renamed webhook
- **WHEN** GitHub sends `repository` with action `renamed`
- **THEN** one normalized message with `eventType: repo.renamed` is published to the queue

#### Scenario: Repository deleted webhook
- **WHEN** GitHub sends `repository` with action `deleted`
- **THEN** one normalized message with `eventType: repo.deleted` is published to the queue

#### Scenario: Default branch changed webhook
- **WHEN** GitHub sends `repository` with action `edited` and the default branch field changed
- **THEN** one normalized message with `eventType: repo.default_branch_changed` is published to the queue

### Requirement: Unsupported webhook actions ignored
The ingress path MUST acknowledge but MUST NOT enqueue webhooks for unsupported `repository` actions or non-repository event types.

#### Scenario: Unsupported repository action
- **WHEN** GitHub sends a `repository` webhook with an action other than created, renamed, deleted, or edited (default branch)
- **THEN** the request returns success without publishing to the queue

### Requirement: Secret handling
The webhook secret MUST be stored in Key Vault or environment configuration and MUST NOT appear in logs.

#### Scenario: Startup or validation failure logging
- **WHEN** signature validation or configuration errors are logged
- **THEN** the webhook secret value is omitted or redacted

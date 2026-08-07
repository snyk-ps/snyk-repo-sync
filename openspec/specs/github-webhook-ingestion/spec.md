## Purpose

Receive GitHub organization repository webhooks on customer-owned ingress infrastructure, validate authenticity, deduplicate deliveries, and publish raw payloads to the Service Bus queue. Lifecycle normalization is performed by the worker application in this repository.

## Requirements

### Requirement: Webhook signature validation
The ingress endpoint MUST validate `X-Hub-Signature-256` using the configured webhook secret before accepting or enqueueing a payload.

#### Scenario: Valid signature
- **WHEN** GitHub delivers a webhook with a valid HMAC-SHA256 signature
- **THEN** the payload is accepted for queue publish

#### Scenario: Invalid or missing signature
- **WHEN** the signature is missing or does not match the payload
- **THEN** the request is rejected with HTTP 401/403 and no message is published

### Requirement: Delivery deduplication
The ingress path MUST deduplicate by GitHub delivery ID (`X-GitHub-Delivery`) before publishing to the queue.

#### Scenario: Duplicate delivery
- **WHEN** the same delivery ID is received more than once
- **THEN** only the first accepted delivery is published; subsequent duplicates are acknowledged without re-publishing

### Requirement: Raw payload publish
GitHub webhooks MUST be published to the same Service Bus queue using the shared transport envelope with `source: "github"`, `ingressId` set to the delivery GUID, `receivedAt`, and the provider-native webhook body in `rawPayload`.

#### Scenario: Repository lifecycle webhook accepted
- **WHEN** GitHub delivers a signed `repository` webhook
- **THEN** one transport message containing the raw webhook body is published to the queue

### Requirement: Secret handling
The webhook secret MUST be stored in Key Vault or environment configuration and MUST NOT appear in logs.

#### Scenario: Startup or validation failure logging
- **WHEN** signature validation or configuration errors are logged
- **THEN** the webhook secret value is omitted or redacted

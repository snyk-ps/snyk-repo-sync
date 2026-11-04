## Why

`POST /github-events` turns a failed `ProcessingOutcome` into a status code and an empty body. A rejected `SNYK_TOKEN` returns 503 after `Parsed queue message` with no Snyk status or path. The Service Bus consumer and the storage-queue follow-up consumer both record `failure_kind`, `reason`, and `description` before dead-lettering. The connector retries from the status code alone, so those fields never reach the caller either.

## What Changes

- When `process_message_body` returns `status="failed"`, emit one error log containing `failure_kind`, `reason`, and `description`, then return the existing status.
- Return a JSON body on every non-2xx response with `failureKind`, `reason`, and `description`. `204` stays empty.
- Keep the status map: `invalid_message` and `invalid_normalization` stay 422, `dependency` stays 503, and `configuration` and `processing` stay 500. Boundary responses keep 400, 404, 405, 413, 415, and 422.
- Omit `SNYK_TOKEN` and authorization headers from the log and the body. The connector still retries every non-2xx response and does not use the body to decide retry.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `github-events-http-ingress`: A non-2xx `POST /github-events` response carries a JSON failure body, and a failed processing outcome is logged with `failure_kind`, `reason`, and `description` before that response.
- `observability`: That HTTP failure log is an operator diagnostic and follows the existing rule that tokens and authorization headers are omitted.

## Impact

- **Code:** `src/worker/http_ingress.py`, which today responds with `content-length: 0` for every status and does not log a failed `ProcessingOutcome`.
- **Tests:** `tests/worker/test_http_ingress.py` asserts the error log, the JSON body, and the current status for each failure kind. `204` stays an empty body with no failure log.
- **API:** Status codes are unchanged. Non-2xx responses gain a JSON body. The connector acknowledgement rule is unchanged: 2xx acknowledges, non-2xx retries.
- **Documentation:** `CONFIGURATION.md` and `INGESTION.md` describe the error JSON body. They still require the connector to retry every non-2xx response.
- **Dependencies:** None.

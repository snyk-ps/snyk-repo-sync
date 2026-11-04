## 1. HTTP failure response

- [x] 1.1 In `src/worker/http_ingress.py`, respond to every non-2xx status with `Content-Type: application/json` and a JSON object of string fields `failureKind`, `reason`, and `description`. Keep `204` as an empty body.
- [x] 1.2 Map boundary responses to the fields in the design: `400` `InvalidJson`, `404` `NotFound`, `405` `MethodNotAllowed`, `413` `RequestTooLarge`, `415` `UnsupportedMediaType`, and boundary `422` `UnsupportedPayload`.
- [x] 1.3 When `process_message_body` returns `status="failed"`, log one error containing `failure_kind`, `reason`, and `description`, then return the existing `_failure_status` with those fields in the JSON body. Use an empty description when the outcome has none.
- [x] 1.4 Return `503` with `failureKind` `dependency` and `reason` `FollowUpSchedulingError` when follow-up scheduling fails, keeping the current error log. Return `500` with `failureKind` `processing` and `reason` `UnexpectedError` for an unexpected exception, with `str(exc)` as the description and the traceback only in the existing `logger.exception` log.
- [x] 1.5 Leave `_failure_status`, the Service Bus log line, and storage-queue settlement unchanged. Omit `SNYK_TOKEN` and authorization headers from the log and the body.

## 2. Tests

- [x] 2.1 Extend `tests/worker/test_http_ingress.py` so each failed `failure_kind` asserts the current status, the JSON body fields, and the error log. Assert a completed outcome still returns `204` with an empty body and no processing-failure error log.
- [x] 2.2 Assert malformed JSON returns `400` with `reason` `InvalidJson` and does not emit the processing-failure error log. Assert follow-up scheduling failure returns `503` with `reason` `FollowUpSchedulingError`.

## 3. Documentation

- [x] 3.1 Update `CONFIGURATION.md` and `INGESTION.md` so non-2xx responses include the JSON object and the connector still retries from the status code. `204` stays empty.

## 4. Archive

- [ ] 4.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/http-ingress-failure-details/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive http-ingress-failure-details` (or project equivalent) to fold deltas into canonical specs.

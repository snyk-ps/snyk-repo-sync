## Context

`GitHubEventsApp` calls `process_message_body`. On `status="failed"` it maps `failure_kind` to a status and responds with `content-length: 0`. `src/worker/consumer.py` logs `kind`, `reason`, and `description` for the same outcome before dead-lettering. The storage-queue follow-up consumer passes those fields into poison settlement.

Follow-up scheduling failures and unexpected exceptions in the HTTP app are already logged. Boundary responses (400, 404, 405, 413, 415, and 422 from `_validate_github_boundary`) happen before `process_message_body` and also return an empty body.

The connector treats 2xx as acknowledgement and every non-2xx response as retryable. It does not read a body to choose that. `204` means no content.

## Goals / Non-Goals

**Goals:**

- Log every failed `ProcessingOutcome` on the HTTP path before returning its status.
- Return one JSON object on every non-2xx response so the caller can see `failureKind`, `reason`, and `description`.
- Leave status codes, `204`, and connector retry behavior unchanged.

**Non-Goals:**

- Changing Service Bus or storage-queue settlement logs.
- Adding an error log for boundary rejections such as `GET /` or an unsupported payload. The JSON body is the diagnostic for those responses.
- Putting a stack trace in the response body.
- Changing which status `_failure_status` returns.

## Decisions

1. **Log failed outcomes in `GitHubEventsApp`.** When `outcome.status == "failed"`, emit one error log containing `failure_kind`, `reason`, and `description`, then return the existing status. The line identifies an HTTP ingress processing failure. It does not say the message was dead-lettered. Follow-up scheduling keeps its current error log. Unexpected exceptions keep `logger.exception`.

2. **JSON body for every non-2xx response.** `Content-Type` is `application/json`. The object is:

   ```json
   {"failureKind": "dependency", "reason": "SnykApiError", "description": "Snyk API GET /v1/group/{groupId}/orgs failed with 401: ..."}
   ```

   `description` is a string and is empty when the outcome has no description. `204` keeps `content-length: 0` and no body.

   Failed outcomes use the outcome fields, with `failureKind` set from `failure_kind`. Other responses use:

   | Status | failureKind | reason |
   | --- | --- | --- |
   | 400 | `invalid_message` | `InvalidJson` |
   | 404 | `request` | `NotFound` |
   | 405 | `request` | `MethodNotAllowed` |
   | 413 | `request` | `RequestTooLarge` |
   | 415 | `request` | `UnsupportedMediaType` |
   | 422 from the GitHub boundary | `invalid_message` | `UnsupportedPayload` |
   | 503 follow-up scheduling | `dependency` | `FollowUpSchedulingError` |
   | 500 unexpected exception | `processing` | `UnexpectedError` |

   Boundary and unexpected-exception descriptions are a short stable sentence or `str(exc)`. The unexpected-exception body omits the traceback that `logger.exception` already records.

3. **Omit secrets.** The log and the body use the stored description. They do not read request headers and do not interpolate `SNYK_TOKEN`. `SnykApiError` text already omits the `Authorization` header.

4. **Document the additive body.** `CONFIGURATION.md` and `INGESTION.md` state that non-2xx responses include this JSON object and that the connector still retries from the status code.

**Alternative rejected:** Log only, and leave the body empty. The connector log is where operators see the 503, and an empty body leaves that log without the Snyk path and status.

**Alternative rejected:** Put the reason only in the body and skip the worker log. Dynatrace alerting is defined on the worker log. A body helps only when the caller records it.

## Risks / Trade-offs

- [A Snyk error description can contain non-secret API text] → The Service Bus path already logs that text. The HTTP log and body use the same text and still omit the token.
- [Connector retries repeat the log once per attempt] → That matches the repeated 503s operators already see.
- [A caller that required `content-length: 0` on errors would break] → The published contract specifies status-based retry and `204` for success. Error bodies were an implementation choice, not a connector control.

## Migration Plan

Deploy the worker. No config change. Rollback is the previous image. In-flight connector retries are unaffected because the status contract does not change.

## Open Questions

None.

## Context

`SnykClient.find_target_id` lists targets with:

```python
query = {
    "version": REST_API_VERSION,
    "source_types": source_type,
    "display_name": normalize_repo_name(repo_name),
    "limit": "100",
}
```

Snyk OpenAPI documents `exclude_empty` with default **`true`**: “Return only the targets that has projects.” Empty imported repos create targets with zero projects; they are excluded from the response, so `select_target_id` never sees them and lookup fails indefinitely.

Observed symptom: import job `complete`, target visible in Snyk UI, absent from `/targets` response until `exclude_empty=false` (validated in Postman).

## Goals / Non-Goals

**Goals:**

- Target id resolution succeeds for empty targets after import.
- Rename/branch-change/delete flows that REST-lookup the old target also see empty targets.

**Non-goals:**

- Configurable `exclude_empty` in operator YAML.
- Listing empty targets for operator diagnostics outside worker code paths.

## Decisions

### Always pass `exclude_empty=false` on target list

| Option | Verdict |
| --- | --- |
| Add `exclude_empty=false` to `find_target_id` query | **Chosen** — minimal fix, matches Snyk docs and Postman validation |
| Remove `display_name` filter and scan all targets | Rejected — unnecessary API volume; not root cause |
| Treat “import complete, no target” as success without id | Rejected — breaks sync-state contract requiring `snykTargetId` |

Implementation:

```python
query = {
    ...
    "exclude_empty": "false",
}
```

Use string `"false"` to match existing string query values (e.g. `"100"` for limit) in `_request_rest`.

### Pagination

First request includes `exclude_empty=false`. Follow `links.next` as today. **Risk:** Snyk next URLs may omit or override params; acceptable for current target volumes; revisit if large-org pagination fails.

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| Larger target list payloads | `display_name` filter still applied; limit 100 |
| Next-page links drop `exclude_empty` | Monitor; add follow-up if reported |
| Empty targets included in accidental broad scans | Only `find_target_id` lists targets today |

## Migration Plan

1. Deploy patch (**`v1.1.1`**) — no config change.
2. Replay dead-lettered import_poll messages or re-send lifecycle events for affected repos.

## Open Questions

_None._

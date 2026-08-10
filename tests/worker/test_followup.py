"""Tests for internal follow-up envelopes and backoff."""

import pytest

from worker.followup import (
    IMPORT_JOB_FAILED_REASON,
    MAX_IMPORT_POLL_RETRIES,
    build_import_poll_message,
    compute_backoff_seconds,
    parse_internal_follow_up,
)


def test_compute_backoff_seconds_exponential_with_cap() -> None:
    assert compute_backoff_seconds(0) == 30
    assert compute_backoff_seconds(1) == 60
    assert compute_backoff_seconds(10) == 900


def test_parse_import_poll_message() -> None:
    message = parse_internal_follow_up(
        build_import_poll_message(
            source="ado",
            scope_id="scope",
            repository_id="repo",
            source_event_id="evt",
            import_job_id="job",
            import_status="pending",
            retry_count=2,
            ado_project_name="proj",
        ),
    )

    assert message.sync_phase == "import_poll"
    assert message.retry_count == 2
    assert message.ado_project_name == "proj"


def test_import_poll_max_retries_constant() -> None:
    assert MAX_IMPORT_POLL_RETRIES == 5
    assert IMPORT_JOB_FAILED_REASON == "ImportJobFailed"


def test_parse_internal_follow_up_rejects_unknown_phase() -> None:
    with pytest.raises(ValueError, match="syncPhase"):
        parse_internal_follow_up({"syncPhase": "unknown", "source": "ado"})

"""Tests for native queue message parsing."""

import json
from pathlib import Path

import pytest

from worker.message import MessageParseError, parse_queue_message

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def test_parse_ado_fixture_by_subject() -> None:
    body = (FIXTURES / "eventgrid_ado_default_branch_changed.json").read_text(encoding="utf-8")
    message = parse_queue_message(body)
    assert message.source == "ado"
    assert message.event_id == "acf86b70-4ec3-4052-9e0b-fbcdd5109c1f"
    assert message.provider_payload["ActionId"] == "Git.RepositoryDefaultBranchChanged"


def test_parse_ado_fixture_by_event_type_only() -> None:
    body = (FIXTURES / "eventgrid_ado_by_event_type_only.json").read_text(encoding="utf-8")
    message = parse_queue_message(body)
    assert message.source == "ado"
    assert message.provider_payload["ActionId"] == "Git.RepositoryDefaultBranchChanged"


def test_parse_github_fixture() -> None:
    body = (FIXTURES / "github_webhook_created.json").read_text(encoding="utf-8")
    message = parse_queue_message(body)
    assert message.source == "github"
    assert message.provider_payload["action"] == "created"


def test_parse_invalid_json() -> None:
    with pytest.raises(MessageParseError, match="valid JSON"):
        parse_queue_message("{not-json")


def test_parse_unrecognized_shape() -> None:
    with pytest.raises(MessageParseError, match="unrecognized queue message shape"):
        parse_queue_message(json.dumps({"foo": "bar"}))


def test_parse_ado_missing_data() -> None:
    payload = {
        "subject": "AzureDevOps/Auditing",
        "eventType": "AzureDevOpsAuditEvent",
    }
    with pytest.raises(MessageParseError, match="missing audit record"):
        parse_queue_message(json.dumps(payload))

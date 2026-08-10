"""Tests for internal queue message routing."""

import json

import pytest

from worker.message import MessageParseError, parse_inbound_message, parse_queue_message


def test_parse_inbound_internal_import_poll() -> None:
    body = json.dumps(
        {
            "syncPhase": "import_poll",
            "source": "ado",
            "scopeId": "scope",
            "repositoryId": "repo",
            "sourceEventId": "evt",
            "importJobId": "job",
            "importStatus": "pending",
            "retryCount": 0,
            "adoProjectName": "proj",
        },
    )
    inbound = parse_inbound_message(body)

    assert inbound.kind == "internal"
    assert inbound.internal is not None
    assert inbound.internal.sync_phase == "import_poll"


def test_parse_inbound_provider_ado_still_works() -> None:
    body = json.dumps(
        {
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {"Id": "evt", "ActionId": "Git.RepositoryCreated"},
        },
    )
    inbound = parse_inbound_message(body)

    assert inbound.kind == "provider"
    assert inbound.provider is not None
    assert inbound.provider.source == "ado"


def test_internal_message_not_parsed_as_github_webhook() -> None:
    body = json.dumps(
        {
            "syncPhase": "lifecycle_deferred",
            "source": "ado",
            "scopeId": "scope",
            "repositoryId": "repo",
            "sourceEventId": "evt",
            "retryCount": 0,
            "eventType": "repo.created",
            "repositoryName": "demo",
            "adoProjectName": "proj",
            "defaultBranch": "main",
            "payload": {},
        },
    )
    inbound = parse_inbound_message(body)
    assert inbound.kind == "internal"


def test_parse_queue_message_still_rejects_internal_shape_without_sync_phase_router() -> None:
    body = json.dumps({"syncPhase": "import_poll", "source": "ado"})
    with pytest.raises(MessageParseError):
        parse_queue_message(body)

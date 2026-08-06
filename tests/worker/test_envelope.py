"""Tests for transport envelope parsing."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from worker.envelope import EnvelopeValidationError, parse_transport_envelope

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def test_parse_ado_fixture() -> None:
    body = (FIXTURES / "transport_envelope_ado.json").read_text(encoding="utf-8")
    envelope = parse_transport_envelope(body)
    assert envelope.source == "ado"
    assert envelope.ingress_id == "ado-hook-repo-created-001"
    assert envelope.received_at == datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
    assert envelope.raw_payload["eventType"] == "git.repo.created"


def test_parse_github_fixture() -> None:
    body = (FIXTURES / "transport_envelope_github.json").read_text(encoding="utf-8")
    envelope = parse_transport_envelope(body)
    assert envelope.source == "github"
    assert envelope.ingress_id == "github-delivery-guid-001"
    assert envelope.raw_payload["action"] == "created"


def test_parse_invalid_json() -> None:
    with pytest.raises(EnvelopeValidationError, match="valid JSON"):
        parse_transport_envelope("{not-json")


def test_parse_invalid_source() -> None:
    payload = {
        "source": "gitlab",
        "ingressId": "x",
        "receivedAt": "2026-08-05T18:00:00Z",
        "rawPayload": {},
    }
    with pytest.raises(EnvelopeValidationError, match="source"):
        parse_transport_envelope(json.dumps(payload))


def test_parse_missing_ingress_id() -> None:
    payload = {
        "source": "ado",
        "ingressId": "",
        "receivedAt": "2026-08-05T18:00:00Z",
        "rawPayload": {},
    }
    with pytest.raises(EnvelopeValidationError, match="ingressId"):
        parse_transport_envelope(json.dumps(payload))


def test_parse_invalid_received_at() -> None:
    payload = {
        "source": "ado",
        "ingressId": "abc",
        "receivedAt": "not-a-date",
        "rawPayload": {},
    }
    with pytest.raises(EnvelopeValidationError, match="receivedAt"):
        parse_transport_envelope(json.dumps(payload))


def test_parse_non_object_raw_payload() -> None:
    payload = {
        "source": "ado",
        "ingressId": "abc",
        "receivedAt": "2026-08-05T18:00:00Z",
        "rawPayload": "bad",
    }
    with pytest.raises(EnvelopeValidationError, match="rawPayload"):
        parse_transport_envelope(json.dumps(payload))

"""Transport envelope model for queue messages."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

VALID_SOURCES = frozenset({"ado", "github"})


class EnvelopeValidationError(ValueError):
    """Raised when a transport envelope fails validation."""


@dataclass(frozen=True)
class TransportEnvelope:
    """Queue message body for provider-native lifecycle events."""

    source: str
    ingress_id: str
    received_at: datetime
    raw_payload: dict[str, Any]


def _parse_received_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EnvelopeValidationError("receivedAt must be a non-empty ISO-8601 string")

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EnvelopeValidationError(
            "receivedAt must be a valid ISO-8601 timestamp"
        ) from exc


def parse_transport_envelope(body: str | bytes) -> TransportEnvelope:
    """Parse and validate a transport envelope from a queue message body.

    Args:
        body: Raw JSON message body.

    Returns:
        Validated transport envelope.

    Raises:
        EnvelopeValidationError: If JSON or envelope fields are invalid.
    """
    if isinstance(body, bytes):
        text = body.decode("utf-8")
    else:
        text = body

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EnvelopeValidationError("message body must be valid JSON") from exc

    if not isinstance(data, dict):
        raise EnvelopeValidationError("message body must be a JSON object")

    source = data.get("source")
    if source not in VALID_SOURCES:
        raise EnvelopeValidationError('source must be "ado" or "github"')

    ingress_id = data.get("ingressId")
    if not isinstance(ingress_id, str) or not ingress_id.strip():
        raise EnvelopeValidationError("ingressId must be a non-empty string")

    received_at = _parse_received_at(data.get("receivedAt"))

    raw_payload = data.get("rawPayload")
    if not isinstance(raw_payload, dict):
        raise EnvelopeValidationError("rawPayload must be a JSON object")

    return TransportEnvelope(
        source=source,
        ingress_id=ingress_id.strip(),
        received_at=received_at,
        raw_payload=raw_payload,
    )

"""Slice-2 message handling: validate envelope, normalize ADO events, complete."""

import logging
from dataclasses import dataclass

from worker.envelope import EnvelopeValidationError, TransportEnvelope, parse_transport_envelope
from worker.normalize import NormalizationError, NormalizedEvent, normalize_ado_lifecycle_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandleResult:
    """Outcome of transport message handling before queue settlement."""

    envelope: TransportEnvelope
    normalized: NormalizedEvent | None = None


def handle_transport_message(body: str | bytes) -> HandleResult:
    """Validate a transport envelope and normalize supported ADO lifecycle events.

    GitHub envelopes are validated and passed through without normalization.
    Sync actions are intentionally omitted in this slice.

    Args:
        body: Raw queue message body.

    Returns:
        Parsed envelope and optional normalized event.

    Raises:
        EnvelopeValidationError: If the envelope is malformed.
        NormalizationError: If ADO normalization fails.
    """
    envelope = parse_transport_envelope(body)
    logger.info(
        "Validated transport envelope",
        extra={
            "source": envelope.source,
            "ingress_id": envelope.ingress_id,
            "received_at": envelope.received_at.isoformat(),
        },
    )

    if envelope.source == "github":
        logger.info(
            "GitHub normalization deferred; completing without lifecycle processing",
            extra={"ingress_id": envelope.ingress_id},
        )
        return HandleResult(envelope=envelope)

    normalized = normalize_ado_lifecycle_event(envelope)
    logger.info(
        "Normalized ADO lifecycle event",
        extra={
            "event_type": normalized.event_type,
            "event_id": normalized.event_id,
            "scope_id": normalized.scope_id,
            "repository_id": normalized.repository_id,
            "ado_org_id": normalized.ado.org_id,
            "ado_org_display_name": normalized.ado.org_display_name,
            "ado_project_id": normalized.ado.project_id,
            "ado_project_name": normalized.ado.project_name,
            "repository_name": normalized.repository.name,
            "payload": normalized.payload,
        },
    )
    return HandleResult(envelope=envelope, normalized=normalized)

"""Slice-1 message handling: validate transport envelope and complete."""

import logging

from worker.envelope import EnvelopeValidationError, TransportEnvelope, parse_transport_envelope

logger = logging.getLogger(__name__)


def handle_transport_message(body: str | bytes) -> TransportEnvelope:
    """Validate a transport envelope for slice-1 processing.

    Normalization and sync actions are intentionally omitted in this slice.

    Args:
        body: Raw queue message body.

    Returns:
        Parsed transport envelope.

    Raises:
        EnvelopeValidationError: If the envelope is malformed.
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
    return envelope

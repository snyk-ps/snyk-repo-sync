"""Service Bus configuration loaded from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

CONNECTION_STRING_ENV = "SERVICEBUS_CONNECTION_STRING"
QUEUE_NAME_ENV = "SERVICEBUS_QUEUE_NAME"


class ServiceBusConfigError(ValueError):
    """Raised when required Service Bus environment variables are missing."""


@dataclass(frozen=True)
class ServiceBusSettings:
    """Non-secret Service Bus settings and connection reference."""

    connection_string: str
    queue_name: str


def load_service_bus_settings(
    environ: Mapping[str, str] | None = None,
) -> ServiceBusSettings:
    """Load Service Bus settings from the environment.

    Args:
        environ: Optional environment mapping for testing.

    Returns:
        Validated Service Bus settings.

    Raises:
        ServiceBusConfigError: If a required variable is missing or empty.
    """
    env = os.environ if environ is None else environ
    connection_string = env.get(CONNECTION_STRING_ENV, "").strip()
    queue_name = env.get(QUEUE_NAME_ENV, "").strip()

    missing = []
    if not connection_string:
        missing.append(CONNECTION_STRING_ENV)
    if not queue_name:
        missing.append(QUEUE_NAME_ENV)

    if missing:
        joined = ", ".join(missing)
        raise ServiceBusConfigError(
            f"Missing required environment variable(s): {joined}"
        )

    return ServiceBusSettings(
        connection_string=connection_string,
        queue_name=queue_name,
    )

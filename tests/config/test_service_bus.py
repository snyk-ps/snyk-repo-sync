"""Tests for Service Bus environment configuration."""

import pytest

from config.service_bus import (
    CONNECTION_STRING_ENV,
    QUEUE_NAME_ENV,
    ServiceBusConfigError,
    load_service_bus_settings,
)


def test_load_service_bus_settings_success() -> None:
    settings = load_service_bus_settings(
        {
            CONNECTION_STRING_ENV: "Endpoint=sb://example/",
            QUEUE_NAME_ENV: "repo-sync-events",
        }
    )
    assert settings.queue_name == "repo-sync-events"
    assert settings.connection_string == "Endpoint=sb://example/"


def test_load_service_bus_settings_missing_connection_string() -> None:
    with pytest.raises(ServiceBusConfigError, match=CONNECTION_STRING_ENV):
        load_service_bus_settings({QUEUE_NAME_ENV: "repo-sync-events"})


def test_load_service_bus_settings_missing_queue_name() -> None:
    with pytest.raises(ServiceBusConfigError, match=QUEUE_NAME_ENV):
        load_service_bus_settings({CONNECTION_STRING_ENV: "Endpoint=sb://example/"})


def test_load_service_bus_settings_uses_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONNECTION_STRING_ENV, "Endpoint=sb://test/")
    monkeypatch.setenv(QUEUE_NAME_ENV, "events")
    settings = load_service_bus_settings()
    assert settings.queue_name == "events"

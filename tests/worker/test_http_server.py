"""Tests for the Uvicorn HTTP server adapter."""

from unittest.mock import MagicMock

from config.settings import HttpSettings
from worker.http_server import UvicornHttpServer


def test_uvicorn_server_uses_http_bind_settings() -> None:
    server = MagicMock()
    factory = MagicMock(return_value=server)
    app = object()

    adapter = UvicornHttpServer(
        app,
        HttpSettings(bind_host="127.0.0.1", port=9090),
        server_factory=factory,
    )
    config = factory.call_args.args[0]

    assert config.app is app
    assert config.host == "127.0.0.1"
    assert config.port == 9090
    adapter.run()
    server.run.assert_called_once_with()


def test_uvicorn_server_stop_requests_shutdown() -> None:
    server = MagicMock()
    adapter = UvicornHttpServer(
        object(),
        HttpSettings(),
        server_factory=MagicMock(return_value=server),
    )

    adapter.stop()

    assert server.should_exit is True

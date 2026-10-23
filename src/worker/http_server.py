"""Uvicorn adapter for the GitHub events ASGI application."""

from __future__ import annotations

from typing import Any, Callable

import uvicorn

from config.settings import HttpSettings


class UvicornHttpServer:
    """Run and stop one configured Uvicorn server."""

    def __init__(
        self,
        app: Any,
        settings: HttpSettings,
        *,
        server_factory: Callable[[uvicorn.Config], uvicorn.Server] = uvicorn.Server,
    ) -> None:
        config = uvicorn.Config(
            app,
            host=settings.bind_host,
            port=settings.port,
            log_config=None,
        )
        self._server = server_factory(config)

    def run(self) -> None:
        """Run the server until shutdown or failure."""
        self._server.run()

    def stop(self) -> None:
        """Request graceful Uvicorn shutdown."""
        self._server.should_exit = True

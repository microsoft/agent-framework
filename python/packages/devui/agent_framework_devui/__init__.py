# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework DevUI - Debug interface with OpenAI compatible API server."""

import logging
import webbrowser
from typing import Any

from ._server import DevServer
from .models import AgentFrameworkRequest, OpenAIError, OpenAIResponse, ResponseStreamEvent
from .models._discovery_models import DiscoveryResponse, EntityInfo

logger = logging.getLogger(__name__)

__version__ = "0.1.0"


def serve(
    entities: list[Any] | None = None,
    entities_dir: str | None = None,
    port: int = 8080,
    host: str = "127.0.0.1",
    auto_open: bool = False,
    cors_origins: list[str] | None = None,
    ui_enabled: bool = True,
) -> None:
    """Launch Agent Framework DevUI with simple API.

    Args:
        entities: List of entities for in-memory registration (IDs auto-generated)
        entities_dir: Directory to scan for entities
        port: Port to run server on
        host: Host to bind server to
        auto_open: Whether to automatically open browser
        cors_origins: List of allowed CORS origins
        ui_enabled: Whether to enable the UI
    """
    import uvicorn

    # Create server with direct parameters
    server = DevServer(
        entities_dir=entities_dir, port=port, host=host, cors_origins=cors_origins, ui_enabled=ui_enabled
    )

    # Register in-memory entities if provided
    if entities:
        logger.info(f"Registering {len(entities)} in-memory entities")
        # Store entities for later registration during server startup
        server._pending_entities = entities

    app = server.get_app()

    if auto_open:

        def open_browser() -> None:
            import time

            time.sleep(1.5)
            webbrowser.open(f"http://{host}:{port}")

        import threading

        threading.Thread(target=open_browser, daemon=True).start()

    logger.info(f"Starting Agent Framework DevUI on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    """CLI entry point for devui command."""
    from ._cli import main as cli_main

    cli_main()


# Export main public API
__all__ = [
    "AgentFrameworkRequest",
    "DevServer",
    "DiscoveryResponse",
    "EntityInfo",
    "OpenAIError",
    "OpenAIResponse",
    "ResponseStreamEvent",
    "main",
    "serve",
]

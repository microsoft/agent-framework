# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework DevUI - Debug interface with OpenAI compatible API server."""

import importlib.metadata
import logging
import webbrowser
from typing import Any

from ._server import DevServer
from .models import AgentFrameworkRequest, OpenAIError, OpenAIResponse, ResponseStreamEvent
from .models._discovery_models import DiscoveryResponse, EntityInfo

logger = logging.getLogger(__name__)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


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
    import re

    import uvicorn

    # Validate host parameter early for security
    if not re.match(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|[a-zA-Z0-9.-]+)$", host):
        raise ValueError(f"Invalid host: {host}. Must be localhost, IP address, or valid hostname")

    # Validate port parameter
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError(f"Invalid port: {port}. Must be integer between 1 and 65535")

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
            import http.client
            import re
            import time

            # Validate host and port for security
            if not re.match(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|[a-zA-Z0-9.-]+)$", host):
                logger.warning(f"Invalid host for auto-open: {host}")
                return

            if not isinstance(port, int) or not (1 <= port <= 65535):
                logger.warning(f"Invalid port for auto-open: {port}")
                return

            # Wait for server to be ready by checking health endpoint
            browser_url = f"http://{host}:{port}"

            for _ in range(30):  # 15 second timeout (30 * 0.5s)
                try:
                    # Use http.client for safe connection handling (standard library)
                    conn = http.client.HTTPConnection(host, port, timeout=1)
                    try:
                        conn.request("GET", "/health")
                        response = conn.getresponse()
                        if response.status == 200:
                            webbrowser.open(browser_url)
                            return
                    finally:
                        conn.close()
                except (http.client.HTTPException, OSError, TimeoutError):
                    pass
                time.sleep(0.5)

            # Fallback: open browser anyway after timeout
            webbrowser.open(browser_url)

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

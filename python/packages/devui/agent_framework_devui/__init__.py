# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework DevUI - Debug interface with OpenAI compatible API server."""

import importlib.metadata
import logging
import webbrowser
from collections.abc import Callable
from typing import Any

from ._conversations import CheckpointConversationManager
from ._server import DevServer
from .models import AgentFrameworkRequest, OpenAIError, OpenAIResponse, ResponseStreamEvent
from .models._discovery_models import DiscoveryResponse, EntityInfo, EnvVarRequirement

logger = logging.getLogger(__name__)

# Module-level cleanup registry (before serve() is called)
_cleanup_registry: dict[int, list[Callable[[], Any]]] = {}

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


def register_cleanup(entity: Any, *hooks: Callable[[], Any]) -> None:
    """Register cleanup hook(s) for an entity.

    Cleanup hooks execute during DevUI server shutdown, before entity
    clients are closed. Supports both synchronous and asynchronous callables.

    Args:
        entity: Agent, workflow, or other entity object
        *hooks: One or more cleanup callables (sync or async)

    Raises:
        ValueError: If no hooks provided

    Examples:
        Single cleanup hook:
        >>> from agent_framework.devui import serve, register_cleanup
        >>> credential = DefaultAzureCredential()
        >>> agent = ChatAgent(...)
        >>> register_cleanup(agent, credential.close)
        >>> serve(entities=[agent])

        Multiple cleanup hooks:
        >>> register_cleanup(agent, credential.close, session.close, db_pool.close)

        Works with file-based discovery:
        >>> # In agents/my_agent/agent.py
        >>> from agent_framework.devui import register_cleanup
        >>> credential = DefaultAzureCredential()
        >>> agent = ChatAgent(...)
        >>> register_cleanup(agent, credential.close)
        >>> # Run: devui ./agents
    """
    if not hooks:
        raise ValueError("At least one cleanup hook required")

    # Use id() to track entity identity (works across modules)
    entity_id = id(entity)

    if entity_id not in _cleanup_registry:
        _cleanup_registry[entity_id] = []

    _cleanup_registry[entity_id].extend(hooks)

    logger.debug(
        f"Registered {len(hooks)} cleanup hook(s) for {type(entity).__name__} "
        f"(id: {entity_id}, total: {len(_cleanup_registry[entity_id])})"
    )


def _get_registered_cleanup_hooks(entity: Any) -> list[Callable[[], Any]]:
    """Get cleanup hooks registered for an entity (internal use).

    Args:
        entity: Entity object to get hooks for

    Returns:
        List of cleanup hooks registered for the entity
    """
    entity_id = id(entity)
    return _cleanup_registry.get(entity_id, [])


def serve(
    entities: list[Any] | None = None,
    entities_dir: str | None = None,
    port: int = 8080,
    host: str = "127.0.0.1",
    auto_open: bool = False,
    cors_origins: list[str] | None = None,
    ui_enabled: bool = True,
    tracing_enabled: bool = False,
    mode: str = "developer",
    auth_enabled: bool = False,
    auth_token: str | None = None,
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
        tracing_enabled: Whether to enable OpenTelemetry tracing
        mode: Server mode - 'developer' (full access, verbose errors) or 'user' (restricted APIs, generic errors)
        auth_enabled: Whether to enable Bearer token authentication
        auth_token: Custom authentication token (auto-generated if not provided with auth_enabled=True)
    """
    import re

    import uvicorn

    # Validate host parameter early for security
    if not re.match(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|[a-zA-Z0-9.-]+)$", host):
        raise ValueError(f"Invalid host: {host}. Must be localhost, IP address, or valid hostname")

    # Validate port parameter
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError(f"Invalid port: {port}. Must be integer between 1 and 65535")

    # Security check: Warn if network-exposed without authentication
    if host not in ("127.0.0.1", "localhost") and not auth_enabled:
        logger.warning("⚠️  WARNING: Exposing DevUI to network without authentication!")
        logger.warning("⚠️  This is INSECURE - anyone on your network can access your agents")
        logger.warning("💡 For network exposure, add --auth flag: devui --host 0.0.0.0 --auth")

    # Handle authentication configuration
    if auth_enabled:
        import os
        import secrets

        # Check if token is in environment variable first
        if not auth_token:
            auth_token = os.environ.get("DEVUI_AUTH_TOKEN")

        # Auto-generate token if STILL not provided
        if not auth_token:
            # Check if we're in a production-like environment
            is_production = (
                host not in ("127.0.0.1", "localhost")  # Exposed to network
                or os.environ.get("CI") == "true"  # Running in CI
                or os.environ.get("KUBERNETES_SERVICE_HOST")  # Running in k8s
            )

            if is_production:
                # REFUSE to start without explicit token
                logger.error("❌ Authentication enabled but no token provided")
                logger.error("❌ Auto-generated tokens are NOT secure for network-exposed deployments")
                logger.error("💡 Set token: export DEVUI_AUTH_TOKEN=<your-secure-token>")
                logger.error("💡 Or pass: serve(entities=[...], auth_token='your-token')")
                raise ValueError("DEVUI_AUTH_TOKEN required when host is not localhost")

            # Development mode: auto-generate and show
            auth_token = secrets.token_urlsafe(32)
            logger.info("🔒 Authentication enabled with auto-generated token")
            logger.info("\n" + "=" * 70)
            logger.info("🔑 DEV TOKEN (localhost only, shown once):")
            logger.info(f"   {auth_token}")
            logger.info("=" * 70 + "\n")
        else:
            logger.info("🔒 Authentication enabled with provided token")

        # Set environment variable for server to use
        os.environ["AUTH_REQUIRED"] = "true"
        os.environ["DEVUI_AUTH_TOKEN"] = auth_token

    # Configure tracing environment variables if enabled
    if tracing_enabled:
        import os

        # Only set if not already configured by user
        if not os.environ.get("ENABLE_OTEL"):
            os.environ["ENABLE_OTEL"] = "true"
            logger.info("Set ENABLE_OTEL=true for tracing")

        if not os.environ.get("ENABLE_SENSITIVE_DATA"):
            os.environ["ENABLE_SENSITIVE_DATA"] = "true"
            logger.info("Set ENABLE_SENSITIVE_DATA=true for tracing")

        if not os.environ.get("OTLP_ENDPOINT"):
            os.environ["OTLP_ENDPOINT"] = "http://localhost:4317"
            logger.info("Set OTLP_ENDPOINT=http://localhost:4317 for tracing")

    # Create server with direct parameters
    server = DevServer(
        entities_dir=entities_dir,
        port=port,
        host=host,
        cors_origins=cors_origins,
        ui_enabled=ui_enabled,
        mode=mode,
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
    "CheckpointConversationManager",
    "DevServer",
    "DiscoveryResponse",
    "EntityInfo",
    "EnvVarRequirement",
    "OpenAIError",
    "OpenAIResponse",
    "ResponseStreamEvent",
    "main",
    "register_cleanup",
    "serve",
]

# Copyright (c) Microsoft. All rights reserved.

"""Run a deterministic local streamable HTTP MCP server for integration tests."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8011
DEFAULT_MOUNT_PATH = "/mcp"
SERVER_NAME = "agent-framework-local-ci-mcp"
AGENT_FRAMEWORK_DESCRIPTION = (
    "Microsoft Agent Framework is a multi-language framework for building, orchestrating, and deploying AI agents."
)


def _normalize_mount_path(path: str) -> str:
    """Normalize a configured mount path for the streamable HTTP endpoint."""
    normalized = path.strip() or DEFAULT_MOUNT_PATH
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/") or "/"


def create_server(*, host: str, port: int, mount_path: str) -> FastMCP:
    """Create the local MCP integration test server."""
    server = FastMCP(
        name=SERVER_NAME,
        instructions="Deterministic local MCP server used by Agent Framework integration tests.",
        host=host,
        port=port,
        streamable_http_path=mount_path,
        log_level="INFO",
    )

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> Response:
        """Return a simple readiness response for CI health checks."""
        await asyncio.sleep(0)
        return JSONResponse(
            {
                "status": "ok",
                "name": SERVER_NAME,
                "mcp_path": mount_path,
            }
        )

    @server.tool(
        name="search_agent_framework_docs",
        description="Return deterministic Agent Framework documentation text for MCP integration tests.",
    )
    def search_agent_framework_docs(query: str) -> str:
        """Return a deterministic response for the MCP integration tests."""
        return (
            f"{AGENT_FRAMEWORK_DESCRIPTION}\n\n"
            f"Query: {query}\n"
            "This response came from the local streamable HTTP MCP integration test server."
        )

    return server


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the local MCP server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind.")
    parser.add_argument(
        "--mount-path",
        default=DEFAULT_MOUNT_PATH,
        help="Mount path for the streamable HTTP MCP endpoint.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> None:
    """Start the local MCP streamable HTTP server."""
    args = parse_args(argv)
    server = create_server(
        host=args.host,
        port=args.port,
        mount_path=_normalize_mount_path(args.mount_path),
    )
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()

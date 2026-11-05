# Copyright (c) Microsoft. All rights reserved.

"""MCP tool handlers for declarative workflows.

The default handler owns a separate MCP protocol session for each invocation.
Custom handlers may implement explicitly scoped session continuity or additional
transport policy. Neither the default handler nor this protocol filters URLs:
hosts must enforce their own destination allowlists and trust the MCP servers
whose outputs enter workflow conversations.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

import httpx2 as httpx

if TYPE_CHECKING:
    from agent_framework import Content, MCPStreamableHTTPTool

__all__ = [
    "ClientProvider",
    "DefaultMCPToolHandler",
    "MCPToolHandler",
    "MCPToolInvocation",
    "MCPToolResult",
]

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInvocation:
    """Evaluated input for an MCP tool call.

    ``server_url`` identifies the server and ``server_label`` names its client.
    ``tool_name`` is either a remote tool or the reserved ``tools/list`` operation.
    ``arguments`` contains JSON-serialisable tool arguments; ``headers`` contains
    evaluated outbound headers. ``connection_name`` is available to custom
    handlers and client providers that resolve host-owned connections.
    """

    server_url: str
    tool_name: str
    server_label: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]
    headers: dict[str, str] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]
    connection_name: str | None = None


@dataclass
class MCPToolResult:
    """Parsed MCP output, or an error that the workflow can store in its result."""

    outputs: list[Content] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    is_error: bool = False
    error_message: str | None = None


@runtime_checkable
class MCPToolHandler(Protocol):
    """Transport contract for declarative ``InvokeMcpTool`` actions.

    Implementations must support concurrent calls from independent workflows.
    They own destination validation, authentication, retries, and any explicitly
    scoped protocol-session continuity. Lifecycle methods are not part of this
    protocol.
    """

    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult:
        """Return tool output or a transport/tool error; propagate programming errors."""
        ...


ClientProvider = Callable[[MCPToolInvocation], Awaitable["httpx.AsyncClient | None"]]


class DefaultMCPToolHandler:
    """Invoke MCP tools with a separate protocol client for every call.

    Every invocation, including ``tools/list``, connects and closes its own
    :class:`agent_framework.MCPStreamableHTTPTool`. No initialized clients,
    session state, credentials, or discovery inventories are cached here.

    The optional ``client_provider`` is called for every invocation. Its HTTP
    client is borrowed and never closed by this handler, so the host may reuse
    HTTP connection pools without sharing MCP sessions. Returning ``None`` uses
    an internally owned HTTP client that is closed with the invocation.

    The handler owns no shared disposable resources and has no shutdown method.
    Hosts must cancel and await active invocations before closing borrowed HTTP
    clients. Admission limits and invocation deadlines are also host-owned.
    Implicit server-side state does not survive later calls, approval waits, or
    checkpoint resumes. Use a custom scoped handler or explicit remote state
    handles when continuity is required.

    This handler performs no URL filtering or SSRF protection.

    Keyword Args:
        client_provider: Optional per-invocation provider of a borrowed HTTP client.
        max_discovery_pages: Maximum pages accepted per tool catalog fetch.
            Defaults to 100; ``None`` disables the limit.
        max_discovery_items: Maximum tools accepted per tool catalog fetch.
            Defaults to 1,000; ``None`` disables the limit.
    """

    LIST_TOOLS_TOOL_NAME: ClassVar[str] = "tools/list"
    """Reserved operation returning a JSON catalog with a ``tools`` array.

    Each item contains ``name``, ``description``, ``inputSchema``, and
    ``outputSchema`` in that order. The catalog is paginated within one
    invocation, not retained for subsequent calls.
    """

    def __init__(
        self,
        *,
        client_provider: ClientProvider | None = None,
        max_discovery_pages: int | None = 100,
        max_discovery_items: int | None = 1_000,
    ) -> None:
        if max_discovery_pages is not None and max_discovery_pages <= 0:
            raise ValueError("max_discovery_pages must be positive or None.")
        if max_discovery_items is not None and max_discovery_items <= 0:
            raise ValueError("max_discovery_items must be positive or None.")
        self._client_provider = client_provider
        self._max_discovery_pages = max_discovery_pages
        self._max_discovery_items = max_discovery_items

    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult:
        """Connect, dispatch, and finish protocol cleanup before returning."""
        from agent_framework import Content, MCPStreamableHTTPTool

        if invocation.tool_name == self.LIST_TOOLS_TOOL_NAME and invocation.arguments:
            message = f"The reserved MCP '{self.LIST_TOOLS_TOOL_NAME}' operation does not accept tool arguments."
            raise ValueError(message)

        tool: MCPStreamableHTTPTool | None = None
        try:
            try:
                client = await self._client_provider(invocation) if self._client_provider is not None else None
                tool = MCPStreamableHTTPTool(
                    name=invocation.server_label or "McpClient",
                    url=invocation.server_url,
                    load_prompts=False,
                    http_client=client,
                    static_headers=dict(invocation.headers),
                    max_discovery_pages=self._max_discovery_pages,
                    max_discovery_items=self._max_discovery_items,
                )
                await tool.connect()
            except Exception as exc:
                logger.warning(
                    "DefaultMCPToolHandler: failed to obtain MCP client for url=%s tool=%s: %s",
                    invocation.server_url,
                    invocation.tool_name,
                    exc,
                )
                message = f"Failed to connect to MCP server: {type(exc).__name__}: {exc}".rstrip(": ")
                return MCPToolResult(
                    outputs=[Content.from_text(f"Error: {message}")], is_error=True, error_message=message
                )
            return await self._invoke_connected_tool(tool, invocation)
        finally:
            if tool is not None:
                await self._close_tool(tool)

    async def _invoke_connected_tool(self, tool: MCPStreamableHTTPTool, invocation: MCPToolInvocation) -> MCPToolResult:
        from agent_framework import Content
        from agent_framework.exceptions import ToolExecutionException

        try:
            if invocation.tool_name == self.LIST_TOOLS_TOOL_NAME:
                return await self._invoke_list_tools(tool)
            raw = await tool.call_tool(invocation.tool_name, **invocation.arguments)
        except ToolExecutionException as exc:
            logger.info(
                "DefaultMCPToolHandler: tool '%s' on '%s' raised ToolExecutionException",
                invocation.tool_name,
                invocation.server_url,
            )
            message = str(exc) or type(exc).__name__
            return MCPToolResult(outputs=[Content.from_text(f"Error: {message}")], is_error=True, error_message=message)
        except httpx.HTTPError as exc:
            message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            return MCPToolResult(outputs=[Content.from_text(f"Error: {message}")], is_error=True, error_message=message)
        except Exception as exc:
            from mcp.shared.exceptions import MCPError

            if isinstance(exc, MCPError):
                message = str(exc) or type(exc).__name__
                return MCPToolResult(
                    outputs=[Content.from_text(f"Error: {message}")], is_error=True, error_message=message
                )
            raise

        outputs = [Content.from_text(raw)] if isinstance(raw, str) else list(raw)
        return MCPToolResult(outputs=outputs)

    @staticmethod
    async def _invoke_list_tools(tool: MCPStreamableHTTPTool) -> MCPToolResult:
        """Preserve the catalog shape and pagination used by workflow expressions."""
        from agent_framework import Content
        from mcp import types as mcp_types

        require_connection: Any = getattr(tool, "_require_connection", None)
        connection: Any | None = None
        session: Any | None = None
        if callable(require_connection):
            with contextlib.suppress(RuntimeError):
                connection = require_connection()
        else:
            session = getattr(tool, "session", None)

        if connection is None and session is None:
            message = "MCP session is not connected; cannot list tools."
            return MCPToolResult(outputs=[Content.from_text(f"Error: {message}")], is_error=True, error_message=message)

        collected: list[Any] = []
        params: mcp_types.PaginatedRequestParams | None = None
        while True:
            if connection is not None:
                tool_list = await connection.list_tools_page(params)
            elif session is not None:
                tool_list = await session.list_tools(params=params)
            else:  # pragma: no cover - guarded before entering the loop
                raise RuntimeError("MCP connection became unavailable while listing tools.")
            collected.extend(tool_list.tools)
            next_cursor = getattr(tool_list, "next_cursor", getattr(tool_list, "nextCursor", None))
            if not next_cursor:
                break
            params = mcp_types.PaginatedRequestParams(cursor=next_cursor)

        payload = {
            "tools": [
                {
                    "name": item.name,
                    "description": item.description,
                    "inputSchema": getattr(item, "input_schema", getattr(item, "inputSchema", None)),
                    "outputSchema": getattr(item, "output_schema", getattr(item, "outputSchema", None)),
                }
                for item in collected
            ]
        }
        return MCPToolResult(outputs=[Content.from_text(json.dumps(payload, indent=2, allow_nan=False))])

    @staticmethod
    async def _close_tool(tool: MCPStreamableHTTPTool) -> None:
        # The tool owns its SDK lifecycle task and any internally allocated HTTP client.
        cleanup = asyncio.create_task(tool.close())
        cancelled = False
        try:
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup.result()
        except Exception:
            logger.warning("DefaultMCPToolHandler: error closing invocation MCP client", exc_info=True)
        if cancelled:
            raise asyncio.CancelledError

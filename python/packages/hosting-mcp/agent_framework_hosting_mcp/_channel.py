# Copyright (c) Microsoft. All rights reserved.

"""``MCPChannel`` — exposes the hosted target as a Model Context Protocol tool.

Mounts a Streamable-HTTP MCP endpoint that advertises a single tool. An MCP
client (another agent, an IDE, tooling) calls the tool with
``{"input": "...", "session_id": "..."}`` and receives the target's reply as
the tool result.

Like the other ``agent-framework-hosting`` channels this routes through the
host pipeline (``ChannelContext.run`` / ``run_stream``) so session resolution,
request metadata, and run/response hooks all apply. The MCP ``tool/call``
conversation key maps onto :class:`ChannelSession` (caller-supplied-session
family); the same single-tool shape works for an ``Agent`` or a ``Workflow``
target (use a ``run_hook`` to reshape the free-form input into a workflow's
typed inputs).
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any

import mcp.types as types
from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelIdentity,
    ChannelRequest,
    ChannelResponseHook,
    ChannelRunHook,
    ChannelSession,
    HostedRunResult,
    logger,
)
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

_DEFAULT_TOOL_NAME = "run_agent"
_DEFAULT_TOOL_DESCRIPTION = (
    "Invoke the hosted agent (or workflow) with a free-form text request and "
    "return its reply. Pass an optional ``session_id`` to continue a prior "
    "conversation."
)


class MCPChannel:
    """Exposes the hosted target as a single MCP tool over Streamable HTTP.

    Mounts the MCP Streamable-HTTP transport at ``path`` (default ``/mcp``).
    The advertised tool accepts ``{"input": str, "session_id": str?}`` and
    returns the target's textual reply as MCP ``TextContent``. Non-text
    content produced by the target is logged and dropped (mirroring
    :meth:`agent_framework.Agent.as_mcp_server`).
    """

    name = "mcp"

    def __init__(
        self,
        *,
        path: str = "/mcp",
        tool_name: str = _DEFAULT_TOOL_NAME,
        tool_description: str = _DEFAULT_TOOL_DESCRIPTION,
        server_name: str = "agent-framework-hosting",
        server_version: str | None = None,
        streaming: bool = True,
        json_response: bool = False,
        stateless: bool = False,
        run_hook: ChannelRunHook | None = None,
        response_hook: ChannelResponseHook | None = None,
    ) -> None:
        """Create an MCP tool channel.

        Keyword Args:
            path: Mount path for the Streamable-HTTP transport. Default ``/mcp``.
            tool_name: Name of the advertised tool. Default ``run_agent``.
            tool_description: Human-readable description advertised to clients.
            server_name: MCP server name reported in the initialize handshake.
            server_version: Optional MCP server version string.
            streaming: When ``True`` (default) the channel consumes the target
                via :meth:`ChannelContext.run_stream` and forwards incremental
                text to the client as MCP progress notifications (when the
                client supplied a ``progressToken``). The full reply is always
                returned as the tool result regardless of this flag.
            json_response: Forwarded to :class:`StreamableHTTPSessionManager`.
                When ``True`` the transport returns a single JSON response
                instead of an SSE stream for each request.
            stateless: Forwarded to :class:`StreamableHTTPSessionManager`. When
                ``True`` the transport does not retain per-session state between
                requests.
            run_hook: Optional :data:`ChannelRunHook` invoked with the parsed
                :class:`ChannelRequest` before the target runs.
            response_hook: Optional :data:`ChannelResponseHook` invoked before
                the channel serializes an originating reply into tool content.
        """
        self.path = path
        self.response_hook = response_hook
        self._tool_name = tool_name
        self._tool_description = tool_description
        self._server_name = server_name
        self._server_version = server_version
        self._streaming = streaming
        self._json_response = json_response
        self._stateless = stateless
        self._hook = run_hook
        self._ctx: ChannelContext | None = None
        self._server: Server[Any, Any] | None = None
        self._session_manager: StreamableHTTPSessionManager | None = None
        self._run_cm: AbstractAsyncContextManager[None] | None = None

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Capture the host context and mount the Streamable-HTTP transport."""
        self._ctx = context
        self._server = self._build_server()
        self._session_manager = StreamableHTTPSessionManager(
            app=self._server,
            json_response=self._json_response,
            stateless=self._stateless,
        )
        return ChannelContribution(
            routes=[Mount(self.path, app=self._handle_asgi)],
            on_startup=[self._on_startup],
            on_shutdown=[self._on_shutdown],
        )

    async def _handle_asgi(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entrypoint delegating to the MCP Streamable-HTTP session manager."""
        if self._session_manager is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("MCPChannel transport not initialized")
        await self._session_manager.handle_request(scope, receive, send)

    async def _on_startup(self) -> None:
        """Enter the session-manager task-group lifecycle on host startup."""
        if self._session_manager is None:  # pragma: no cover - guarded by lifecycle
            return
        self._run_cm = self._session_manager.run()
        await self._run_cm.__aenter__()

    async def _on_shutdown(self) -> None:
        """Exit the session-manager task-group lifecycle on host shutdown."""
        if self._run_cm is not None:
            await self._run_cm.__aexit__(None, None, None)
            self._run_cm = None

    def _build_server(self) -> Server[Any, Any]:
        """Build the low-level MCP server with the single host-routed tool."""
        server: Server[Any, Any] = Server(name=self._server_name, version=self._server_version)
        tool = types.Tool(
            name=self._tool_name,
            description=self._tool_description,
            inputSchema={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "The request to send to the hosted agent or workflow.",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional conversation id to continue a prior session.",
                    },
                },
                "required": ["input"],
            },
        )

        @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator, misc]
        async def _list_tools() -> list[types.Tool]:  # noqa: RUF029  # pyright: ignore[reportUnusedFunction]
            return [tool]

        @server.call_tool()  # type: ignore[no-untyped-call, untyped-decorator, misc]
        async def _call_tool(name: str, arguments: Mapping[str, Any]) -> list[types.ContentBlock]:  # pyright: ignore[reportUnusedFunction]
            return await self._invoke_tool(arguments)

        return server

    async def _invoke_tool(self, arguments: Mapping[str, Any]) -> list[types.ContentBlock]:
        """Route a single ``tool/call`` through the host pipeline."""
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            raise RuntimeError("MCPChannel not initialized")

        text_input = arguments.get("input")
        if not isinstance(text_input, str) or not text_input:
            return [types.TextContent(type="text", text="Error: 'input' must be a non-empty string.")]
        session_id = arguments.get("session_id")
        session = ChannelSession(isolation_key=session_id) if isinstance(session_id, str) and session_id else None
        identity = (
            ChannelIdentity(channel=self.name, native_id=session_id)
            if isinstance(session_id, str) and session_id
            else None
        )

        channel_request = ChannelRequest(
            channel=self.name,
            operation="message.create",
            input=text_input,
            session=session,
            stream=self._streaming,
            identity=identity,
            attributes={"tool_name": self._tool_name},
        )

        if channel_request.stream:
            result = await self._run_streaming(channel_request, protocol_request=dict(arguments))
        else:
            result = await self._ctx.run(
                channel_request,
                run_hook=self._hook,
                protocol_request=dict(arguments),
                response_hook=self.response_hook,
                channel_name=self.name,
            )

        return self._result_to_content(result)

    async def _run_streaming(
        self, request: ChannelRequest, *, protocol_request: Mapping[str, Any]
    ) -> HostedRunResult[Any]:
        """Consume the target as a stream, forwarding progress, returning the full reply."""
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            raise RuntimeError("MCPChannel not initialized")

        progress_token, request_id = self._progress_context()
        progress = 0.0
        stream = await self._ctx.run_stream(
            request,
            run_hook=self._hook,
            protocol_request=protocol_request,
            response_hook=self.response_hook,
            channel_name=self.name,
        )
        async for update in stream:
            chunk = getattr(update, "text", None)
            if not chunk:
                continue
            if progress_token is not None:
                progress += 1.0
                try:
                    await self._send_progress(progress_token, progress, chunk, request_id)
                except Exception:  # pragma: no cover - progress is best-effort
                    logger.exception("MCPChannel progress notification failed")
        return HostedRunResult(await stream.get_final_response())

    def _progress_context(self) -> tuple[str | int | None, str | None]:
        """Best-effort lookup of the active request's progress token + id."""
        if self._server is None:  # pragma: no cover - guarded by lifecycle
            return None, None
        try:
            ctx = self._server.request_context
        except Exception:  # pragma: no cover - no active request context
            return None, None
        token = ctx.meta.progressToken if ctx.meta is not None else None
        request_id = str(ctx.request_id)
        return token, request_id

    async def _send_progress(
        self,
        progress_token: str | int,
        progress: float,
        message: str,
        request_id: str | None,
    ) -> None:
        """Send a single MCP progress notification for streamed text."""
        if self._server is None:  # pragma: no cover - guarded by lifecycle
            return
        await self._server.request_context.session.send_progress_notification(
            progress_token=progress_token,
            progress=progress,
            message=message,
            related_request_id=request_id,
        )

    def _result_to_content(self, result: HostedRunResult[Any]) -> list[types.ContentBlock]:
        """Convert a host result into MCP tool content (text only)."""
        text = getattr(result.result, "text", None)
        if not isinstance(text, str):
            text = ""
        return [types.TextContent(type="text", text=text)]

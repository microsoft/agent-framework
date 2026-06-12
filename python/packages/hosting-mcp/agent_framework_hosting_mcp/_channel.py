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

import base64
import json
import re
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, is_dataclass
from typing import Any, cast

import mcp.types as types
from agent_framework import Content, Message
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
from pydantic import AnyUrl
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

_DEFAULT_TOOL_NAME = "run_agent"
_DEFAULT_TOOL_DESCRIPTION = (
    "Invoke the hosted agent (or workflow) with a free-form text request and "
    "return its reply. Pass an optional ``session_id`` to continue a prior "
    "conversation."
)
_DATA_URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<data>[A-Za-z0-9+/=]+)$")


def _mcp_uri(uri: str) -> AnyUrl:
    """Build an MCP URI model from a string URI."""
    return AnyUrl(uri)


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable representation for MCP structured content."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


def _structured_content(value: Any) -> dict[str, Any] | None:
    """Normalize an Agent Framework structured output value for MCP."""
    if value is None:
        return None

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        value = model_dump(mode="json")
    elif is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)

    if isinstance(value, Mapping):
        mapping_value = cast("Mapping[Any, Any]", value)  # type: ignore[redundant-cast]
        safe_value = _json_safe(dict(mapping_value))
        if isinstance(safe_value, dict):
            safe_mapping = cast("Mapping[Any, Any]", safe_value)
            return {str(key): item for key, item in safe_mapping.items()}
        return {"value": safe_value}
    safe_value = _json_safe(value)
    return {"value": safe_value}


def _data_content_to_mcp(content: Content) -> list[types.ContentBlock]:
    """Convert Agent Framework data content into the closest MCP content block."""
    if not content.uri:
        return []
    match = _DATA_URI_PATTERN.match(content.uri)
    if match is None:
        logger.warning("MCPChannel could not parse data URI; omitted.")
        return []

    media_type = content.media_type or match.group("media_type")
    data = match.group("data")
    if media_type.startswith("image/"):
        return [types.ImageContent(type="image", data=data, mimeType=media_type)]
    if media_type.startswith("audio/"):
        return [types.AudioContent(type="audio", data=data, mimeType=media_type)]
    return [
        types.EmbeddedResource(
            type="resource",
            resource=types.BlobResourceContents(uri=_mcp_uri(content.uri), mimeType=media_type, blob=data),
        )
    ]


def _content_to_mcp(content: Content) -> list[types.ContentBlock]:
    """Convert one Agent Framework content item into MCP content blocks."""
    match content.type:
        case "text":
            return [types.TextContent(type="text", text=content.text or "")]
        case "text_reasoning":
            return [types.TextContent(type="text", text=content.text)] if content.text else []
        case "data":
            return _data_content_to_mcp(content)
        case "uri":
            if not content.uri:
                return []
            block: types.ContentBlock = types.ResourceLink(
                type="resource_link",
                name=content.uri,
                uri=_mcp_uri(content.uri),
                mimeType=content.media_type,
            )
            return [block]
        case "function_result":
            if content.items:
                blocks: list[types.ContentBlock] = []
                for item in content.items:
                    blocks.extend(_content_to_mcp(item))
                return blocks
            return [types.TextContent(type="text", text=str(content.result or ""))]
        case "error":
            return [types.TextContent(type="text", text=content.message or content.error_details or "")]
        case _:
            logger.warning("MCPChannel does not support content type: %s. Omitted.", content.type)
            return []


def _value_to_mcp(value: Any) -> list[types.ContentBlock]:
    """Convert a workflow output or fallback value into MCP content blocks."""
    if isinstance(value, Content):
        return _content_to_mcp(value)
    if isinstance(value, Message):
        blocks: list[types.ContentBlock] = []
        for content in value.contents:
            blocks.extend(_content_to_mcp(content))
        return blocks
    if isinstance(value, str):
        return [types.TextContent(type="text", text=value)]
    if isinstance(value, bytes):
        data = base64.b64encode(value).decode("utf-8")
        return [
            types.EmbeddedResource(
                type="resource",
                resource=types.BlobResourceContents(
                    uri=_mcp_uri("data:application/octet-stream;base64," + data),
                    mimeType="application/octet-stream",
                    blob=data,
                ),
            )
        ]
    return [types.TextContent(type="text", text=json.dumps(_json_safe(value), default=str))]


class MCPChannel:
    """Exposes the hosted target as a single MCP tool over Streamable HTTP.

    Mounts the MCP Streamable-HTTP transport at ``path`` (default ``/mcp``).
    The advertised tool accepts ``{"input": str, "session_id": str?}`` and
    returns the target's reply as MCP content blocks. Agent structured outputs
    are returned as MCP ``structuredContent``.
    """

    name = "mcp"

    def __init__(
        self,
        *,
        path: str = "/mcp",
        tool_name: str = _DEFAULT_TOOL_NAME,
        tool_description: str = _DEFAULT_TOOL_DESCRIPTION,
        server_name: str | None = None,
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
                Defaults to the hosted target's ``name`` attribute when available.
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
        # StreamableHTTPSessionManager owns MCP initialize/session/progress semantics;
        # mounting it keeps the channel on the real MCP HTTP transport.
        return ChannelContribution(
            routes=[Mount("/", app=self._handle_asgi)],
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
        target_name = getattr(self._ctx.target, "name", None) if self._ctx is not None else None
        server_name = self._server_name or (target_name if isinstance(target_name, str) and target_name else None)
        server: Server[Any, Any] = Server(name=server_name or "agent-framework-hosting", version=self._server_version)
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
        async def _call_tool(name: str, arguments: Mapping[str, Any]) -> types.CallToolResult:  # pyright: ignore[reportUnusedFunction]
            return await self._invoke_tool(arguments)

        return server

    async def _invoke_tool(self, arguments: Mapping[str, Any]) -> types.CallToolResult:
        """Route a single ``tool/call`` through the host pipeline."""
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            raise RuntimeError("MCPChannel not initialized")

        text_input = arguments.get("input")
        if not isinstance(text_input, str) or not text_input:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text="Error: 'input' must be a non-empty string.")],
                isError=True,
            )
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

    def _result_to_content(self, result: HostedRunResult[Any]) -> types.CallToolResult:
        """Convert a host result into an MCP tool result."""
        response = result.result
        content: list[types.ContentBlock] = []

        messages = cast("Sequence[Any] | None", getattr(response, "messages", None))
        if messages:
            for message in messages:
                for item in cast("Sequence[Any]", getattr(message, "contents", None) or ()):
                    if isinstance(item, Content):
                        content.extend(_content_to_mcp(item))
                    else:
                        content.append(types.TextContent(type="text", text=str(item)))

        get_outputs = getattr(response, "get_outputs", None)
        if callable(get_outputs):
            for output in cast("Sequence[Any]", get_outputs()):
                content.extend(_value_to_mcp(output))

        structured = _structured_content(getattr(response, "value", None))
        if not content:
            text = getattr(response, "text", None)
            if isinstance(text, str) and text:
                content.append(types.TextContent(type="text", text=text))
            elif structured is not None:
                content.append(types.TextContent(type="text", text=json.dumps(structured, indent=2)))
            else:
                content.append(types.TextContent(type="text", text=""))

        return types.CallToolResult(content=content, structuredContent=structured, isError=False)

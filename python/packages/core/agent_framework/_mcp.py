# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import contextvars
import json
import logging
import re
import sys
from abc import abstractmethod
from collections.abc import Callable, Collection, Sequence
from contextlib import AsyncExitStack, _AsyncGeneratorContextManager  # type: ignore
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from opentelemetry import propagate

from ._tools import FunctionTool
from ._types import (
    ChatOptions,
    Content,
    Message,
)
from .exceptions import ToolException, ToolExecutionException

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from httpx import AsyncClient
    from mcp import types
    from mcp.client.session import ClientSession
    from mcp.shared.context import RequestContext
    from mcp.shared.session import RequestResponder

    from ._clients import SupportsChatGetResponse
    from ._middleware import FunctionInvocationContext


logger = logging.getLogger(__name__)


class MCPSpecificApproval(TypedDict, total=False):
    """Represents the specific approval mode for an MCP tool.

    When using this mode, the user must specify which tools always or never require approval.

    Attributes:
        always_require_approval: A sequence of tool names that always require approval.
        never_require_approval: A sequence of tool names that never require approval.
    """

    always_require_approval: Collection[str] | None
    never_require_approval: Collection[str] | None


_MCP_REMOTE_NAME_KEY = "_mcp_remote_name"
_MCP_NORMALIZED_NAME_KEY = "_mcp_normalized_name"
_mcp_call_headers: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar("_mcp_call_headers")
MCP_DEFAULT_TIMEOUT = 30
MCP_DEFAULT_SSE_READ_TIMEOUT = 60 * 5

# region: Helpers

LOG_LEVEL_MAPPING: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}


def _get_input_model_from_mcp_prompt(prompt: types.Prompt) -> dict[str, Any]:
    """Get the input model from an MCP prompt.

    Returns a JSON schema dictionary for prompt arguments.
    """
    # Check if 'arguments' is missing or empty
    if not prompt.arguments:
        return {"type": "object", "properties": {}}

    # Convert prompt arguments to JSON schema format
    properties: dict[str, Any] = {}
    required: list[str] = []

    for prompt_argument in prompt.arguments:
        # For prompts, all arguments are typically string type unless specified otherwise
        properties[prompt_argument.name] = {
            "type": "string",
            "description": prompt_argument.description if hasattr(prompt_argument, "description") else "",
        }
        if prompt_argument.required:
            required.append(prompt_argument.name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _normalize_mcp_name(name: str) -> str:
    """Normalize MCP tool/prompt names to allowed identifier pattern (A-Za-z0-9_.-)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name)


def _build_prefixed_mcp_name(
    normalized_name: str,
    tool_name_prefix: str | None,
) -> str:
    """Build the exposed MCP function name from a normalized name and optional prefix."""
    if not tool_name_prefix:
        return normalized_name
    normalized_prefix = _normalize_mcp_name(tool_name_prefix).rstrip("_.-")
    if not normalized_prefix:
        return normalized_name
    trimmed_name = normalized_name.lstrip("_.-")
    return f"{normalized_prefix}_{trimmed_name}" if trimmed_name else normalized_prefix


def _inject_otel_into_mcp_meta(meta: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Inject OpenTelemetry trace context into MCP request _meta via the global propagator(s)."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    if not carrier:
        return meta

    if meta is None:
        meta = {}
    for key, value in carrier.items():
        if key not in meta:
            meta[key] = value

    return meta


def streamable_http_client(*args: Any, **kwargs: Any) -> _AsyncGeneratorContextManager[Any, None]:
    """Lazily import the MCP streamable HTTP transport."""
    try:
        from mcp.client.streamable_http import streamable_http_client as _streamable_http_client
    except ModuleNotFoundError as ex:
        missing_name = ex.name or str(ex)
        if missing_name == "mcp" or missing_name.startswith("mcp.") or "mcp" in missing_name:
            raise ModuleNotFoundError("`MCPStreamableHTTPTool` requires `mcp`. Please install `mcp`.") from ex
        raise ModuleNotFoundError(
            f"`MCPStreamableHTTPTool` requires streamable HTTP transport support. "
            f"The optional dependency `{missing_name}` is not installed. Please update your dependencies."
        ) from ex

    return _streamable_http_client(*args, **kwargs)  # type: ignore[return-value]


# region: MCP Plugin


class MCPTool:
    """Main MCP class for connecting to Model Context Protocol servers.

    This is the base class for MCP tool implementations. It handles connection management,
    tool and prompt loading, and communication with MCP servers.

    Note:
        MCPTool cannot be instantiated directly. Use one of the subclasses:
        MCPStdioTool, MCPStreamableHTTPTool, or MCPWebsocketTool.

    Examples:
        See the subclass documentation for usage examples:

        - :class:`MCPStdioTool` for stdio-based MCP servers
        - :class:`MCPStreamableHTTPTool` for HTTP-based MCP servers
        - :class:`MCPWebsocketTool` for WebSocket-based MCP servers
    """

    def __init__(
        self,
        name: str,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        session: ClientSession | None = None,
        request_timeout: int | None = None,
        client: SupportsChatGetResponse | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the MCP Tool base.

        Note:
            Do not use this method, use one of the subclasses: MCPStreamableHTTPTool, MCPWebsocketTool
            or MCPStdioTool.

        Args:
            name: The name of the MCP tool.
            description: A description of the MCP tool.
            approval_mode: Whether approval is required to run tools.
            allowed_tools: A collection of tool names to allow.
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
            access the ``.functions`` list after connecting and set ``result_parser`` on
            individual ``FunctionTool`` instances.
            session: An existing MCP client session to use.
            request_timeout: Timeout in seconds for MCP requests.
            client: A chat client for sampling callbacks.
            additional_properties: Additional properties for the tool.
        """
        self.name = name
        self.description = description or ""
        self.approval_mode = approval_mode
        self.allowed_tools = allowed_tools
        self.tool_name_prefix = _normalize_mcp_name(tool_name_prefix).rstrip("_.-") if tool_name_prefix else None
        self.additional_properties = additional_properties
        self.load_tools_flag = load_tools
        self.parse_tool_results = parse_tool_results
        self.load_prompts_flag = load_prompts
        self.parse_prompt_results = parse_prompt_results
        self._exit_stack = AsyncExitStack()
        self._lifecycle_lock = asyncio.Lock()
        self._lifecycle_request_lock = asyncio.Lock()
        self._lifecycle_queue: asyncio.Queue[tuple[str, bool, asyncio.Future[None]]] | None = None
        self._lifecycle_owner_task: asyncio.Task[None] | None = None
        self.session = session
        self.request_timeout = request_timeout
        self.client = client
        self._functions: list[FunctionTool] = []
        self.is_connected: bool = False
        self._tools_loaded: bool = False
        self._prompts_loaded: bool = False

    def __str__(self) -> str:
        return f"MCPTool(name={self.name}, description={self.description})"

    def _parse_prompt_result_from_mcp(
        self,
        mcp_type: types.GetPromptResult,
    ) -> str:
        """Parse an MCP GetPromptResult directly into a string representation."""
        from mcp import types

        parts: list[str] = []
        for message in mcp_type.messages:
            content = message.content
            if isinstance(content, types.TextContent):
                parts.append(content.text)
            elif isinstance(content, (types.ImageContent, types.AudioContent)):
                parts.append(
                    json.dumps(
                        {
                            "type": "image" if isinstance(content, types.ImageContent) else "audio",
                            "data": content.data,
                            "mimeType": content.mimeType,
                        },
                        default=str,
                    )
                )
            elif isinstance(content, types.EmbeddedResource):
                match content.resource:
                    case types.TextResourceContents():
                        parts.append(content.resource.text)
                    case types.BlobResourceContents():
                        parts.append(
                            json.dumps(
                                {
                                    "type": "blob",
                                    "data": content.resource.blob,
                                    "mimeType": content.resource.mimeType,
                                },
                                default=str,
                            )
                        )
            else:
                parts.append(str(content))
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        return json.dumps(parts, default=str)

    def _parse_message_from_mcp(
        self,
        mcp_type: types.PromptMessage | types.SamplingMessage,
    ) -> Message:
        """Parse an MCP container type into an Agent Framework type."""
        return Message(
            role=mcp_type.role,
            contents=self._parse_content_from_mcp(mcp_type.content),
            raw_representation=mcp_type,
        )

    def _parse_tool_result_from_mcp(
        self,
        mcp_type: types.CallToolResult,
    ) -> list[Content]:
        """Parse an MCP CallToolResult into a list of Content items."""
        from mcp import types

        result: list[Content] = []
        for item in mcp_type.content:
            match item:
                case types.TextContent():
                    result.append(Content.from_text(item.text))
                case types.ImageContent() | types.AudioContent():
                    decoded = base64.b64decode(item.data)
                    result.append(
                        Content.from_data(
                            data=decoded,
                            media_type=item.mimeType,
                        )
                    )
                case types.ResourceLink():
                    result.append(
                        Content.from_uri(
                            uri=str(item.uri),
                            media_type=item.mimeType,
                        )
                    )
                case types.EmbeddedResource():
                    match item.resource:
                        case types.TextResourceContents():
                            result.append(Content.from_text(item.resource.text))
                        case types.BlobResourceContents():
                            blob = item.resource.blob
                            mime = item.resource.mimeType or "application/octet-stream"
                            if not blob.startswith("data:"):
                                blob = f"data:{mime};base64,{blob}"
                            result.append(
                                Content.from_uri(
                                    uri=blob,
                                    media_type=mime,
                                )
                            )
                case _:
                    result.append(Content.from_text(str(item)))

        if not result:
            result.append(Content.from_text("null"))
        return result

    def _parse_content_from_mcp(
        self,
        mcp_type: types.ImageContent
        | types.TextContent
        | types.AudioContent
        | types.EmbeddedResource
        | types.ResourceLink
        | types.ToolUseContent
        | types.ToolResultContent
        | Sequence[
            types.ImageContent
            | types.TextContent
            | types.AudioContent
            | types.EmbeddedResource
            | types.ResourceLink
            | types.ToolUseContent
            | types.ToolResultContent
        ],
    ) -> list[Content]:
        """Parse an MCP type into an Agent Framework type."""
        from mcp import types

        mcp_content_types: Sequence[Any] = (
            cast(Sequence[Any], mcp_type) if isinstance(mcp_type, Sequence) else [mcp_type]
        )  # type: ignore[redundant-cast]
        return_types: list[Content] = []
        for mcp_type in mcp_content_types:
            match mcp_type:
                case types.TextContent():
                    return_types.append(Content.from_text(text=mcp_type.text, raw_representation=mcp_type))
                case types.ImageContent() | types.AudioContent():
                    data_bytes = base64.b64decode(mcp_type.data) if isinstance(mcp_type.data, str) else mcp_type.data
                    return_types.append(
                        Content.from_data(
                            data=data_bytes,
                            media_type=mcp_type.mimeType,
                            raw_representation=mcp_type,
                        )
                    )
                case types.ResourceLink():
                    return_types.append(
                        Content.from_uri(
                            uri=str(mcp_type.uri),
                            media_type=mcp_type.mimeType or "application/json",
                            raw_representation=mcp_type,
                        )
                    )
                case types.ToolUseContent():
                    return_types.append(
                        Content.from_function_call(
                            call_id=mcp_type.id,
                            name=mcp_type.name,
                            arguments=mcp_type.input,
                            raw_representation=mcp_type,
                        )
                    )
                case types.ToolResultContent():
                    return_types.append(
                        Content.from_function_result(
                            call_id=mcp_type.toolUseId,
                            result=self._parse_content_from_mcp(mcp_type.content)
                            if mcp_type.content
                            else mcp_type.structuredContent,
                            exception=str(Exception()) if mcp_type.isError else None,  # type: ignore[arg-type]
                            raw_representation=mcp_type,
                        )
                    )
                case types.EmbeddedResource():
                    match mcp_type.resource:
                        case types.TextResourceContents():
                            return_types.append(
                                Content.from_text(
                                    text=mcp_type.resource.text,
                                    raw_representation=mcp_type,
                                    additional_properties=(
                                        mcp_type.annotations.model_dump() if mcp_type.annotations else None
                                    ),
                                )
                            )
                        case types.BlobResourceContents():
                            return_types.append(
                                Content.from_uri(
                                    uri=mcp_type.resource.blob,
                                    media_type=mcp_type.resource.mimeType,
                                    raw_representation=mcp_type,
                                    additional_properties=(
                                        mcp_type.annotations.model_dump() if mcp_type.annotations else None
                                    ),
                                )
                            )
                case _:
                    pass
        return return_types

    def _prepare_content_for_mcp(
        self,
        content: Content,
    ) -> (
        types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink | None
    ):
        """Prepare an Agent Framework content type for MCP."""
        from mcp import types

        if content.type == "text":
            return types.TextContent(type="text", text=content.text)  # type: ignore[attr-defined]
        if content.type == "data":
            if content.media_type and content.media_type.startswith("image/"):  # type: ignore[attr-defined]
                return types.ImageContent(type="image", data=content.uri, mimeType=content.media_type)  # type: ignore[attr-defined]
            if content.media_type and content.media_type.startswith("audio/"):  # type: ignore[attr-defined]
                return types.AudioContent(type="audio", data=content.uri, mimeType=content.media_type)  # type: ignore[attr-defined]
            if content.media_type and content.media_type.startswith("application/"):  # type: ignore[attr-defined]
                return types.EmbeddedResource(
                    type="resource",
                    resource=types.BlobResourceContents(
                        blob=content.uri,  # type: ignore[attr-defined]
                        mimeType=content.media_type,  # type: ignore[attr-defined]
                        uri=(
                            content.additional_properties.get("uri", "af://binary")
                            if content.additional_properties
                            else "af://binary"
                        ),  # type: ignore[arg-type]
                    ),
                )
            return None
        if content.type == "uri":
            resource_name = (
                content.additional_properties.get("name", "Unknown") if content.additional_properties else "Unknown"
            )
            return types.ResourceLink(
                type="resource_link",
                uri=content.uri,  # type: ignore[arg-type,attr-defined]
                mimeType=content.media_type,  # type: ignore[attr-defined]
                name=resource_name,
            )
        return None

    def _prepare_message_for_mcp(
        self,
        content: Message,
    ) -> list[
        types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink
    ]:
        """Prepare a Message for MCP format."""
        messages: list[
            types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink
        ] = []
        for item in content.contents:
            mcp_content = self._prepare_content_for_mcp(item)
            if mcp_content:
                messages.append(mcp_content)
        return messages

    @property
    def functions(self) -> list[FunctionTool]:
        """Get the list of functions that are allowed."""
        if not self.allowed_tools:
            return self._functions
        allowed_names = set(self.allowed_tools)
        filtered_functions: list[FunctionTool] = []
        for func in self._functions:
            additional_properties = func.additional_properties or {}
            normalized_name = additional_properties.get(_MCP_NORMALIZED_NAME_KEY)
            remote_name = additional_properties.get(_MCP_REMOTE_NAME_KEY)
            if (
                func.name in allowed_names
                or (isinstance(normalized_name, str) and normalized_name in allowed_names)
                or (isinstance(remote_name, str) and remote_name in allowed_names)
            ):
                filtered_functions.append(func)
        return filtered_functions

    async def _ensure_lifecycle_owner(self) -> None:
        async with self._lifecycle_lock:
            if self._lifecycle_owner_task is not None and not self._lifecycle_owner_task.done():
                return

            self._lifecycle_queue = asyncio.Queue()
            self._lifecycle_owner_task = asyncio.create_task(
                self._run_lifecycle_owner(),
                name=f"mcp-lifecycle:{self.name}",
            )

    async def _run_lifecycle_owner(self) -> None:
        queue = self._lifecycle_queue
        if queue is None:
            return

        stop_error: BaseException | None = None
        try:
            while True:
                action, reset, future = await queue.get()

                try:
                    if action == "connect":
                        await self._connect_on_owner(reset=reset)
                    elif action == "close":
                        await self._close_on_owner()
                    else:
                        raise RuntimeError(f"Unknown MCP lifecycle action: {action}")
                except asyncio.CancelledError as ex:
                    stop_error = ex
                    if not future.done():
                        future.set_exception(ex)
                    raise
                except Exception as ex:
                    if not future.done():
                        future.set_exception(ex)
                else:
                    if not future.done():
                        future.set_result(None)

                if action == "close":
                    return
        except asyncio.CancelledError as ex:
            stop_error = ex
            raise
        finally:
            while True:
                try:
                    _, _, future = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not future.done():
                    future.set_exception(stop_error or RuntimeError("MCP lifecycle owner stopped unexpectedly."))

            self._lifecycle_queue = None
            self._lifecycle_owner_task = None

    def _is_lifecycle_owner_task(self) -> bool:
        owner_task = self._lifecycle_owner_task
        return owner_task is not None and asyncio.current_task() is owner_task

    async def _run_on_lifecycle_owner(self, action: str, *, reset: bool = False) -> None:
        await self._ensure_lifecycle_owner()

        if self._is_lifecycle_owner_task():
            if action == "connect":
                await self._connect_on_owner(reset=reset)
            elif action == "close":
                await self._close_on_owner()
            else:
                raise RuntimeError(f"Unknown MCP lifecycle action: {action}")
            return

        queue = self._lifecycle_queue
        if queue is None:
            raise RuntimeError("MCP lifecycle owner is not available.")

        future = asyncio.get_running_loop().create_future()
        await queue.put((action, reset, future))
        await future

    async def _safe_close_exit_stack(self) -> None:
        """Safely close the exit stack, handling unexpected cleanup failures."""
        try:
            await self._exit_stack.aclose()
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "cancel scope" in error_msg:
                logger.warning(
                    "Could not cleanly close MCP exit stack due to cancel scope error. "
                    "This indicates MCP lifecycle ownership was lost. Error: %s",
                    e,
                )
            else:
                raise
        except asyncio.CancelledError:
            logger.warning("Could not cleanly close MCP exit stack because the lifecycle owner task was cancelled.")

    async def connect(self, *, reset: bool = False) -> None:
        if self._is_lifecycle_owner_task():
            await self._connect_on_owner(reset=reset)
            return

        async with self._lifecycle_request_lock:
            await self._run_on_lifecycle_owner("connect", reset=reset)

    async def _connect_on_owner(self, *, reset: bool = False) -> None:
        """Connect to the MCP server.

        Establishes a connection to the MCP server, initializes the session,
        and loads tools and prompts if configured to do so.

        Keyword Args:
            reset: If True, forces a reconnection even if already connected.

        Raises:
            ToolException: If connection or session initialization fails.
        """
        if reset:
            await self._safe_close_exit_stack()
            self.session = None
            self.is_connected = False
            self._exit_stack = AsyncExitStack()
        if not self.session:
            try:
                transport = await self._exit_stack.enter_async_context(self.get_mcp_client())
            except Exception as ex:
                await self._safe_close_exit_stack()
                command = getattr(self, "command", None)
                if command:
                    error_msg = f"Failed to start MCP server '{command}': {ex}"
                else:
                    error_msg = f"Failed to connect to MCP server: {ex}"
                raise ToolException(error_msg, inner_exception=ex) from ex
            try:
                try:
                    from mcp import types
                    from mcp.client.session import ClientSession as runtime_client_session
                except ModuleNotFoundError as ex:
                    await self._safe_close_exit_stack()
                    raise ToolException(
                        "MCP support requires `mcp`. Please install `mcp`.",
                        inner_exception=ex,
                    ) from ex

                sampling_capabilities = None
                if self.client is not None:
                    sampling_capabilities = types.SamplingCapability(
                        tools=types.SamplingToolsCapability(),
                    )
                session = await self._exit_stack.enter_async_context(
                    runtime_client_session(
                        read_stream=transport[0],
                        write_stream=transport[1],
                        read_timeout_seconds=(
                            timedelta(seconds=self.request_timeout) if self.request_timeout else None
                        ),
                        message_handler=self.message_handler,
                        logging_callback=self.logging_callback,
                        sampling_callback=self.sampling_callback,
                        sampling_capabilities=sampling_capabilities,
                    )
                )
            except Exception as ex:
                await self._safe_close_exit_stack()
                raise ToolException(
                    message="Failed to create MCP session. Please check your configuration.",
                    inner_exception=ex,
                ) from ex
            try:
                await session.initialize()
            except Exception as ex:
                await self._safe_close_exit_stack()
                # Provide context about initialization failure
                command = getattr(self, "command", None)
                if command:
                    args_str = " ".join(getattr(self, "args", []))
                    full_command = f"{command} {args_str}".strip()
                    error_msg = f"MCP server '{full_command}' failed to initialize: {ex}"
                else:
                    error_msg = f"MCP server failed to initialize: {ex}"
                raise ToolException(error_msg, inner_exception=ex) from ex
            self.session = session
        elif self.session._request_id == 0:  # type: ignore[attr-defined]
            # If the session is not initialized, we need to reinitialize it
            await self.session.initialize()
        logger.debug("Connected to MCP server: %s", self.session)
        self.is_connected = True
        if self.load_tools_flag:
            await self.load_tools()
            self._tools_loaded = True
        if self.load_prompts_flag:
            await self.load_prompts()
            self._prompts_loaded = True

        if logger.level != logging.NOTSET:
            try:
                level_name = cast(
                    Any, next(level for level, value in LOG_LEVEL_MAPPING.items() if value == logger.level)
                )
                await self.session.set_logging_level(level_name)
            except Exception as exc:
                logger.warning("Failed to set log level to %s", logger.level, exc_info=exc)

    async def sampling_callback(
        self,
        context: RequestContext[ClientSession, Any],
        params: types.CreateMessageRequestParams,
    ) -> types.CreateMessageResult | types.ErrorData:
        """Callback function for sampling.

        This function is called when the MCP server needs to get a message completed.
        It uses the configured chat client to generate responses.

        Note:
            This is a simple version of this function. It can be overridden to allow
            more complex sampling. It gets added to the session at initialization time,
            so overriding it is the best way to customize this behavior.

        Args:
            context: The request context from the MCP server.
            params: The message creation request parameters.

        Returns:
            Either a CreateMessageResult with the generated message or ErrorData if generation fails.
        """
        from mcp import types

        if not self.client:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="No chat client available. Please set a chat client.",
            )
        logger.debug("Sampling callback called with params: %s", params)
        messages: list[Message] = []
        for msg in params.messages:
            messages.append(self._parse_message_from_mcp(msg))

        options: ChatOptions[None] = {}
        if params.systemPrompt is not None:
            options["instructions"] = params.systemPrompt
        if params.tools is not None:
            options["tools"] = [
                FunctionTool(
                    name=tool.name,
                    description=tool.description or "",
                    input_model=tool.inputSchema,
                )
                for tool in params.tools
            ]
        if params.toolChoice is not None and params.toolChoice.mode is not None:
            options["tool_choice"] = params.toolChoice.mode

        if params.temperature is not None:
            options["temperature"] = params.temperature
        options["max_tokens"] = params.maxTokens
        if params.stopSequences is not None:
            options["stop"] = params.stopSequences

        try:
            chat_client: Any = self.client
            response: Any = await chat_client.get_response(
                messages,
                options=options or None,
            )
        except Exception as ex:
            logger.debug("Sampling callback error: %s", ex, exc_info=True)
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message=f"Failed to get chat message content: {ex}",
            )
        if not response or not response.messages:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="Failed to get chat message content.",
            )
        mcp_contents = self._prepare_message_for_mcp(response.messages[0])
        # grab the first content that is of type TextContent or ImageContent
        mcp_content = next(
            (content for content in mcp_contents if isinstance(content, (types.TextContent, types.ImageContent))),
            None,
        )
        if not mcp_content:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="Failed to get right content types from the response.",
            )
        return types.CreateMessageResult(
            role="assistant",
            content=mcp_content,
            model=response.model_id or "unknown",
        )

    async def logging_callback(self, params: types.LoggingMessageNotificationParams) -> None:
        """Callback function for logging.

        This function is called when the MCP Server sends a log message.
        By default it will log the message to the logger with the level set in the params.

        Note:
            Subclass MCPTool and override this function if you want to adapt the behavior.

        Args:
            params: The logging message notification parameters from the MCP server.
        """
        logger.log(LOG_LEVEL_MAPPING[params.level], params.data)

    async def message_handler(
        self,
        message: (RequestResponder[types.ServerRequest, types.ClientResult] | types.ServerNotification | Exception),
    ) -> None:
        """Handle messages from the MCP server.

        By default this function will handle exceptions on the server by logging them,
        and it will trigger a reload of the tools and prompts when the list changed
        notification is received.

        Note:
            If you want to extend this behavior, you can subclass MCPTool and override
            this function. If you want to keep the default behavior, make sure to call
            ``super().message_handler(message)``.

        Args:
            message: The message from the MCP server (request responder, notification, or exception).
        """
        from mcp import types

        if isinstance(message, Exception):
            logger.error("Error from MCP server: %s", message, exc_info=message)
            return
        if isinstance(message, types.ServerNotification):
            match message.root.method:
                case "notifications/tools/list_changed":
                    await self.load_tools()
                case "notifications/prompts/list_changed":
                    await self.load_prompts()
                case _:
                    logger.debug("Unhandled notification: %s", message.root.method)

    def _determine_approval_mode(
        self,
        *candidate_names: str,
    ) -> Literal["always_require", "never_require"] | None:
        if isinstance(self.approval_mode, dict):
            if (always_require := self.approval_mode.get("always_require_approval")) and any(
                name in always_require for name in candidate_names
            ):
                return "always_require"
            if (never_require := self.approval_mode.get("never_require_approval")) and any(
                name in never_require for name in candidate_names
            ):
                return "never_require"
            return None
        return self.approval_mode  # type: ignore[return-value]

    async def load_prompts(self) -> None:
        """Load prompts from the MCP server.

        Retrieves available prompts from the connected MCP server and converts
        them into FunctionTool instances. Handles pagination automatically.

        Raises:
            ToolExecutionException: If the MCP server is not connected.
        """
        from mcp import types

        # Track existing function names to prevent duplicates
        existing_names = {func.name for func in self._functions}

        params: types.PaginatedRequestParams | None = None
        while True:
            # Ensure connection is still valid before each page request
            await self._ensure_connected()

            prompt_list = await self.session.list_prompts(params=params)  # type: ignore[union-attr]

            for prompt in prompt_list.prompts:
                normalized_name = _normalize_mcp_name(prompt.name)
                local_name = _build_prefixed_mcp_name(normalized_name, self.tool_name_prefix)

                # Skip if already loaded
                if local_name in existing_names:
                    continue

                input_model = _get_input_model_from_mcp_prompt(prompt)
                approval_mode = self._determine_approval_mode(local_name, normalized_name, prompt.name)
                func: FunctionTool = FunctionTool(
                    func=partial(self.get_prompt, prompt.name),
                    name=local_name,
                    description=prompt.description or "",
                    approval_mode=approval_mode,
                    input_model=input_model,
                    additional_properties={
                        _MCP_REMOTE_NAME_KEY: prompt.name,
                        _MCP_NORMALIZED_NAME_KEY: normalized_name,
                    },
                )
                self._functions.append(func)
                existing_names.add(local_name)

            # Check if there are more pages
            if not prompt_list or not prompt_list.nextCursor:
                break
            params = types.PaginatedRequestParams(cursor=prompt_list.nextCursor)

    async def load_tools(self) -> None:
        """Load tools from the MCP server.

        Retrieves available tools from the connected MCP server and converts
        them into FunctionTool instances. Handles pagination automatically.

        Raises:
            ToolExecutionException: If the MCP server is not connected.
        """
        from mcp import types

        # Track existing function names to prevent duplicates
        existing_names = {func.name for func in self._functions}

        params: types.PaginatedRequestParams | None = None
        while True:
            # Ensure connection is still valid before each page request
            await self._ensure_connected()

            tool_list = await self.session.list_tools(params=params)  # type: ignore[union-attr]

            for tool in tool_list.tools:
                normalized_name = _normalize_mcp_name(tool.name)
                local_name = _build_prefixed_mcp_name(normalized_name, self.tool_name_prefix)

                # Skip if already loaded
                if local_name in existing_names:
                    continue

                approval_mode = self._determine_approval_mode(local_name, normalized_name, tool.name)
                # Normalize inputSchema: ensure "properties" exists for object schemas.
                # Some MCP servers (e.g. zero-argument tools) omit "properties",
                # which causes OpenAI API to reject the schema with a 400 error.
                # Guard against non-conforming MCP servers that send inputSchema=None
                # despite the MCP spec typing it as dict[str, Any].
                input_schema = dict(tool.inputSchema or {})
                if input_schema.get("type") == "object" and "properties" not in input_schema:
                    input_schema["properties"] = {}

                async def _call_tool_with_runtime_kwargs(
                    ctx: FunctionInvocationContext,
                    *,
                    _remote_tool_name: str = tool.name,
                    **kwargs: Any,
                ) -> str | list[Content]:
                    call_kwargs = dict(ctx.kwargs)
                    call_kwargs.update(kwargs)
                    return await self.call_tool(_remote_tool_name, **call_kwargs)

                # Create FunctionTools out of each tool
                func: FunctionTool = FunctionTool(
                    func=_call_tool_with_runtime_kwargs,
                    name=local_name,
                    description=tool.description or "",
                    approval_mode=approval_mode,
                    input_model=input_schema,
                    additional_properties={
                        _MCP_REMOTE_NAME_KEY: tool.name,
                        _MCP_NORMALIZED_NAME_KEY: normalized_name,
                    },
                )
                self._functions.append(func)
                existing_names.add(local_name)

            # Check if there are more pages
            if not tool_list or not tool_list.nextCursor:
                break
            params = types.PaginatedRequestParams(cursor=tool_list.nextCursor)

    async def _close_on_owner(self) -> None:
        await self._safe_close_exit_stack()
        self._exit_stack = AsyncExitStack()
        self.session = None
        self.is_connected = False

    async def close(self) -> None:
        """Disconnect from the MCP server.

        Closes the connection and cleans up resources.
        """
        if self._is_lifecycle_owner_task():
            await self._close_on_owner()
            return

        async with self._lifecycle_request_lock:
            await self._run_on_lifecycle_owner("close")

    @abstractmethod
    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP client.

        Returns:
            An async context manager for the MCP client transport.
        """
        pass

    async def _ensure_connected(self) -> None:
        """Ensure the connection is valid, reconnecting if necessary.

        This method proactively checks if the connection is valid and
        reconnects if it's not, avoiding the need to catch ClosedResourceError.

        Raises:
            ToolExecutionException: If reconnection fails.
        """
        try:
            await self.session.send_ping()  # type: ignore[union-attr]
        except Exception:
            logger.info("MCP connection invalid or closed. Reconnecting...")
            try:
                await self.connect(reset=True)
            except Exception as ex:
                raise ToolExecutionException(
                    "Failed to establish MCP connection.",
                    inner_exception=ex,
                ) from ex

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str | list[Content]:
        """Call a tool with the given arguments.

        Args:
            tool_name: The name of the tool to call.

        Keyword Args:
            kwargs: Arguments to pass to the tool.

        Returns:
            A list of Content items representing the tool output.  The default
            ``parse_tool_results`` always returns ``list[Content]``; a custom
            callback may return a plain ``str`` which is also accepted.

        Raises:
            ToolExecutionException: If the MCP server is not connected, tools are not loaded,
                or the tool call fails.
        """
        from anyio import ClosedResourceError
        from mcp.shared.exceptions import McpError

        if not self.load_tools_flag:
            raise ToolExecutionException(
                "Tools are not loaded for this server, please set load_tools=True in the constructor."
            )
        # Filter out framework kwargs that cannot be serialized by the MCP SDK.
        # These are internal objects passed through the function invocation pipeline
        # that should not be forwarded to external MCP servers.
        # conversation_id is an internal tracking ID used by services like Azure AI.
        # options contains metadata/store used by AG-UI for Azure AI client requirements.
        # response_format is a Pydantic model class used for structured output (not serializable).
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in {
                "chat_options",
                "tools",
                "tool_choice",
                "session",
                "thread",
                "conversation_id",
                "options",
                "response_format",
            }
        }

        # Inject OpenTelemetry trace context into MCP _meta for distributed tracing.
        otel_meta = _inject_otel_into_mcp_meta()

        parser = self.parse_tool_results or self._parse_tool_result_from_mcp
        # Try the operation, reconnecting once if the connection is closed
        for attempt in range(2):
            try:
                result = await self.session.call_tool(tool_name, arguments=filtered_kwargs, meta=otel_meta)  # type: ignore
                if result.isError:
                    parsed = parser(result)
                    text = (
                        "\n".join(c.text for c in parsed if c.type == "text" and c.text)
                        if isinstance(parsed, list)
                        else str(parsed)
                    )
                    raise ToolExecutionException(text or str(parsed))
                return parser(result)
            except ToolExecutionException:
                raise
            except ClosedResourceError as cl_ex:
                if attempt == 0:
                    # First attempt failed, try reconnecting
                    logger.info("MCP connection closed unexpectedly. Reconnecting...")
                    try:
                        await self.connect(reset=True)
                        continue  # Retry the operation
                    except Exception as reconn_ex:
                        raise ToolExecutionException(
                            "Failed to reconnect to MCP server.",
                            inner_exception=reconn_ex,
                        ) from reconn_ex
                else:
                    # Second attempt also failed, give up
                    logger.error(f"MCP connection closed unexpectedly after reconnection: {cl_ex}")
                    raise ToolExecutionException(
                        f"Failed to call tool '{tool_name}' - connection lost.",
                        inner_exception=cl_ex,
                    ) from cl_ex
            except McpError as mcp_exc:
                error_message = mcp_exc.error.message
                raise ToolExecutionException(error_message, inner_exception=mcp_exc) from mcp_exc
            except Exception as ex:
                raise ToolExecutionException(f"Failed to call tool '{tool_name}'.", inner_exception=ex) from ex
        raise ToolExecutionException(f"Failed to call tool '{tool_name}' after retries.")

    async def get_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        """Call a prompt with the given arguments.

        Args:
            prompt_name: The name of the prompt to retrieve.

        Keyword Args:
            kwargs: Arguments to pass to the prompt.

        Returns:
            A string representation of the prompt result — either plain text or serialized JSON.

        Raises:
            ToolExecutionException: If the MCP server is not connected, prompts are not loaded,
                or the prompt call fails.
        """
        from anyio import ClosedResourceError
        from mcp.shared.exceptions import McpError

        if not self.load_prompts_flag:
            raise ToolExecutionException(
                "Prompts are not loaded for this server, please set load_prompts=True in the constructor."
            )

        parser = self.parse_prompt_results or self._parse_prompt_result_from_mcp
        # Try the operation, reconnecting once if the connection is closed
        for attempt in range(2):
            try:
                prompt_result = await self.session.get_prompt(prompt_name, arguments=kwargs)  # type: ignore
                return parser(prompt_result)
            except ClosedResourceError as cl_ex:
                if attempt == 0:
                    # First attempt failed, try reconnecting
                    logger.info("MCP connection closed unexpectedly. Reconnecting...")
                    try:
                        await self.connect(reset=True)
                        continue  # Retry the operation
                    except Exception as reconn_ex:
                        raise ToolExecutionException(
                            "Failed to reconnect to MCP server.",
                            inner_exception=reconn_ex,
                        ) from reconn_ex
                else:
                    # Second attempt also failed, give up
                    logger.error(f"MCP connection closed unexpectedly after reconnection: {cl_ex}")
                    raise ToolExecutionException(
                        f"Failed to call prompt '{prompt_name}' - connection lost.",
                        inner_exception=cl_ex,
                    ) from cl_ex
            except McpError as mcp_exc:
                error_message = mcp_exc.error.message
                raise ToolExecutionException(error_message, inner_exception=mcp_exc) from mcp_exc
            except Exception as ex:
                raise ToolExecutionException(f"Failed to call prompt '{prompt_name}'.", inner_exception=ex) from ex
        raise ToolExecutionException(f"Failed to get prompt '{prompt_name}' after retries.")

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        Connects to the MCP server automatically.

        Returns:
            The MCPTool instance.

        Raises:
            ToolException: If connection fails.
            ToolExecutionException: If context manager setup fails.
        """
        try:
            await self.connect()
            return self
        except ToolException:
            raise
        except Exception as ex:
            await self.close()
            raise ToolExecutionException("Failed to enter context manager.", inner_exception=ex) from ex

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        """Exit the async context manager.

        Closes the connection and cleans up resources.

        Args:
            exc_type: The exception type if an exception was raised, None otherwise.
            exc_value: The exception value if an exception was raised, None otherwise.
            traceback: The exception traceback if an exception was raised, None otherwise.
        """
        await self.close()


# region: MCP Plugin Implementations


class MCPStdioTool(MCPTool):
    """MCP tool for connecting to stdio-based MCP servers.

    This class connects to MCP servers that communicate via standard input/output,
    typically used for local processes.

    Examples:
        .. code-block:: python

            from agent_framework import MCPStdioTool, Agent

            # Create an MCP stdio tool
            mcp_tool = MCPStdioTool(
                name="filesystem",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                description="File system operations",
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = Agent(client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("List files in the directory")
    """

    def __init__(
        self,
        name: str,
        command: str,
        *,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        encoding: str | None = None,
        client: SupportsChatGetResponse | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP stdio tool.

        Note:
            The arguments are used to create a StdioServerParameters object,
            which is then used to create a stdio client. See ``mcp.client.stdio.stdio_client``
            and ``mcp.client.stdio.stdio_server_parameters`` for more details.

        Args:
            name: The name of the tool.
            command: The command to run the MCP server.

        Keyword Args:
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
                access the ``.functions`` list after connecting and set ``result_parser`` on
                individual ``FunctionTool`` instances.
            request_timeout: The default timeout in seconds for all requests.
            session: The session to use for the MCP connection.
            description: The description of the tool.
            approval_mode: The approval mode for the tool. This can be:
                - "always_require": The tool always requires approval before use.
                - "never_require": The tool never requires approval before use.
                - A dict with keys `always_require_approval` or `never_require_approval`,
                  followed by a sequence of strings with the names of the relevant tools.
                A tool should not be listed in both, if so, it will require approval.
            allowed_tools: A list of tools that are allowed to use this tool.
            additional_properties: Additional properties.
            args: The arguments to pass to the command.
            env: The environment variables to set for the command.
            encoding: The encoding to use for the command output.
            client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the stdio client.
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            tool_name_prefix=tool_name_prefix,
            additional_properties=additional_properties,
            session=session,
            client=client,
            load_tools=load_tools,
            parse_tool_results=parse_tool_results,
            load_prompts=load_prompts,
            parse_prompt_results=parse_prompt_results,
            request_timeout=request_timeout,
        )
        self.command = command
        self.args = args or []
        self.env = env
        self.encoding = encoding
        self._client_kwargs = kwargs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP stdio client.

        Returns:
            An async context manager for the stdio client transport.
        """
        args: dict[str, Any] = {
            "command": self.command,
            "args": self.args,
            "env": self.env,
        }
        if self.encoding:
            args["encoding"] = self.encoding
        if self._client_kwargs:
            args.update(self._client_kwargs)
        try:
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ModuleNotFoundError as ex:
            raise ModuleNotFoundError("`mcp` is required to use `MCPStdioTool`. Please install `mcp`.") from ex

        return stdio_client(server=StdioServerParameters(**args))


class MCPStreamableHTTPTool(MCPTool):
    """MCP tool for connecting to HTTP-based MCP servers.

    This class connects to MCP servers that communicate via streamable HTTP/SSE.

    Examples:
        .. code-block:: python

            from agent_framework import MCPStreamableHTTPTool, Agent

            # Create an MCP HTTP tool
            mcp_tool = MCPStreamableHTTPTool(
                name="web-api",
                url="https://api.example.com/mcp",
                description="Web API operations",
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = Agent(client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("Fetch data from the API")
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        terminate_on_close: bool | None = None,
        client: SupportsChatGetResponse | None = None,
        additional_properties: dict[str, Any] | None = None,
        http_client: AsyncClient | None = None,
        header_provider: Callable[[dict[str, Any]], dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP streamable HTTP tool.

        Note:
            The arguments are used to create a streamable HTTP client using the
            new ``mcp.client.streamable_http.streamable_http_client`` API.
            If an asyncClient is provided via ``http_client``, it will be used directly.
            Otherwise, the ``streamable_http_client`` API will create and manage a default client.

        Args:
            name: The name of the tool.
            url: The URL of the MCP server.

        Keyword Args:
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
                access the ``.functions`` list after connecting and set ``result_parser`` on
                individual ``FunctionTool`` instances.
            request_timeout: The default timeout in seconds for all requests.
            session: The session to use for the MCP connection.
            description: The description of the tool.
            approval_mode: The approval mode for the tool. This can be:
                - "always_require": The tool always requires approval before use.
                - "never_require": The tool never requires approval before use.
                - A dict with keys `always_require_approval` or `never_require_approval`,
                  followed by a sequence of strings with the names of the relevant tools.
                A tool should not be listed in both, if so, it will require approval.
            allowed_tools: A list of tools that are allowed to use this tool.
            additional_properties: Additional properties.
            terminate_on_close: Close the transport when the MCP client is terminated.
            client: The chat client to use for sampling.
            http_client: Optional asyncClient to use. If not provided, the
                ``streamable_http_client`` API will create and manage a default client.
                To configure headers, timeouts, or other HTTP client settings, create
                and pass your own ``asyncClient`` instance.
            header_provider: Optional callable that receives the runtime keyword arguments
                (from ``FunctionInvocationContext.kwargs``) and returns a ``dict[str, str]``
                of HTTP headers to inject into every outbound request to the MCP server.
                Use this to forward per-request context (e.g. authentication tokens set in
                agent middleware) without creating a separate ``httpx.AsyncClient``.
            kwargs: Additional keyword arguments (accepted for backward compatibility but not used).
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            tool_name_prefix=tool_name_prefix,
            additional_properties=additional_properties,
            session=session,
            client=client,
            load_tools=load_tools,
            parse_tool_results=parse_tool_results,
            load_prompts=load_prompts,
            parse_prompt_results=parse_prompt_results,
            request_timeout=request_timeout,
        )
        self.url = url
        self.terminate_on_close = terminate_on_close
        self._httpx_client: AsyncClient | None = http_client
        self._header_provider = header_provider

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP streamable HTTP client.

        Returns:
            An async context manager for the streamable HTTP client transport.
        """
        from httpx import AsyncClient, Request, Timeout

        http_client = self._httpx_client
        if self._header_provider is not None:
            if http_client is None:
                http_client = AsyncClient(
                    follow_redirects=True,
                    timeout=Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
                )
                self._httpx_client = http_client

            if not hasattr(self, "_inject_headers_hook"):

                async def _inject_headers(request: Request) -> None:  # noqa: RUF029
                    headers = _mcp_call_headers.get({})
                    for key, value in headers.items():
                        request.headers[key] = value

                self._inject_headers_hook = _inject_headers  # type: ignore[attr-defined]
                http_client.event_hooks["request"].append(self._inject_headers_hook)  # type: ignore[attr-defined]

        return streamable_http_client(
            url=self.url,
            http_client=http_client,
            terminate_on_close=self.terminate_on_close if self.terminate_on_close is not None else True,
        )

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str | list[Content]:
        """Call a tool, injecting headers from the header_provider if configured.

        When a ``header_provider`` was supplied at construction time, the runtime
        *kwargs* (originating from ``FunctionInvocationContext.kwargs``) are passed
        to the provider.  The returned headers are attached to every HTTP request
        made during this tool call via a ``contextvars.ContextVar``.

        Args:
            tool_name: The name of the tool to call.

        Keyword Args:
            kwargs: Arguments to pass to the tool.

        Returns:
            A list of Content items representing the tool output.
        """
        if self._header_provider is not None:
            headers = self._header_provider(kwargs)
            token = _mcp_call_headers.set(headers)
            try:
                return await super().call_tool(tool_name, **kwargs)
            finally:
                _mcp_call_headers.reset(token)
        return await super().call_tool(tool_name, **kwargs)


class MCPWebsocketTool(MCPTool):
    """MCP tool for connecting to WebSocket-based MCP servers.

    This class connects to MCP servers that communicate via WebSocket.

    Examples:
        .. code-block:: python

            from agent_framework import MCPWebsocketTool, Agent

            # Create an MCP WebSocket tool
            mcp_tool = MCPWebsocketTool(
                name="realtime-service", url="wss://service.example.com/mcp", description="Real-time service operations"
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = Agent(client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("Connect to the real-time service")
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        client: SupportsChatGetResponse | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP WebSocket tool.

        Note:
            The arguments are used to create a WebSocket client.
            See ``mcp.client.websocket.websocket_client`` for more details.
            Any extra arguments passed to the constructor will be passed to the
            WebSocket client constructor.

        Args:
            name: The name of the tool.
            url: The URL of the MCP server.

        Keyword Args:
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
                access the ``.functions`` list after connecting and set ``result_parser`` on
                individual ``FunctionTool`` instances.
            request_timeout: The default timeout in seconds for all requests.
            session: The session to use for the MCP connection.
            description: The description of the tool.
            approval_mode: The approval mode for the tool. This can be:
                - "always_require": The tool always requires approval before use.
                - "never_require": The tool never requires approval before use.
                - A dict with keys `always_require_approval` or `never_require_approval`,
                  followed by a sequence of strings with the names of the relevant tools.
                A tool should not be listed in both, if so, it will require approval.
            allowed_tools: A list of tools that are allowed to use this tool.
            additional_properties: Additional properties.
            client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the WebSocket client.
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            tool_name_prefix=tool_name_prefix,
            additional_properties=additional_properties,
            session=session,
            client=client,
            load_tools=load_tools,
            parse_tool_results=parse_tool_results,
            load_prompts=load_prompts,
            parse_prompt_results=parse_prompt_results,
            request_timeout=request_timeout,
        )
        self.url = url
        self._client_kwargs = kwargs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP WebSocket client.

        Returns:
            An async context manager for the WebSocket client transport.
        """
        try:
            from mcp.client.websocket import websocket_client
        except ModuleNotFoundError as ex:
            missing_name = ex.name or "mcp/websocket dependencies"
            if missing_name == "mcp" or missing_name.startswith("mcp."):
                reason = "The `mcp` package is not installed."
            elif missing_name == "websockets" or missing_name.startswith("websockets."):
                reason = "WebSocket transport support is not installed."
            else:
                reason = f"The optional dependency `{missing_name}` is not installed."
            raise ModuleNotFoundError(
                f"`MCPWebsocketTool` requires websocket transport support. {reason} "
                "Please install `mcp[ws]` and update your dependencies."
            ) from ex

        args: dict[str, Any] = {
            "url": self.url,
        }
        if self._client_kwargs:
            args.update(self._client_kwargs)
        return websocket_client(**args)

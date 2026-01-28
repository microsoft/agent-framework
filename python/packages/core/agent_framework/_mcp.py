# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import logging
import re
import sys
from abc import abstractmethod
from collections.abc import Callable, Collection, Sequence
from contextlib import AsyncExitStack, _AsyncGeneratorContextManager  # type: ignore
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, Literal

import httpx
from anyio import ClosedResourceError
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.websocket import websocket_client
from mcp.shared.context import RequestContext
from mcp.shared.exceptions import McpError
from mcp.shared.session import RequestResponder
from pydantic import BaseModel, create_model

from ._tools import (
    FunctionTool,
    HostedMCPSpecificApproval,
    _build_pydantic_model_from_json_schema,
)
from ._types import (
    ChatMessage,
    Content,
    Role,
)
from .exceptions import ToolException, ToolExecutionException

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from ._clients import ChatClientProtocol

logger = logging.getLogger(__name__)

# region: Helpers

LOG_LEVEL_MAPPING: dict[types.LoggingLevel, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}

__all__ = [
    "MCPStdioTool",
    "MCPStreamableHTTPTool",
    "MCPWebsocketTool",
]


def _parse_message_from_mcp(
    mcp_type: types.PromptMessage | types.SamplingMessage,
) -> ChatMessage:
    """Parse an MCP container type into an Agent Framework type."""
    return ChatMessage(
        role=Role(value=mcp_type.role),
        contents=_parse_content_from_mcp(mcp_type.content),
        raw_representation=mcp_type,
    )


def _parse_contents_from_mcp_tool_result(
    mcp_type: types.CallToolResult,
) -> list[Content]:
    """Parse an MCP CallToolResult into Agent Framework content types.

    This function extracts the complete _meta field from CallToolResult objects
    and merges all metadata into the additional_properties field of converted
    content items.

    Note: The _meta field from CallToolResult is applied to ALL content items
    in the result, as the Agent Framework's content model doesn't have a
    result-level metadata container. This ensures metadata is preserved but
    means it will be duplicated across multiple content items if present.

    Args:
        mcp_type: The MCP CallToolResult object to convert.

    Returns:
        A list of Agent Framework content items with metadata merged into
        additional_properties.
    """
    meta_data = mcp_type.meta

    # Prepare merged metadata once if present
    merged_meta_props = None
    if meta_data:
        merged_meta_props = {}
        if hasattr(meta_data, "__dict__"):
            merged_meta_props.update(meta_data.__dict__)
        elif isinstance(meta_data, dict):
            merged_meta_props.update(meta_data)
        else:
            merged_meta_props["_meta"] = meta_data

    # Convert each content item and merge metadata
    result_contents = []
    for item in mcp_type.content:
        contents = _parse_content_from_mcp(item)

        if merged_meta_props:
            for content in contents:
                existing_props = getattr(content, "additional_properties", None) or {}
                # Merge with content-specific properties, letting content-specific props override
                final_props = merged_meta_props.copy()
                final_props.update(existing_props)
                content.additional_properties = final_props
        result_contents.extend(contents)
    return result_contents


def _parse_content_from_mcp(
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
    mcp_types = mcp_type if isinstance(mcp_type, Sequence) else [mcp_type]
    return_types: list[Content] = []
    for mcp_type in mcp_types:
        match mcp_type:
            case types.TextContent():
                return_types.append(Content.from_text(text=mcp_type.text, raw_representation=mcp_type))
            case types.ImageContent() | types.AudioContent():
                # MCP protocol uses base64-encoded strings, convert to bytes
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
                        result=_parse_content_from_mcp(mcp_type.content)
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
    return return_types


def _prepare_content_for_mcp(
    content: Content,
) -> types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink | None:
    """Prepare an Agent Framework content type for MCP."""
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
                    # uri's are not limited in MCP but they have to be set.
                    # the uri of data content, contains the data uri, which
                    # is not the uri meant here, UriContent would match this.
                    uri=(
                        content.additional_properties.get("uri", "af://binary")
                        if content.additional_properties
                        else "af://binary"
                    ),  # type: ignore[reportArgumentType]
                ),
            )
        return None
    if content.type == "uri":
        return types.ResourceLink(
            type="resource_link",
            uri=content.uri,  # type: ignore[reportArgumentType,attr-defined]
            mimeType=content.media_type,  # type: ignore[attr-defined]
            name=(content.additional_properties.get("name", "Unknown") if content.additional_properties else "Unknown"),
        )
    return None


def _prepare_message_for_mcp(
    content: ChatMessage,
) -> list[types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink]:
    """Prepare a ChatMessage for MCP format."""
    messages: list[
        types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink
    ] = []
    for item in content.contents:
        mcp_content = _prepare_content_for_mcp(item)
        if mcp_content:
            messages.append(mcp_content)
    return messages


def _get_input_model_from_mcp_prompt(prompt: types.Prompt) -> type[BaseModel]:
    """Creates a Pydantic model from a prompt's parameters."""
    # Check if 'arguments' is missing or empty
    if not prompt.arguments:
        return create_model(f"{prompt.name}_input")

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

    schema = {"properties": properties, "required": required}
    return _build_pydantic_model_from_json_schema(prompt.name, schema)


def _get_input_model_from_mcp_tool(tool: types.Tool) -> type[BaseModel]:
    """Creates a Pydantic model from a tools parameters."""
    return _build_pydantic_model_from_json_schema(tool.name, tool.inputSchema)


def _normalize_mcp_name(name: str) -> str:
    """Normalize MCP tool/prompt names to allowed identifier pattern (A-Za-z0-9_.-)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name)


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
        approval_mode: (Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        load_tools: bool = True,
        parse_tool_results: Literal[True] | Callable[[types.CallToolResult], Any] | None = True,
        load_prompts: bool = True,
        parse_prompt_results: Literal[True] | Callable[[types.GetPromptResult], Any] | None = True,
        session: ClientSession | None = None,
        request_timeout: int | None = None,
        chat_client: "ChatClientProtocol | None" = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the MCP Tool base.

        Note:
            Do not use this method, use one of the subclasses: MCPStreamableHTTPTool, MCPWebsocketTool
            or MCPStdioTool.
        """
        self.name = name
        self.description = description or ""
        self.approval_mode = approval_mode
        self.allowed_tools = allowed_tools
        self.additional_properties = additional_properties
        self.load_tools_flag = load_tools
        self.parse_tool_results = parse_tool_results
        self.load_prompts_flag = load_prompts
        self.parse_prompt_results = parse_prompt_results
        self._exit_stack = AsyncExitStack()
        self.session = session
        self.request_timeout = request_timeout
        self.chat_client = chat_client
        self._functions: list[FunctionTool[Any, Any]] = []
        self.is_connected: bool = False
        self._tools_loaded: bool = False
        self._prompts_loaded: bool = False

    def __str__(self) -> str:
        return f"MCPTool(name={self.name}, description={self.description})"

    @property
    def functions(self) -> list[FunctionTool[Any, Any]]:
        """Get the list of functions that are allowed."""
        if not self.allowed_tools:
            return self._functions
        return [func for func in self._functions if func.name in self.allowed_tools]

    async def _safe_close_exit_stack(self) -> None:
        """Safely close the exit stack, handling cross-task boundary errors.

        anyio's cancel scopes are bound to the task they were created in.
        If aclose() is called from a different task (e.g., during streaming reconnection),
        anyio will raise a RuntimeError or CancelledError. In this case, we log a warning
        and allow garbage collection to clean up the resources.

        Known error variants:
        - "Attempted to exit cancel scope in a different task than it was entered in"
        - "Attempted to exit a cancel scope that isn't the current task's current cancel scope"
        - CancelledError from anyio cancel scope cleanup
        """
        try:
            await self._exit_stack.aclose()
        except RuntimeError as e:
            error_msg = str(e).lower()
            # Check for anyio cancel scope errors (multiple variants exist)
            if "cancel scope" in error_msg:
                logger.warning(
                    "Could not cleanly close MCP exit stack due to cancel scope error. "
                    "Old resources will be garbage collected. Error: %s",
                    e,
                )
            else:
                raise
        except asyncio.CancelledError:
            # CancelledError can occur during cleanup when cancel scopes are involved
            logger.warning(
                "Could not cleanly close MCP exit stack due to cancellation. Old resources will be garbage collected."
            )

    async def connect(self, *, reset: bool = False) -> None:
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
                session = await self._exit_stack.enter_async_context(
                    ClientSession(
                        read_stream=transport[0],
                        write_stream=transport[1],
                        read_timeout_seconds=(
                            timedelta(seconds=self.request_timeout) if self.request_timeout else None
                        ),
                        message_handler=self.message_handler,
                        logging_callback=self.logging_callback,
                        sampling_callback=self.sampling_callback,
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
        elif self.session._request_id == 0:  # type: ignore[reportPrivateUsage]
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
                await self.session.set_logging_level(
                    next(level for level, value in LOG_LEVEL_MAPPING.items() if value == logger.level)
                )
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
        if not self.chat_client:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="No chat client available. Please set a chat client.",
            )
        logger.debug("Sampling callback called with params: %s", params)
        messages: list[ChatMessage] = []
        for msg in params.messages:
            messages.append(_parse_message_from_mcp(msg))
        try:
            response = await self.chat_client.get_response(
                messages,
                temperature=params.temperature,
                max_tokens=params.maxTokens,
                stop=params.stopSequences,
            )
        except Exception as ex:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message=f"Failed to get chat message content: {ex}",
            )
        if not response or not response.messages:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="Failed to get chat message content.",
            )
        mcp_contents = _prepare_message_for_mcp(response.messages[0])
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
        local_name: str,
    ) -> Literal["always_require", "never_require"] | None:
        if isinstance(self.approval_mode, dict):
            if (always_require := self.approval_mode.get("always_require_approval")) and local_name in always_require:
                return "always_require"
            if (never_require := self.approval_mode.get("never_require_approval")) and local_name in never_require:
                return "never_require"
            return None
        return self.approval_mode  # type: ignore[reportReturnType]

    async def load_prompts(self) -> None:
        """Load prompts from the MCP server.

        Retrieves available prompts from the connected MCP server and converts
        them into FunctionTool instances. Handles pagination automatically.

        Raises:
            ToolExecutionException: If the MCP server is not connected.
        """
        # Track existing function names to prevent duplicates
        existing_names = {func.name for func in self._functions}

        params: types.PaginatedRequestParams | None = None
        while True:
            # Ensure connection is still valid before each page request
            await self._ensure_connected()

            prompt_list = await self.session.list_prompts(params=params)  # type: ignore[union-attr]

            for prompt in prompt_list.prompts:
                local_name = _normalize_mcp_name(prompt.name)

                # Skip if already loaded
                if local_name in existing_names:
                    continue

                input_model = _get_input_model_from_mcp_prompt(prompt)
                approval_mode = self._determine_approval_mode(local_name)
                func: FunctionTool[BaseModel, list[ChatMessage] | Any | types.GetPromptResult] = FunctionTool(
                    func=partial(self.get_prompt, prompt.name),
                    name=local_name,
                    description=prompt.description or "",
                    approval_mode=approval_mode,
                    input_model=input_model,
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
        # Track existing function names to prevent duplicates
        existing_names = {func.name for func in self._functions}

        params: types.PaginatedRequestParams | None = None
        while True:
            # Ensure connection is still valid before each page request
            await self._ensure_connected()

            tool_list = await self.session.list_tools(params=params)  # type: ignore[union-attr]

            for tool in tool_list.tools:
                local_name = _normalize_mcp_name(tool.name)

                # Skip if already loaded
                if local_name in existing_names:
                    continue

                input_model = _get_input_model_from_mcp_tool(tool)
                approval_mode = self._determine_approval_mode(local_name)
                # Create FunctionTools out of each tool
                func: FunctionTool[BaseModel, list[Content] | Any | types.CallToolResult] = FunctionTool(
                    func=partial(self.call_tool, tool.name),
                    name=local_name,
                    description=tool.description or "",
                    approval_mode=approval_mode,
                    input_model=input_model,
                )
                self._functions.append(func)
                existing_names.add(local_name)

            # Check if there are more pages
            if not tool_list or not tool_list.nextCursor:
                break
            params = types.PaginatedRequestParams(cursor=tool_list.nextCursor)

    async def close(self) -> None:
        """Disconnect from the MCP server.

        Closes the connection and cleans up resources.
        """
        await self._safe_close_exit_stack()
        self.session = None
        self.is_connected = False

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

    async def call_tool(self, tool_name: str, **kwargs: Any) -> list[Content] | Any | types.CallToolResult:
        """Call a tool with the given arguments.

        Args:
            tool_name: The name of the tool to call.

        Keyword Args:
            kwargs: Arguments to pass to the tool.

        Returns:
            A list of content items returned by the tool.

        Raises:
            ToolExecutionException: If the MCP server is not connected, tools are not loaded,
                or the tool call fails.
        """
        if not self.load_tools_flag:
            raise ToolExecutionException(
                "Tools are not loaded for this server, please set load_tools=True in the constructor."
            )
        # Filter out framework kwargs that cannot be serialized by the MCP SDK.
        # These are internal objects passed through the function invocation pipeline
        # that should not be forwarded to external MCP servers.
        # conversation_id is an internal tracking ID used by services like Azure AI.
        # options contains metadata/store used by AG-UI for Azure AI client requirements.
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in {"chat_options", "tools", "tool_choice", "thread", "conversation_id", "options"}
        }

        # Try the operation, reconnecting once if the connection is closed
        for attempt in range(2):
            try:
                result = await self.session.call_tool(tool_name, arguments=filtered_kwargs)  # type: ignore
                if self.parse_tool_results is None:
                    return result
                if self.parse_tool_results is True:
                    return _parse_contents_from_mcp_tool_result(result)
                if callable(self.parse_tool_results):
                    return self.parse_tool_results(result)
                return result
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
                raise ToolExecutionException(mcp_exc.error.message, inner_exception=mcp_exc) from mcp_exc
            except Exception as ex:
                raise ToolExecutionException(f"Failed to call tool '{tool_name}'.", inner_exception=ex) from ex
        raise ToolExecutionException(f"Failed to call tool '{tool_name}' after retries.")

    async def get_prompt(self, prompt_name: str, **kwargs: Any) -> list[ChatMessage] | Any | types.GetPromptResult:
        """Call a prompt with the given arguments.

        Args:
            prompt_name: The name of the prompt to retrieve.

        Keyword Args:
            kwargs: Arguments to pass to the prompt.

        Returns:
            A list of chat messages returned by the prompt.

        Raises:
            ToolExecutionException: If the MCP server is not connected, prompts are not loaded,
                or the prompt call fails.
        """
        if not self.load_prompts_flag:
            raise ToolExecutionException(
                "Prompts are not loaded for this server, please set load_prompts=True in the constructor."
            )

        # Try the operation, reconnecting once if the connection is closed
        for attempt in range(2):
            try:
                prompt_result = await self.session.get_prompt(prompt_name, arguments=kwargs)  # type: ignore
                if self.parse_prompt_results is None:
                    return prompt_result
                if self.parse_prompt_results is True:
                    return [_parse_message_from_mcp(message) for message in prompt_result.messages]
                if callable(self.parse_prompt_results):
                    return self.parse_prompt_results(prompt_result)
                return prompt_result
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
                raise ToolExecutionException(mcp_exc.error.message, inner_exception=mcp_exc) from mcp_exc
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
            await self._safe_close_exit_stack()
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

            from agent_framework import MCPStdioTool, ChatAgent

            # Create an MCP stdio tool
            mcp_tool = MCPStdioTool(
                name="filesystem",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                description="File system operations",
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = ChatAgent(chat_client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("List files in the directory")
    """

    def __init__(
        self,
        name: str,
        command: str,
        *,
        load_tools: bool = True,
        parse_tool_results: Literal[True] | Callable[[types.CallToolResult], Any] | None = True,
        load_prompts: bool = True,
        parse_prompt_results: Literal[True] | Callable[[types.GetPromptResult], Any] | None = True,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        encoding: str | None = None,
        chat_client: "ChatClientProtocol | None" = None,
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
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: How to parse tool results from the MCP server.
                Set to True, to use the default parser that converts to Agent Framework types.
                Set to a callable to use a custom parser function.
                Set to None to return the raw MCP tool result.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: How to parse prompt results from the MCP server.
                Set to True, to use the default parser that converts to Agent Framework types.
                Set to a callable to use a custom parser function.
                Set to None to return the raw MCP prompt result.
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
            chat_client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the stdio client.
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            additional_properties=additional_properties,
            session=session,
            chat_client=chat_client,
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
        return stdio_client(server=StdioServerParameters(**args))


class MCPStreamableHTTPTool(MCPTool):
    """MCP tool for connecting to HTTP-based MCP servers.

    This class connects to MCP servers that communicate via streamable HTTP/SSE.

    Examples:
        .. code-block:: python

            from agent_framework import MCPStreamableHTTPTool, ChatAgent

            # Create an MCP HTTP tool
            mcp_tool = MCPStreamableHTTPTool(
                name="web-api",
                url="https://api.example.com/mcp",
                description="Web API operations",
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = ChatAgent(chat_client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("Fetch data from the API")
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        load_tools: bool = True,
        parse_tool_results: Literal[True] | Callable[[types.CallToolResult], Any] | None = True,
        load_prompts: bool = True,
        parse_prompt_results: Literal[True] | Callable[[types.GetPromptResult], Any] | None = True,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        terminate_on_close: bool | None = None,
        chat_client: "ChatClientProtocol | None" = None,
        additional_properties: dict[str, Any] | None = None,
        http_client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP streamable HTTP tool.

        Note:
            The arguments are used to create a streamable HTTP client using the
            new ``mcp.client.streamable_http.streamable_http_client`` API.
            If an httpx.AsyncClient is provided via ``http_client``, it will be used directly.
            Otherwise, the ``streamable_http_client`` API will create and manage a default client.

        Args:
            name: The name of the tool.
            url: The URL of the MCP server.

        Keyword Args:
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: How to parse tool results from the MCP server.
                Set to True, to use the default parser that converts to Agent Framework types.
                Set to a callable to use a custom parser function.
                Set to None to return the raw MCP tool result.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: How to parse prompt results from the MCP server.
                Set to True, to use the default parser that converts to Agent Framework types.
                Set to a callable to use a custom parser function.
                Set to None to return the raw MCP prompt result.
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
            chat_client: The chat client to use for sampling.
            http_client: Optional httpx.AsyncClient to use. If not provided, the
                ``streamable_http_client`` API will create and manage a default client.
                To configure headers, timeouts, or other HTTP client settings, create
                and pass your own ``httpx.AsyncClient`` instance.
            kwargs: Additional keyword arguments (accepted for backward compatibility but not used).
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            additional_properties=additional_properties,
            session=session,
            chat_client=chat_client,
            load_tools=load_tools,
            parse_tool_results=parse_tool_results,
            load_prompts=load_prompts,
            parse_prompt_results=parse_prompt_results,
            request_timeout=request_timeout,
        )
        self.url = url
        self.terminate_on_close = terminate_on_close
        self._httpx_client: httpx.AsyncClient | None = http_client

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP streamable HTTP client.

        Returns:
            An async context manager for the streamable HTTP client transport.
        """
        # Pass the http_client (which may be None) to streamable_http_client
        return streamable_http_client(
            url=self.url,
            http_client=self._httpx_client,
            terminate_on_close=self.terminate_on_close if self.terminate_on_close is not None else True,
        )


class MCPWebsocketTool(MCPTool):
    """MCP tool for connecting to WebSocket-based MCP servers.

    This class connects to MCP servers that communicate via WebSocket.

    Examples:
        .. code-block:: python

            from agent_framework import MCPWebsocketTool, ChatAgent

            # Create an MCP WebSocket tool
            mcp_tool = MCPWebsocketTool(
                name="realtime-service", url="wss://service.example.com/mcp", description="Real-time service operations"
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = ChatAgent(chat_client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("Connect to the real-time service")
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        load_tools: bool = True,
        parse_tool_results: Literal[True] | Callable[[types.CallToolResult], Any] | None = True,
        load_prompts: bool = True,
        parse_prompt_results: Literal[True] | Callable[[types.GetPromptResult], Any] | None = True,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        chat_client: "ChatClientProtocol | None" = None,
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
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: How to parse tool results from the MCP server.
                Set to True, to use the default parser that converts to Agent Framework types.
                Set to a callable to use a custom parser function.
                Set to None to return the raw MCP tool result.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: How to parse prompt results from the MCP server.
                Set to True, to use the default parser that converts to Agent Framework types.
                Set to a callable to use a custom parser function.
                Set to None to return the raw MCP prompt result.
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
            chat_client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the WebSocket client.
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            additional_properties=additional_properties,
            session=session,
            chat_client=chat_client,
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
        args: dict[str, Any] = {
            "url": self.url,
        }
        if self._client_kwargs:
            args.update(self._client_kwargs)
        return websocket_client(**args)

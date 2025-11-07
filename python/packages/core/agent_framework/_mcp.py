# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import re
import sys
from abc import abstractmethod
from collections.abc import Collection
from contextlib import AsyncExitStack, _AsyncGeneratorContextManager  # type: ignore
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, Literal

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.websocket import websocket_client
from mcp.shared.context import RequestContext
from mcp.shared.exceptions import McpError
from mcp.shared.session import RequestResponder
from pydantic import BaseModel, Field, create_model

from ._tools import AIFunction, HostedMCPSpecificApproval
from ._types import ChatMessage, Contents, DataContent, Role, TextContent, UriContent
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


def _mcp_prompt_message_to_chat_message(
    mcp_type: types.PromptMessage | types.SamplingMessage,
) -> ChatMessage:
    """Convert a MCP container type to a Agent Framework type."""
    return ChatMessage(
        role=Role(value=mcp_type.role),
        contents=[_mcp_type_to_ai_content(mcp_type.content)],
        raw_representation=mcp_type,
    )


def _mcp_call_tool_result_to_ai_contents(
    mcp_type: types.CallToolResult,
) -> list[Contents]:
    """Convert a MCP container type to a Agent Framework type."""
    return [_mcp_type_to_ai_content(item) for item in mcp_type.content]


def _mcp_type_to_ai_content(
    mcp_type: types.ImageContent | types.TextContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink,
) -> Contents:
    """Convert a MCP type to a Agent Framework type."""
    match mcp_type:
        case types.TextContent():
            return TextContent(text=mcp_type.text, raw_representation=mcp_type)
        case types.ImageContent() | types.AudioContent():
            return DataContent(uri=mcp_type.data, media_type=mcp_type.mimeType, raw_representation=mcp_type)
        case types.ResourceLink():
            return UriContent(
                uri=str(mcp_type.uri), media_type=mcp_type.mimeType or "application/json", raw_representation=mcp_type
            )
        case _:
            match mcp_type.resource:
                case types.TextResourceContents():
                    return TextContent(
                        text=mcp_type.resource.text,
                        raw_representation=mcp_type,
                        additional_properties=mcp_type.annotations.model_dump() if mcp_type.annotations else None,
                    )
                case types.BlobResourceContents():
                    return DataContent(
                        uri=mcp_type.resource.blob,
                        media_type=mcp_type.resource.mimeType,
                        raw_representation=mcp_type,
                        additional_properties=mcp_type.annotations.model_dump() if mcp_type.annotations else None,
                    )


def _ai_content_to_mcp_types(
    content: Contents,
) -> types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink | None:
    """Convert a BaseContent type to a MCP type."""
    match content:
        case TextContent():
            return types.TextContent(type="text", text=content.text)
        case DataContent():
            if content.media_type and content.media_type.startswith("image/"):
                return types.ImageContent(type="image", data=content.uri, mimeType=content.media_type)
            if content.media_type and content.media_type.startswith("audio/"):
                return types.AudioContent(type="audio", data=content.uri, mimeType=content.media_type)
            if content.media_type and content.media_type.startswith("application/"):
                return types.EmbeddedResource(
                    type="resource",
                    resource=types.BlobResourceContents(
                        blob=content.uri,
                        mimeType=content.media_type,
                        # uri's are not limited in MCP but they have to be set.
                        # the uri of data content, contains the data uri, which
                        # is not the uri meant here, UriContent would match this.
                        uri=content.additional_properties.get("uri", "af://binary")
                        if content.additional_properties
                        else "af://binary",  # type: ignore[reportArgumentType]
                    ),
                )
            return None
        case UriContent():
            return types.ResourceLink(
                type="resource_link",
                uri=content.uri,  # type: ignore[reportArgumentType]
                mimeType=content.media_type,
                name=content.additional_properties.get("name", "Unknown")
                if content.additional_properties
                else "Unknown",
            )
        case _:
            return None


def _chat_message_to_mcp_types(
    content: ChatMessage,
) -> list[types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink]:
    """Convert a ChatMessage to a list of MCP types."""
    messages: list[
        types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink
    ] = []
    for item in content.contents:
        mcp_content = _ai_content_to_mcp_types(item)
        if mcp_content:
            messages.append(mcp_content)
    return messages


def _get_input_model_from_mcp_prompt(prompt: types.Prompt) -> type[BaseModel]:
    """Creates a Pydantic model from a prompt's parameters."""
    # Check if 'arguments' is missing or empty
    if not prompt.arguments:
        return create_model(f"{prompt.name}_input")

    field_definitions: dict[str, Any] = {}
    for prompt_argument in prompt.arguments:
        # For prompts, all arguments are typically required and string type
        # unless specified otherwise in the prompt argument
        python_type = str  # Default type for prompt arguments

        # Create field definition for create_model
        if prompt_argument.required:
            field_definitions[prompt_argument.name] = (python_type, ...)
        else:
            field_definitions[prompt_argument.name] = (python_type, None)

    return create_model(f"{prompt.name}_input", **field_definitions)


def _get_input_model_from_mcp_tool(tool: types.Tool) -> type[BaseModel]:
    """Creates a Pydantic model from a tools parameters."""
    properties = tool.inputSchema.get("properties", None)
    required = tool.inputSchema.get("required", [])
    definitions = tool.inputSchema.get("$defs", {})

    # Check if 'properties' is missing or not a dictionary
    if not properties:
        return create_model(f"{tool.name}_input")

    def resolve_type(prop_details: dict[str, Any]) -> type:
        """Resolve JSON Schema type to Python type, handling $ref."""
        # Handle $ref by resolving the reference
        if "$ref" in prop_details:
            ref = prop_details["$ref"]
            # Extract the reference path (e.g., "#/$defs/CustomerIdParam" -> "CustomerIdParam")
            if ref.startswith("#/$defs/"):
                def_name = ref.split("/")[-1]
                if def_name in definitions:
                    # Resolve the reference and use its type
                    resolved = definitions[def_name]
                    return resolve_type(resolved)
            # If we can't resolve the ref, default to dict for safety
            return dict

        # Map JSON Schema types to Python types
        json_type = prop_details.get("type", "string")
        match json_type:
            case "integer":
                return int
            case "number":
                return float
            case "boolean":
                return bool
            case "array":
                return list
            case "object":
                return dict
            case _:
                return str  # default

    field_definitions: dict[str, Any] = {}
    for prop_name, prop_details in properties.items():
        prop_details = json.loads(prop_details) if isinstance(prop_details, str) else prop_details

        python_type = resolve_type(prop_details)
        description = prop_details.get("description", "")

        # Create field definition for create_model
        if prop_name in required:
            field_definitions[prop_name] = (
                (python_type, Field(description=description)) if description else (python_type, ...)
            )
        else:
            default_value = prop_details.get("default", None)
            field_definitions[prop_name] = (
                (python_type, Field(default=default_value, description=description))
                if description
                else (python_type, default_value)
            )

    return create_model(f"{tool.name}_input", **field_definitions)


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
        approval_mode: Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None = None,
        allowed_tools: Collection[str] | None = None,
        load_tools: bool = True,
        load_prompts: bool = True,
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
        self.load_prompts_flag = load_prompts
        self._exit_stack = AsyncExitStack()
        self.session = session
        self.request_timeout = request_timeout
        self.chat_client = chat_client
        self._functions: list[AIFunction[Any, Any]] = []
        self.is_connected: bool = False

    def __str__(self) -> str:
        return f"MCPTool(name={self.name}, description={self.description})"

    @property
    def functions(self) -> list[AIFunction[Any, Any]]:
        """Get the list of functions that are allowed."""
        if not self.allowed_tools:
            return self._functions
        return [func for func in self._functions if func.name in self.allowed_tools]

    async def connect(self) -> None:
        """Connect to the MCP server.

        Establishes a connection to the MCP server, initializes the session,
        and loads tools and prompts if configured to do so.

        Raises:
            ToolException: If connection or session initialization fails.
        """
        if not self.session:
            try:
                transport = await self._exit_stack.enter_async_context(self.get_mcp_client())
            except Exception as ex:
                await self._exit_stack.aclose()
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
                        read_timeout_seconds=timedelta(seconds=self.request_timeout) if self.request_timeout else None,
                        message_handler=self.message_handler,
                        logging_callback=self.logging_callback,
                        sampling_callback=self.sampling_callback,
                    )
                )
            except Exception as ex:
                await self._exit_stack.aclose()
                raise ToolException(
                    message="Failed to create MCP session. Please check your configuration.", inner_exception=ex
                ) from ex
            try:
                await session.initialize()
            except Exception as ex:
                await self._exit_stack.aclose()
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
        if self.load_prompts_flag:
            await self.load_prompts()

        if logger.level != logging.NOTSET:
            try:
                await self.session.set_logging_level(
                    next(level for level, value in LOG_LEVEL_MAPPING.items() if value == logger.level)
                )
            except Exception as exc:
                logger.warning("Failed to set log level to %s", logger.level, exc_info=exc)

    async def sampling_callback(
        self, context: RequestContext[ClientSession, Any], params: types.CreateMessageRequestParams
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
            messages.append(_mcp_prompt_message_to_chat_message(msg))
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
        mcp_contents = _chat_message_to_mcp_types(response.messages[0])
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
        message: RequestResponder[types.ServerRequest, types.ClientResult] | types.ServerNotification | Exception,
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
        them into AIFunction instances.

        Raises:
            ToolExecutionException: If the MCP server is not connected.
        """
        if not self.session:
            raise ToolExecutionException("MCP server not connected, please call connect() before using this method.")
        try:
            prompt_list = await self.session.list_prompts()
        except Exception as exc:
            logger.info(
                "Prompt could not be loaded, you can exclude trying to load, by setting: load_prompts=False",
                exc_info=exc,
            )
            prompt_list = None
        for prompt in prompt_list.prompts if prompt_list else []:
            local_name = _normalize_mcp_name(prompt.name)
            input_model = _get_input_model_from_mcp_prompt(prompt)
            approval_mode = self._determine_approval_mode(local_name)
            func: AIFunction[BaseModel, list[ChatMessage]] = AIFunction(
                func=partial(self.get_prompt, prompt.name),
                name=local_name,
                description=prompt.description or "",
                approval_mode=approval_mode,
                input_model=input_model,
            )
            self._functions.append(func)

    async def load_tools(self) -> None:
        """Load tools from the MCP server.

        Retrieves available tools from the connected MCP server and converts
        them into AIFunction instances.

        Raises:
            ToolExecutionException: If the MCP server is not connected.
        """
        if not self.session:
            raise ToolExecutionException("MCP server not connected, please call connect() before using this method.")
        try:
            tool_list = await self.session.list_tools()
        except Exception as exc:
            logger.info(
                "Tools could not be loaded, you can exclude trying to load, by setting: load_tools=False",
                exc_info=exc,
            )
            tool_list = None
        for tool in tool_list.tools if tool_list else []:
            local_name = _normalize_mcp_name(tool.name)
            input_model = _get_input_model_from_mcp_tool(tool)
            approval_mode = self._determine_approval_mode(local_name)
            # Create AIFunctions out of each tool
            func: AIFunction[BaseModel, list[Contents]] = AIFunction(
                func=partial(self.call_tool, tool.name),
                name=local_name,
                description=tool.description or "",
                approval_mode=approval_mode,
                input_model=input_model,
            )
            self._functions.append(func)

    async def close(self) -> None:
        """Disconnect from the MCP server.

        Closes the connection and cleans up resources.
        """
        await self._exit_stack.aclose()
        self.session = None
        self.is_connected = False

    @abstractmethod
    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP client.

        Returns:
            An async context manager for the MCP client transport.
        """
        pass

    async def call_tool(self, tool_name: str, **kwargs: Any) -> list[Contents]:
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
        if not self.session:
            raise ToolExecutionException("MCP server not connected, please call connect() before using this method.")
        if not self.load_tools_flag:
            raise ToolExecutionException(
                "Tools are not loaded for this server, please set load_tools=True in the constructor."
            )
        try:
            return _mcp_call_tool_result_to_ai_contents(await self.session.call_tool(tool_name, arguments=kwargs))
        except McpError as mcp_exc:
            raise ToolExecutionException(mcp_exc.error.message, inner_exception=mcp_exc) from mcp_exc
        except Exception as ex:
            raise ToolExecutionException(f"Failed to call tool '{tool_name}'.", inner_exception=ex) from ex

    async def get_prompt(self, prompt_name: str, **kwargs: Any) -> list[ChatMessage]:
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
        if not self.session:
            raise ToolExecutionException("MCP server not connected, please call connect() before using this method.")
        if not self.load_prompts_flag:
            raise ToolExecutionException(
                "Prompts are not loaded for this server, please set load_prompts=True in the constructor."
            )
        try:
            prompt_result = await self.session.get_prompt(prompt_name, arguments=kwargs)
            return [_mcp_prompt_message_to_chat_message(message) for message in prompt_result.messages]
        except McpError as mcp_exc:
            raise ToolExecutionException(mcp_exc.error.message, inner_exception=mcp_exc) from mcp_exc
        except Exception as ex:
            raise ToolExecutionException(f"Failed to call prompt '{prompt_name}'.", inner_exception=ex) from ex

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
            await self._exit_stack.aclose()
            raise ToolExecutionException("Failed to enter context manager.", inner_exception=ex) from ex

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any
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
        load_prompts: bool = True,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None = None,
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
            load_prompts: Whether to load prompts from the MCP server.
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
            load_prompts=load_prompts,
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
                headers={"Authorization": "Bearer token"},
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
        load_prompts: bool = True,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None = None,
        allowed_tools: Collection[str] | None = None,
        headers: dict[str, Any] | None = None,
        timeout: float | None = None,
        sse_read_timeout: float | None = None,
        terminate_on_close: bool | None = None,
        chat_client: "ChatClientProtocol | None" = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP streamable HTTP tool.

        Note:
            The arguments are used to create a streamable HTTP client.
            See ``mcp.client.streamable_http.streamablehttp_client`` for more details.
            Any extra arguments passed to the constructor will be passed to the
            streamable HTTP client constructor.

        Args:
            name: The name of the tool.
            url: The URL of the MCP server.

        Keyword Args:
            load_tools: Whether to load tools from the MCP server.
            load_prompts: Whether to load prompts from the MCP server.
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
            headers: The headers to send with the request.
            timeout: The timeout for the request.
            sse_read_timeout: The timeout for reading from the SSE stream.
            terminate_on_close: Close the transport when the MCP client is terminated.
            chat_client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the SSE client.
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
            load_prompts=load_prompts,
            request_timeout=request_timeout,
        )
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.sse_read_timeout = sse_read_timeout
        self.terminate_on_close = terminate_on_close
        self._client_kwargs = kwargs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP streamable HTTP client.

        Returns:
            An async context manager for the streamable HTTP client transport.
        """
        args: dict[str, Any] = {
            "url": self.url,
        }
        if self.headers:
            args["headers"] = self.headers
        if self.timeout is not None:
            args["timeout"] = self.timeout
        if self.sse_read_timeout is not None:
            args["sse_read_timeout"] = self.sse_read_timeout
        if self.terminate_on_close is not None:
            args["terminate_on_close"] = self.terminate_on_close
        if self._client_kwargs:
            args.update(self._client_kwargs)
        return streamablehttp_client(**args)


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
        load_prompts: bool = True,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None = None,
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
            load_prompts: Whether to load prompts from the MCP server.
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
            load_prompts=load_prompts,
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

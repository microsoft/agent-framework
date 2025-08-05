# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import re
import sys
from abc import abstractmethod
from collections.abc import Sequence
from contextlib import AsyncExitStack, _AsyncGeneratorContextManager  # type: ignore
from datetime import timedelta
from functools import partial
from typing import Any

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.websocket import websocket_client
from mcp.shared.context import RequestContext
from mcp.shared.exceptions import McpError
from mcp.shared.session import RequestResponder
from pydantic import create_model

from ._clients import ChatClient
from ._tools import AIFunction
from ._types import ChatMessage, ChatRole, DataContent, TextContent, UriContent
from .exceptions import FunctionException, FunctionExecutionException

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


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
    "MCPSseTools",
    "MCPStdioTools",
    "MCPStreamableHttpTools",
    "MCPWebsocketTools",
]


def _mcp_prompt_message_to_ai_content(
    mcp_type: types.PromptMessage | types.SamplingMessage,
) -> ChatMessage:
    """Convert a MCP container type to a Agent Framework type."""
    return ChatMessage(
        role=ChatRole(mcp_type.role),
        contents=[_mcp_content_types_to_ai_content(mcp_type.content)],  # type: ignore[call-arg]
        raw_representation=mcp_type,
    )


def _mcp_call_tool_result_to_ai_contents(
    mcp_type: types.CallToolResult,
) -> list[TextContent | DataContent | UriContent]:
    """Convert a MCP container type to a Agent Framework type."""
    return [_mcp_content_types_to_ai_content(item) for item in mcp_type.content]


def _mcp_content_types_to_ai_content(
    mcp_type: types.ImageContent | types.TextContent | types.AudioContent | types.EmbeddedResource | types.ResourceLink,
) -> TextContent | DataContent | UriContent:
    """Convert a MCP type to a Agent Framework type."""
    if isinstance(mcp_type, types.TextContent):
        return TextContent(text=mcp_type.text, raw_representation=mcp_type)
    if isinstance(mcp_type, (types.ImageContent, types.AudioContent)):
        return DataContent(uri=mcp_type.data, media_type=mcp_type.mimeType, raw_representation=mcp_type)
    if isinstance(mcp_type, types.ResourceLink):
        return UriContent(
            uri=str(mcp_type.uri), media_type=mcp_type.mimeType or "application/json", raw_representation=mcp_type
        )
    # subtypes of EmbeddedResource
    if isinstance(mcp_type.resource, types.TextResourceContents):
        return TextContent(
            text=mcp_type.resource.text,
            raw_representation=mcp_type,
            additional_properties=mcp_type.annotations.model_dump() if mcp_type.annotations else {},
        )
    return DataContent(
        uri=mcp_type.resource.blob,
        raw_representation=mcp_type,
        additional_properties=mcp_type.annotations.model_dump() if mcp_type.annotations else {},
    )


def _ai_content_to_mcp_content_types(
    content: ChatMessage | TextContent | DataContent | UriContent,
) -> Sequence[types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource]:
    """Convert a kernel content type to a MCP type."""
    if isinstance(content, TextContent):
        return [types.TextContent(type="text", text=content.text)]
    if isinstance(content, DataContent):
        if content.media_type and content.media_type.startswith("image/"):
            return [types.ImageContent(type="image", data=content.uri, mimeType=content.media_type)]
        if content.media_type and content.media_type.startswith("audio/"):
            return [types.AudioContent(type="audio", data=content.uri, mimeType=content.media_type)]
        if content.media_type and content.media_type.startswith("application/"):
            return [
                types.EmbeddedResource(
                    type="resource",
                    resource=types.BlobResourceContents(
                        blob=content.uri,
                        mimeType=content.media_type,
                        uri="sk://binary",  # type: ignore[reportArgumentType]
                    ),
                )
            ]
    if isinstance(content, UriContent):
        return [
            types.EmbeddedResource(
                type="resource",
                resource=types.BlobResourceContents(
                    uri=content.uri,  # type: ignore[reportArgumentType]
                    mimeType=content.media_type,
                    blob="",
                ),
            )
        ]
    if isinstance(content, ChatMessage):
        messages: list[types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource] = []
        for item in content.contents:
            if isinstance(item, (TextContent, DataContent, UriContent)):
                messages.extend(_ai_content_to_mcp_content_types(item))
            else:
                logger.debug("Unsupported content type: %s", type(item))
        return messages

    raise FunctionExecutionException(f"Unsupported content type: {type(content)}")


def _get_input_model_from_mcp_prompt(prompt: types.Prompt) -> type[Any]:
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


def _get_input_model_from_mcp_tool(tool: types.Tool) -> type[Any]:
    """Creates a Pydantic model from a tools parameters."""
    properties = tool.inputSchema.get("properties", None)
    required = tool.inputSchema.get("required", [])
    # Check if 'properties' is missing or not a dictionary
    if not properties:
        return create_model(f"{tool.name}_input")

    field_definitions: dict[str, Any] = {}
    for prop_name, prop_details in properties.items():
        prop_details = json.loads(prop_details) if isinstance(prop_details, str) else prop_details

        # Map JSON Schema types to Python types
        json_type = prop_details.get("type", "string")
        python_type: type = str  # default
        if json_type == "integer":
            python_type = int
        elif json_type == "number":
            python_type = float
        elif json_type == "boolean":
            python_type = bool
        elif json_type == "array":
            python_type = list
        elif json_type == "object":
            python_type = dict

        # Create field definition for create_model
        if prop_name in required:
            field_definitions[prop_name] = (python_type, ...)
        else:
            default_value = prop_details.get("default", None)
            field_definitions[prop_name] = (python_type, default_value)

    return create_model(f"{tool.name}_input", **field_definitions)


def _normalize_mcp_name(name: str) -> str:
    """Normalize MCP tool/prompt names to allowed identifier pattern (A-Za-z0-9_.-)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name)


# region: MCP Plugin


class MCPBase:
    """MCP Base."""

    def __init__(
        self,
        name: str,
        description: str | None = None,
        load_tools: bool = True,
        load_prompts: bool = True,
        session: ClientSession | None = None,
        request_timeout: int | None = None,
        chat_client: ChatClient | None = None,
    ) -> None:
        """Initialize the MCP Plugin Base."""
        self.name = name
        self.description = description
        self.load_tools_flag = load_tools
        self.load_prompts_flag = load_prompts
        self._exit_stack = AsyncExitStack()
        self.session = session
        self.request_timeout = request_timeout
        self.chat_client = chat_client
        self.functions: dict[str, AIFunction[Any, Any]] = {}

    async def connect(self) -> None:
        """Connect to the MCP server."""
        if not self.session:
            try:
                transport = await self._exit_stack.enter_async_context(self.get_mcp_client())
            except Exception as ex:
                await self._exit_stack.aclose()
                raise FunctionException("Failed to connect to the MCP server. Please check your configuration.") from ex
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
                raise FunctionException(
                    "Failed to create a session. Please check your configuration.",
                ) from ex
            await session.initialize()
            self.session = session
        elif self.session._request_id == 0:  # type: ignore[reportPrivateUsage]
            # If the session is not initialized, we need to reinitialize it
            await self.session.initialize()
        logger.debug("Connected to MCP server: %s", self.session)
        if self.load_tools_flag:
            await self.load_tools()
        if self.load_prompts_flag:
            await self.load_prompts()

        if logger.level != logging.NOTSET:
            try:
                await self.session.set_logging_level(
                    next(level for level, value in LOG_LEVEL_MAPPING.items() if value == logger.level)
                )
            except Exception:
                logger.warning("Failed to set log level to %s", logger.level)

    async def sampling_callback(
        self, context: RequestContext[ClientSession, Any], params: types.CreateMessageRequestParams
    ) -> types.CreateMessageResult | types.ErrorData:
        """Callback function for sampling.

        This function is called when the MCP server needs to get a message completed.

        This is a simple version of this function, it can be overridden to allow more complex sampling.
        It get's added to the session at initialization time, so overriding it is the best way to do this.
        """
        if not self.chat_client:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="No chat client available. Please set a chat client.",
            )
        logger.debug("Sampling callback called with params: %s", params)
        messages: list[ChatMessage] = []
        for msg in params.messages:
            messages.append(_mcp_prompt_message_to_ai_content(msg))
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
        mcp_contents = _ai_content_to_mcp_content_types(response.messages[0])
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
            model=response.ai_model_id or "unknown",
        )

    async def logging_callback(self, params: types.LoggingMessageNotificationParams) -> None:
        """Callback function for logging.

        This function is called when the MCP Server sends a log message.
        By default it will log the message to the logger with the level set in the params.

        Please subclass the MCP*Plugin and override this function if you want to adapt the behavior.
        """
        logger.log(LOG_LEVEL_MAPPING[params.level], params.data)

    async def message_handler(
        self,
        message: RequestResponder[types.ServerRequest, types.ClientResult] | types.ServerNotification | Exception,
    ) -> None:
        """Handle messages from the MCP server.

        By default this function will handle exceptions on the server, by logging those.

        And it will trigger a reload of the tools and prompts when the list changed notification is received.

        If you want to extend this behavior you can subclass the MCPPlugin and override this function,
        if you want to keep the default behavior, make sure to call `super().message_handler(message)`.
        """
        if isinstance(message, Exception):
            logger.error("Error from MCP server: %s", message)
            return
        if isinstance(message, types.ServerNotification):
            match message.root.method:
                case "notifications/tools/list_changed":
                    await self.load_tools()
                case "notifications/prompts/list_changed":
                    await self.load_prompts()
                case _:
                    logger.debug("Unhandled notification: %s", message.root.method)

    async def load_prompts(self):
        """Load prompts from the MCP server."""
        if not self.session:
            raise FunctionExecutionException(
                "MCP server not connected, please call connect() before using this method."
            )
        try:
            prompt_list = await self.session.list_prompts()
        except Exception:
            prompt_list = None
        for prompt in prompt_list.prompts if prompt_list else []:
            local_name = _normalize_mcp_name(prompt.name)
            input_model = _get_input_model_from_mcp_prompt(prompt)
            func = AIFunction(
                func=partial(self.get_prompt, prompt.name),
                name=local_name,
                description=prompt.description or "",
                input_model=input_model,
            )
            self.functions[local_name] = func

    async def load_tools(self):
        """Load tools from the MCP server."""
        if not self.session:
            raise FunctionExecutionException(
                "MCP server not connected, please call connect() before using this method."
            )
        try:
            tool_list = await self.session.list_tools()
        except Exception:
            tool_list = None
            # Create methods with the kernel_function decorator for each tool
        for tool in tool_list.tools if tool_list else []:
            local_name = _normalize_mcp_name(tool.name)
            input_model = _get_input_model_from_mcp_tool(tool)
            func = AIFunction(
                func=partial(self.call_tool, tool.name),
                name=local_name,
                description=tool.description,
                input_model=input_model,
            )
            self.functions[local_name] = func

    async def close(self) -> None:
        """Disconnect from the MCP server."""
        await self._exit_stack.aclose()
        self.session = None

    @abstractmethod
    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP client."""
        pass

    async def call_tool(self, tool_name: str, **kwargs: Any) -> list[TextContent | DataContent | UriContent]:
        """Call a tool with the given arguments."""
        if not self.session:
            raise FunctionExecutionException(
                "MCP server not connected, please call connect() before using this method."
            )
        if not self.load_tools_flag:
            raise FunctionExecutionException(
                "Tools are not loaded for this server, please set load_tools=True in the constructor."
            )
        try:
            return _mcp_call_tool_result_to_ai_contents(await self.session.call_tool(tool_name, arguments=kwargs))
        except McpError:
            raise
        except Exception as ex:
            raise FunctionExecutionException(f"Failed to call tool '{tool_name}'.") from ex

    async def get_prompt(self, prompt_name: str, **kwargs: Any) -> list[ChatMessage]:
        """Call a prompt with the given arguments."""
        if not self.session:
            raise FunctionExecutionException(
                "MCP server not connected, please call connect() before using this method."
            )
        if not self.load_prompts_flag:
            raise FunctionExecutionException(
                "Prompts are not loaded for this server, please set load_prompts=True in the constructor."
            )
        try:
            prompt_result = await self.session.get_prompt(prompt_name, arguments=kwargs)
            return [_mcp_prompt_message_to_ai_content(message) for message in prompt_result.messages]
        except McpError:
            raise
        except Exception as ex:
            raise FunctionExecutionException(f"Failed to call prompt '{prompt_name}'.") from ex

    async def __aenter__(self) -> Self:
        """Enter the context manager."""
        try:
            await self.connect()
            return self
        except FunctionException:
            raise
        except Exception as ex:
            await self._exit_stack.aclose()
            raise FunctionExecutionException("Failed to enter context manager.") from ex

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any
    ) -> None:
        """Exit the context manager."""
        await self.close()


# region: MCP Plugin Implementations


class MCPStdioTools(MCPBase):
    """MCP stdio server configuration."""

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
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        encoding: str | None = None,
        chat_client: ChatClient | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP stdio plugin.

        The arguments are used to create a StdioServerParameters object.
        Which is then used to create a stdio client.
        see mcp.client.stdio.stdio_client and mcp.client.stdio.stdio_server_parameters
        for more details.

        Args:
            name: The name of the plugin.
            command: The command to run the MCP server.
            load_tools: Whether to load tools from the MCP server.
            load_prompts: Whether to load prompts from the MCP server.
            request_timeout: The default timeout used for all requests.
            session: The session to use for the MCP connection.
            description: The description of the plugin.
            args: The arguments to pass to the command.
            env: The environment variables to set for the command.
            encoding: The encoding to use for the command output.
            chat_client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the stdio client.

        """
        super().__init__(
            name=name,
            description=description,
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
        """Get an MCP stdio client."""
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


class MCPSseTools(MCPBase):
    """MCP sse server configuration."""

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
        headers: dict[str, Any] | None = None,
        timeout: float | None = None,
        sse_read_timeout: float | None = None,
        chat_client: ChatClient | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP sse plugin.

                The arguments are used to create a sse client.
        see mcp.client.sse.sse_client for more details.

        Any extra arguments passed to the constructor will be passed to the
        sse client constructor.

        Args:
            name: The name of the plugin.
            url: The URL of the MCP server.
            load_tools: Whether to load tools from the MCP server.
            load_prompts: Whether to load prompts from the MCP server.
            request_timeout: The default timeout used for all requests.
            session: The session to use for the MCP connection.
            description: The description of the plugin.
            headers: The headers to send with the request.
            timeout: The timeout for the request.
            sse_read_timeout: The timeout for reading from the SSE stream.
            chat_client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the sse client.

        """
        super().__init__(
            name=name,
            description=description,
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
        self._client_kwargs = kwargs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP SSE client."""
        args: dict[str, Any] = {
            "url": self.url,
        }
        if self.headers:
            args["headers"] = self.headers
        if self.timeout is not None:
            args["timeout"] = self.timeout
        if self.sse_read_timeout is not None:
            args["sse_read_timeout"] = self.sse_read_timeout
        if self._client_kwargs:
            args.update(self._client_kwargs)
        return sse_client(**args)


class MCPStreamableHttpTools(MCPBase):
    """MCP streamable http server configuration."""

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
        headers: dict[str, Any] | None = None,
        timeout: float | None = None,
        sse_read_timeout: float | None = None,
        terminate_on_close: bool | None = None,
        chat_client: ChatClient | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP streamable http plugin.

        The arguments are used to create a streamable http client.
        see mcp.client.streamable_http.streamablehttp_client for more details.

        Any extra arguments passed to the constructor will be passed to the
        streamable http client constructor.

        Args:
            name: The name of the plugin.
            url: The URL of the MCP server.
            load_tools: Whether to load tools from the MCP server.
            load_prompts: Whether to load prompts from the MCP server.
            request_timeout: The default timeout used for all requests.
            session: The session to use for the MCP connection.
            description: The description of the plugin.
            headers: The headers to send with the request.
            timeout: The timeout for the request.
            sse_read_timeout: The timeout for reading from the SSE stream.
            terminate_on_close: Close the transport when the MCP client is terminated.
            chat_client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the sse client.
        """
        super().__init__(
            name=name,
            description=description,
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
        """Get an MCP streamable http client."""
        args: dict[str, Any] = {
            "url": self.url,
        }
        if self.headers:
            args["headers"] = self.headers
        if self.timeout:
            args["timeout"] = self.timeout
        if self.sse_read_timeout:
            args["sse_read_timeout"] = self.sse_read_timeout
        if self.terminate_on_close is not None:
            args["terminate_on_close"] = self.terminate_on_close
        if self._client_kwargs:
            args.update(self._client_kwargs)
        return streamablehttp_client(**args)


class MCPWebsocketTools(MCPBase):
    """MCP websocket server configuration."""

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
        chat_client: ChatClient | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP websocket plugin.

                The arguments are used to create a websocket client.
        see mcp.client.websocket.websocket_client for more details.

        Any extra arguments passed to the constructor will be passed to the
        websocket client constructor.

        Args:
            name: The name of the plugin.
            url: The URL of the MCP server.
            load_tools: Whether to load tools from the MCP server.
            load_prompts: Whether to load prompts from the MCP server.
            request_timeout: The default timeout used for all requests.
            session: The session to use for the MCP connection.
            description: The description of the plugin.
            chat_client: The chat client to use for sampling.
            kwargs: Any extra arguments to pass to the websocket client.

        """
        super().__init__(
            name=name,
            description=description,
            session=session,
            chat_client=chat_client,
            load_tools=load_tools,
            load_prompts=load_prompts,
            request_timeout=request_timeout,
        )
        self.url = url
        self._client_kwargs = kwargs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP websocket client."""
        args: dict[str, Any] = {
            "url": self.url,
        }
        if self._client_kwargs:
            args.update(self._client_kwargs)
        return websocket_client(**args)

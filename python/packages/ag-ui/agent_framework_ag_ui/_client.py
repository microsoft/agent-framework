# Copyright (c) Microsoft. All rights reserved.

"""AG-UI Chat Client implementation."""

import json
import logging
import sys
import uuid
from collections.abc import AsyncIterable, MutableSequence
from functools import wraps
from typing import TYPE_CHECKING, Any, Generic, cast

import httpx
from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionTool,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework.observability import use_instrumentation

from ._event_converters import AGUIEventConverter
from ._http_service import AGUIHttpService
from ._message_adapters import agent_framework_messages_to_agui
from ._utils import convert_tools_to_agui_format

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self, TypedDict  # pragma: no cover
else:
    from typing_extensions import Self, TypedDict  # pragma: no cover

if TYPE_CHECKING:
    from ._types import AGUIChatOptions

logger: logging.Logger = logging.getLogger(__name__)


def _unwrap_server_function_call_contents(contents: MutableSequence[Content | dict[str, Any]]) -> None:
    """Replace server_function_call instances with their underlying call content."""
    for idx, content in enumerate(contents):
        if content.type == "server_function_call":  # type: ignore[union-attr]
            contents[idx] = content.function_call  # type: ignore[assignment, union-attr]


TBaseChatClient = TypeVar("TBaseChatClient", bound=type[BaseChatClient[Any]])

TAGUIChatOptions = TypeVar(
    "TAGUIChatOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AGUIChatOptions",
    covariant=True,
)


def _apply_server_function_call_unwrap(chat_client: TBaseChatClient) -> TBaseChatClient:
    """Class decorator that unwraps server-side function calls after tool handling."""

    original_get_streaming_response = chat_client.get_streaming_response

    @wraps(original_get_streaming_response)
    async def streaming_wrapper(self: Any, *args: Any, **kwargs: Any) -> AsyncIterable[ChatResponseUpdate]:
        async for update in original_get_streaming_response(self, *args, **kwargs):
            _unwrap_server_function_call_contents(cast(MutableSequence[Content | dict[str, Any]], update.contents))
            yield update

    chat_client.get_streaming_response = streaming_wrapper  # type: ignore[assignment]

    original_get_response = chat_client.get_response

    @wraps(original_get_response)
    async def response_wrapper(self: Any, *args: Any, **kwargs: Any) -> ChatResponse:
        response: ChatResponse[Any] = await original_get_response(self, *args, **kwargs)  # type: ignore[var-annotated]
        if response.messages:
            for message in response.messages:
                _unwrap_server_function_call_contents(cast(MutableSequence[Content | dict[str, Any]], message.contents))
        return response

    chat_client.get_response = response_wrapper  # type: ignore[assignment]
    return chat_client


@_apply_server_function_call_unwrap
@use_function_invocation
@use_instrumentation
@use_chat_middleware
class AGUIChatClient(BaseChatClient[TAGUIChatOptions], Generic[TAGUIChatOptions]):
    """Chat client for communicating with AG-UI compliant servers.

    This client implements the BaseChatClient interface and automatically handles:
    - Thread ID management for conversation continuity
    - State synchronization between client and server
    - Server-Sent Events (SSE) streaming
    - Event conversion to Agent Framework types

    Important: Message History Management
        This client sends exactly the messages it receives to the server. It does NOT
        automatically maintain conversation history. The server must handle history via thread_id.

        For stateless servers: Use ChatAgent wrapper which will send full message history on each
        request. However, even with ChatAgent, the server must echo back all context for the
        agent to maintain history across turns.

    Important: Tool Handling (Hybrid Execution - matches .NET)
        1. Client tool metadata sent to server - LLM knows about both client and server tools
        2. Server has its own tools that execute server-side
        3. When LLM calls a client tool, @use_function_invocation executes it locally
        4. Both client and server tools work together (hybrid pattern)

        The wrapping ChatAgent's @use_function_invocation handles client tool execution
        automatically when the server's LLM decides to call them.

    Examples:
        Direct usage (server manages thread history):

        .. code-block:: python

            from agent_framework.ag_ui import AGUIChatClient

            client = AGUIChatClient(endpoint="http://localhost:8888/")

            # First message - thread ID auto-generated
            response = await client.get_response("Hello!")
            thread_id = response.additional_properties.get("thread_id")

            # Second message - server retrieves history using thread_id
            response2 = await client.get_response(
                "How are you?",
                metadata={"thread_id": thread_id}
            )

        Recommended usage with ChatAgent (client manages history):

        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework.ag_ui import AGUIChatClient

            client = AGUIChatClient(endpoint="http://localhost:8888/")
            agent = ChatAgent(name="assistant", client=client)
            thread = await agent.get_new_thread()

            # ChatAgent automatically maintains history and sends full context
            response = await agent.run("Hello!", thread=thread)
            response2 = await agent.run("How are you?", thread=thread)

        Streaming usage:

        .. code-block:: python

            async for update in client.get_streaming_response("Tell me a story"):
                if update.contents:
                    for content in update.contents:
                        if hasattr(content, "text"):
                            print(content.text, end="", flush=True)

        Context manager:

        .. code-block:: python

            async with AGUIChatClient(endpoint="http://localhost:8888/") as client:
                response = await client.get_response("Hello!")
                print(response.messages[0].text)

        Using custom ChatOptions with type safety:

        .. code-block:: python

            from typing import TypedDict
            from agent_framework_ag_ui import AGUIChatClient, AGUIChatOptions

            class MyOptions(AGUIChatOptions, total=False):
                my_custom_option: str

            client: AGUIChatClient[MyOptions] = AGUIChatClient(endpoint="http://localhost:8888/")
            response = await client.get_response("Hello", options={"my_custom_option": "value"})
    """

    OTEL_PROVIDER_NAME = "agui"

    def __init__(
        self,
        *,
        endpoint: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the AG-UI chat client.

        Args:
            endpoint: The AG-UI server endpoint URL (e.g., "http://localhost:8888/")
            http_client: Optional httpx.AsyncClient instance. If None, one will be created.
            timeout: Request timeout in seconds (default: 60.0)
            additional_properties: Additional properties to store
            **kwargs: Additional arguments passed to BaseChatClient
        """
        super().__init__(additional_properties=additional_properties, **kwargs)
        self._http_service = AGUIHttpService(
            endpoint=endpoint,
            http_client=http_client,
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_service.close()

    async def __aenter__(self) -> Self:
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()

    def _register_server_tool_placeholder(self, tool_name: str) -> None:
        """Register a declaration-only placeholder so function invocation skips execution."""

        config = getattr(self, "function_invocation_configuration", None)
        if not config:
            return
        if any(getattr(tool, "name", None) == tool_name for tool in config.additional_tools):
            return

        placeholder: FunctionTool[Any, Any] = FunctionTool(
            name=tool_name,
            description="Server-managed tool placeholder (AG-UI)",
            func=None,
        )
        config.additional_tools = list(config.additional_tools) + [placeholder]
        registered: set[str] = getattr(self, "_registered_server_tools", set())
        registered.add(tool_name)
        self._registered_server_tools = registered  # type: ignore[attr-defined]
        from agent_framework._logging import get_logger

        logger = get_logger()
        logger.debug(f"[AGUIChatClient] Registered server placeholder: {tool_name}")

    def _extract_state_from_messages(
        self, messages: MutableSequence[ChatMessage]
    ) -> tuple[list[ChatMessage], dict[str, Any] | None]:
        """Extract state from last message if present.

        Args:
            messages: List of chat messages

        Returns:
            Tuple of (messages_without_state, state_dict)
        """
        if not messages:
            return list(messages), None

        last_message = messages[-1]

        for content in last_message.contents:
            if isinstance(content, Content) and content.type == "data" and content.media_type == "application/json":
                try:
                    uri = content.uri
                    if uri.startswith("data:application/json;base64,"):  # type: ignore[union-attr]
                        import base64

                        encoded_data = uri.split(",", 1)[1]  # type: ignore[union-attr]
                        decoded_bytes = base64.b64decode(encoded_data)
                        state = json.loads(decoded_bytes.decode("utf-8"))

                        messages_without_state = list(messages[:-1]) if len(messages) > 1 else []
                        return messages_without_state, state
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    from agent_framework._logging import get_logger

                    logger = get_logger()
                    logger.warning(f"Failed to extract state from message: {e}")

        return list(messages), None

    def _convert_messages_to_agui_format(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert Agent Framework messages to AG-UI format.

        Args:
            messages: List of ChatMessage objects

        Returns:
            List of AG-UI formatted message dictionaries
        """
        return agent_framework_messages_to_agui(messages)

    def _get_thread_id(self, options: dict[str, Any]) -> str:
        """Get or generate thread ID from chat options.

        Args:
            options: Chat options containing metadata

        Returns:
            Thread ID string
        """
        thread_id = None
        metadata = options.get("metadata")
        if metadata:
            thread_id = metadata.get("thread_id")

        if not thread_id:
            thread_id = f"thread_{uuid.uuid4().hex}"

        return thread_id

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        """Internal method to get non-streaming response.

        Keyword Args:
            messages: List of chat messages
            options: Chat options for the request
            **kwargs: Additional keyword arguments

        Returns:
            ChatResponse object
        """
        return await ChatResponse.from_chat_response_generator(
            self._inner_get_streaming_response(
                messages=messages,
                options=options,
                **kwargs,
            )
        )

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Internal method to get streaming response.

        Keyword Args:
            messages: List of chat messages
            options: Chat options for the request
            **kwargs: Additional keyword arguments

        Yields:
            ChatResponseUpdate objects
        """
        messages_to_send, state = self._extract_state_from_messages(messages)

        thread_id = self._get_thread_id(options)
        run_id = f"run_{uuid.uuid4().hex}"

        agui_messages = self._convert_messages_to_agui_format(messages_to_send)

        # Send client tools to server so LLM knows about them
        # Client tools execute via ChatAgent's @use_function_invocation wrapper
        agui_tools = convert_tools_to_agui_format(options.get("tools"))

        # Build set of client tool names (matches .NET clientToolSet)
        # Used to distinguish client vs server tools in response stream
        client_tool_set: set[str] = set()
        tools = options.get("tools")
        if tools:
            for tool in tools:
                if hasattr(tool, "name"):
                    client_tool_set.add(tool.name)  # type: ignore[arg-type]
        self._last_client_tool_set = client_tool_set  # type: ignore[attr-defined]

        logger.debug(
            "[AGUIChatClient] Preparing request",
            extra={
                "thread_id": thread_id,
                "run_id": run_id,
                "client_tools": list(client_tool_set),
                "messages": [msg.text for msg in messages_to_send if msg.text],
            },
        )
        logger.debug(f"[AGUIChatClient] Client tool set: {client_tool_set}")

        converter = AGUIEventConverter()

        async for event in self._http_service.post_run(
            thread_id=thread_id,
            run_id=run_id,
            messages=agui_messages,
            state=state,
            tools=agui_tools,
        ):
            logger.debug(f"[AGUIChatClient] Raw AG-UI event: {event}")
            update = converter.convert_event(event)
            if update is not None:
                logger.debug(
                    "[AGUIChatClient] Converted update",
                    extra={"role": update.role, "contents": [type(c).__name__ for c in update.contents]},
                )
                # Distinguish client vs server tools
                for i, content in enumerate(update.contents):
                    if content.type == "function_call":  # type: ignore[attr-defined]
                        logger.debug(
                            f"[AGUIChatClient] Function call: {content.name}, in client_tool_set: {content.name in client_tool_set}"  # type: ignore[attr-defined]
                        )
                        if content.name in client_tool_set:  # type: ignore[attr-defined]
                            # Client tool - let @use_function_invocation execute it
                            if not content.additional_properties:  # type: ignore[attr-defined]
                                content.additional_properties = {}  # type: ignore[attr-defined]
                            content.additional_properties["agui_thread_id"] = thread_id  # type: ignore[attr-defined]
                        else:
                            # Server tool - wrap so @use_function_invocation ignores it
                            logger.debug(f"[AGUIChatClient] Wrapping server tool: {content.name}")  # type: ignore[union-attr]
                            self._register_server_tool_placeholder(content.name)  # type: ignore[arg-type]
                            update.contents[i] = Content(type="server_function_call", function_call=content)  # type: ignore

                yield update

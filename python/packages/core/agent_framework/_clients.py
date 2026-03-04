# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from collections.abc import (
    AsyncIterable,
    Awaitable,
    Callable,
    Mapping,
    Sequence,
)
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
    Protocol,
    TypedDict,
    cast,
    overload,
    runtime_checkable,
)

from pydantic import BaseModel

from ._serialization import SerializationMixin
from ._tools import (
    FunctionInvocationConfiguration,
    ToolTypes,
)
from ._types import (
    ChatResponse,
    ChatResponseUpdate,
    EmbeddingGenerationOptions,
    EmbeddingInputT,
    EmbeddingT,
    GeneratedEmbeddings,
    Message,
    ResponseStream,
    validate_chat_options,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover


if TYPE_CHECKING:
    from ._agents import Agent
    from ._middleware import (
        MiddlewareTypes,
    )
    from ._types import ChatOptions


InputT = TypeVar("InputT", contravariant=True)

BaseChatClientT = TypeVar("BaseChatClientT", bound="BaseChatClient")

logger = logging.getLogger("agent_framework")


# region SupportsChatGetResponse Protocol

# Contravariant for the Protocol
OptionsContraT = TypeVar(
    "OptionsContraT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    contravariant=True,
)

# Used for the overloads that capture the response model type from options
ResponseModelBoundT = TypeVar("ResponseModelBoundT", bound=BaseModel)


@runtime_checkable
class SupportsChatGetResponse(Protocol[OptionsContraT]):
    """A protocol for a chat client that can generate responses.

    This protocol defines the interface that all chat clients must implement,
    including methods for generating both streaming and non-streaming responses.

    The generic type parameter TOptions specifies which options TypedDict this
    client accepts, enabling IDE autocomplete and type checking for provider-specific
    options.

    Note:
        Protocols use structural subtyping (duck typing). Classes don't need
        to explicitly inherit from this protocol to be considered compatible.

    Examples:
        .. code-block:: python

            from agent_framework import SupportsChatGetResponse, ChatResponse, Message


            # Any class implementing the required methods is compatible
            class CustomChatClient:
                additional_properties: dict = {}

                def get_response(self, messages, *, stream=False, **kwargs):
                    if stream:
                        from agent_framework import ChatResponseUpdate, ResponseStream

                        async def _stream():
                            yield ChatResponseUpdate()

                        return ResponseStream(_stream())
                    else:

                        async def _response():
                            return ChatResponse(messages=[], response_id="custom")

                        return _response()


            # Verify the instance satisfies the protocol
            client = CustomChatClient()
            assert isinstance(client, SupportsChatGetResponse)
    """

    additional_properties: dict[str, Any]

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OptionsContraT | ChatOptions[None] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OptionsContraT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OptionsContraT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Send input and return the response.

        Args:
            messages: The sequence of input messages to send.
            stream: Whether to stream the response. Defaults to False.
            options: Chat options as a TypedDict.
            **kwargs: Additional chat options.

        Returns:
            When stream=False: An awaitable ChatResponse from the client.
            When stream=True: A ResponseStream yielding partial updates.

        Raises:
            ValueError: If the input message sequence is ``None``.
        """
        ...


# endregion


# region ChatClientBase

# Covariant for the BaseChatClient
OptionsCoT = TypeVar(
    "OptionsCoT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    covariant=True,
)


class BaseChatClient(SerializationMixin, ABC, Generic[OptionsCoT]):
    """Abstract base class for chat clients without middleware wrapping.

    This abstract base class provides core functionality for chat client implementations,
    including message preparation and tool normalization, but without middleware,
    telemetry, or function invocation support.

    The generic type parameter TOptions specifies which options TypedDict this client
    accepts. This enables IDE autocomplete and type checking for provider-specific options
    when using the typed overloads of get_response.

    Note:
        BaseChatClient cannot be instantiated directly as it's an abstract base class.
        Subclasses must implement ``_inner_get_response()`` with a stream parameter to handle both
        streaming and non-streaming responses.

        For full-featured clients with middleware, telemetry, and function invocation support,
        use the public client classes (e.g., ``OpenAIChatClient``, ``OpenAIResponsesClient``)
        which compose these layers correctly.

    Examples:
        .. code-block:: python

            from agent_framework import BaseChatClient, ChatResponse, Message
            from collections.abc import AsyncIterable


            class CustomChatClient(BaseChatClient):
                async def _inner_get_response(self, *, messages, stream, options, **kwargs):
                    if stream:
                        # Streaming implementation
                        from agent_framework import ChatResponseUpdate

                        async def _stream():
                            yield ChatResponseUpdate(role="assistant", contents=[{"type": "text", "text": "Hello!"}])

                        return _stream()
                    else:
                        # Non-streaming implementation
                        return ChatResponse(
                            messages=[Message(role="assistant", text="Hello!")], response_id="custom-response"
                        )


            # Create an instance of your custom client
            client = CustomChatClient()

            # Use the client to get responses
            response = await client.get_response([Message(role="user", text="Hello, how are you?")])
            # Or stream responses
            async for update in client.get_response([Message(role="user", text="Hello!")], stream=True):
                print(update)
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "unknown"
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}
    STORES_BY_DEFAULT: ClassVar[bool] = False
    """Whether this client stores conversation history server-side by default.

    Clients that use server-side storage (e.g., OpenAI Responses API with ``store=True``
    as default, Azure AI Agent sessions) should override this to ``True``.
    When ``True``, the agent skips auto-injecting ``InMemoryHistoryProvider`` unless the
    user explicitly sets ``store=False``.
    """
    # OTEL_PROVIDER_NAME is used for OTel setup, should be overridden in subclasses

    def __init__(
        self,
        *,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a BaseChatClient instance.

        Keyword Args:
            additional_properties: Additional properties for the client.
            kwargs: Additional keyword arguments (merged into additional_properties).
        """
        self.additional_properties = additional_properties or {}
        super().__init__(**kwargs)

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Convert the instance to a dictionary.

        Extracts additional_properties fields to the root level.

        Keyword Args:
            exclude: Set of field names to exclude from serialization.
            exclude_none: Whether to exclude None values from the output. Defaults to True.

        Returns:
            Dictionary representation of the instance.
        """
        # Get the base dict from SerializationMixin
        result = super().to_dict(exclude=exclude, exclude_none=exclude_none)

        # Extract additional_properties to root level
        if self.additional_properties:
            result.update(self.additional_properties)

        return result

    async def _validate_options(self, options: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and normalize chat options.

        Subclasses should call this at the start of _inner_get_response to validate options.

        Args:
            options: The raw options dict.

        Returns:
            The validated and normalized options dict.
        """
        return await validate_chat_options(dict(options))

    def _finalize_response_updates(
        self,
        updates: Sequence[ChatResponseUpdate],
        *,
        response_format: Any | None = None,
    ) -> ChatResponse:
        """Finalize response updates into a single ChatResponse."""
        output_format_type = response_format if isinstance(response_format, type) else None
        return ChatResponse.from_updates(updates, output_format_type=output_format_type)

    def _build_response_stream(
        self,
        stream: AsyncIterable[ChatResponseUpdate] | Awaitable[AsyncIterable[ChatResponseUpdate]],
        *,
        response_format: Any | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Create a ResponseStream with the standard finalizer."""
        return ResponseStream(
            stream,
            finalizer=lambda updates: self._finalize_response_updates(updates, response_format=response_format),
        )

    # region Internal method to be implemented by derived classes

    @abstractmethod
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Send a chat request to the AI service.

        Subclasses must implement this method to handle both streaming and non-streaming
        responses based on the stream parameter. Implementations should call
        ``await self._validate_options(options)`` at the start to validate options.

        Keyword Args:
            messages: The prepared chat messages to send.
            stream: Whether to stream the response.
            options: The options dict for the request (call _validate_options first).
            kwargs: Any additional keyword arguments.

        Returns:
            When stream=False: An Awaitable ChatResponse from the model.
            When stream=True: A ResponseStream of ChatResponseUpdate instances.
        """

    # region Public method

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OptionsCoT | ChatOptions[None] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Get a response from a chat client.

        Args:
            messages: The message or messages to send to the model.
            stream: Whether to stream the response. Defaults to False.
            options: Chat options as a TypedDict.
            **kwargs: Other keyword arguments, can be used to pass function specific parameters.

        Returns:
            When streaming a response stream of ChatResponseUpdates, otherwise an Awaitable ChatResponse.
        """
        return self._inner_get_response(
            messages=messages,
            stream=stream,
            options=options or {},  # type: ignore[arg-type]
            **kwargs,
        )

    def service_url(self) -> str:
        """Get the URL of the service.

        Override this in the subclass to return the proper URL.
        If the service does not have a URL, return None.

        Returns:
            The service URL or 'Unknown' if not implemented.
        """
        return "Unknown"

    def as_agent(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsCoT | Mapping[str, Any] | None = None,
        context_providers: Sequence[Any] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> Agent[OptionsCoT]:
        """Create a Agent with this client.

        This is a convenience method that creates a Agent instance with this
        chat client already configured.

        Keyword Args:
            id: The unique identifier for the agent. Will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            instructions: Optional instructions for the agent.
                These will be put into the messages sent to the chat client service as a system message.
            tools: The tools to use for the request.
            default_options: A TypedDict containing chat options. When using a typed client like
                ``OpenAIChatClient``, this enables IDE autocomplete for provider-specific options
                including temperature, max_tokens, model_id, tool_choice, and more.
                Note: response_format typing does not flow into run outputs when set via default_options,
                and dict literals are accepted without specialized option typing.
            context_providers: Context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            function_invocation_configuration: Optional function invocation configuration override.
            kwargs: Any additional keyword arguments. Will be stored as ``additional_properties``.

        Returns:
            A Agent instance configured with this chat client.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIChatClient

                # Create a client
                client = OpenAIChatClient(model_id="gpt-4")

                # Create an agent using the convenience method
                agent = client.as_agent(
                    name="assistant",
                    instructions="You are a helpful assistant.",
                    default_options={"temperature": 0.7, "max_tokens": 500},
                )

                # Run the agent
                response = await agent.run("Hello!")
        """
        from ._agents import Agent

        return Agent(
            client=self,
            id=id,
            name=name,
            description=description,
            instructions=instructions,
            tools=tools,
            default_options=cast(Any, default_options),
            context_providers=context_providers,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            **kwargs,
        )


# endregion


# region Tool Support Protocols


@runtime_checkable
class SupportsCodeInterpreterTool(Protocol):
    """Protocol for clients that support code interpreter tools.

    This protocol enables runtime checking to determine if a client
    supports code interpreter functionality.

    Examples:
        .. code-block:: python

            from agent_framework import SupportsCodeInterpreterTool

            if isinstance(client, SupportsCodeInterpreterTool):
                tool = client.get_code_interpreter_tool()
                agent = ChatAgent(client, tools=[tool])
    """

    @staticmethod
    def get_code_interpreter_tool(**kwargs: Any) -> Any:
        """Create a code interpreter tool configuration.

        Keyword Args:
            **kwargs: Provider-specific configuration options.

        Returns:
            A tool configuration ready to pass to ChatAgent.
        """
        ...


@runtime_checkable
class SupportsWebSearchTool(Protocol):
    """Protocol for clients that support web search tools.

    This protocol enables runtime checking to determine if a client
    supports web search functionality.

    Examples:
        .. code-block:: python

            from agent_framework import SupportsWebSearchTool

            if isinstance(client, SupportsWebSearchTool):
                tool = client.get_web_search_tool()
                agent = ChatAgent(client, tools=[tool])
    """

    @staticmethod
    def get_web_search_tool(**kwargs: Any) -> Any:
        """Create a web search tool configuration.

        Keyword Args:
            **kwargs: Provider-specific configuration options.

        Returns:
            A tool configuration ready to pass to ChatAgent.
        """
        ...


@runtime_checkable
class SupportsImageGenerationTool(Protocol):
    """Protocol for clients that support image generation tools.

    This protocol enables runtime checking to determine if a client
    supports image generation functionality.

    Examples:
        .. code-block:: python

            from agent_framework import SupportsImageGenerationTool

            if isinstance(client, SupportsImageGenerationTool):
                tool = client.get_image_generation_tool()
                agent = ChatAgent(client, tools=[tool])
    """

    @staticmethod
    def get_image_generation_tool(**kwargs: Any) -> Any:
        """Create an image generation tool configuration.

        Keyword Args:
            **kwargs: Provider-specific configuration options.

        Returns:
            A tool configuration ready to pass to ChatAgent.
        """
        ...


@runtime_checkable
class SupportsMCPTool(Protocol):
    """Protocol for clients that support MCP (Model Context Protocol) tools.

    This protocol enables runtime checking to determine if a client
    supports MCP server connections.

    Examples:
        .. code-block:: python

            from agent_framework import SupportsMCPTool

            if isinstance(client, SupportsMCPTool):
                tool = client.get_mcp_tool(name="my_mcp", url="https://...")
                agent = ChatAgent(client, tools=[tool])
    """

    @staticmethod
    def get_mcp_tool(**kwargs: Any) -> Any:
        """Create an MCP tool configuration.

        Keyword Args:
            **kwargs: Provider-specific configuration options including
                name and url for the MCP server.

        Returns:
            A tool configuration ready to pass to ChatAgent.
        """
        ...


@runtime_checkable
class SupportsFileSearchTool(Protocol):
    """Protocol for clients that support file search tools.

    This protocol enables runtime checking to determine if a client
    supports file search functionality with vector stores.

    Examples:
        .. code-block:: python

            from agent_framework import SupportsFileSearchTool

            if isinstance(client, SupportsFileSearchTool):
                tool = client.get_file_search_tool(vector_store_ids=["vs_123"])
                agent = ChatAgent(client, tools=[tool])
    """

    @staticmethod
    def get_file_search_tool(**kwargs: Any) -> Any:
        """Create a file search tool configuration.

        Keyword Args:
            **kwargs: Provider-specific configuration options.

        Returns:
            A tool configuration ready to pass to ChatAgent.
        """
        ...


# endregion


# region SupportsGetEmbeddings Protocol

# Contravariant TypeVars for the Protocol
EmbeddingInputContraT = TypeVar(
    "EmbeddingInputContraT",
    default="str",
    contravariant=True,
)
EmbeddingOptionsContraT = TypeVar(
    "EmbeddingOptionsContraT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="EmbeddingGenerationOptions",
    contravariant=True,
)


@runtime_checkable
class SupportsGetEmbeddings(Protocol[EmbeddingInputContraT, EmbeddingT, EmbeddingOptionsContraT]):
    """Protocol for an embedding client that can generate embeddings.

    This protocol enables duck-typing for embedding generation. Any class that
    implements ``get_embeddings`` with a compatible signature satisfies this protocol.

    Generic over the input type (defaults to ``str``), output embedding type
    (defaults to ``list[float]``), and options type.

    Examples:
        .. code-block:: python

            from agent_framework import SupportsGetEmbeddings


            async def use_embeddings(client: SupportsGetEmbeddings) -> None:
                result = await client.get_embeddings(["Hello, world!"])
                for embedding in result:
                    print(embedding.vector)
    """

    additional_properties: dict[str, Any]

    def get_embeddings(
        self,
        values: Sequence[EmbeddingInputContraT],
        *,
        options: EmbeddingOptionsContraT | None = None,
    ) -> Awaitable[GeneratedEmbeddings[EmbeddingT]]:
        """Generate embeddings for the given values.

        Args:
            values: The values to generate embeddings for.
            options: Optional embedding generation options.

        Returns:
            Generated embeddings with metadata.
        """
        ...


# endregion


# region BaseEmbeddingClient

# Covariant for the BaseEmbeddingClient
EmbeddingOptionsT = TypeVar(
    "EmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="EmbeddingGenerationOptions",
    covariant=True,
)


class BaseEmbeddingClient(SerializationMixin, ABC, Generic[EmbeddingInputT, EmbeddingT, EmbeddingOptionsT]):
    """Abstract base class for embedding clients.

    Subclasses implement ``get_embeddings`` to provide the actual
    embedding generation logic.

    Generic over the input type (defaults to ``str``), output embedding type
    (defaults to ``list[float]``), and options type.

    Examples:
        .. code-block:: python

            from agent_framework import BaseEmbeddingClient, Embedding, GeneratedEmbeddings
            from collections.abc import Sequence


            class CustomEmbeddingClient(BaseEmbeddingClient):
                async def get_embeddings(self, values, *, options=None):
                    return GeneratedEmbeddings([Embedding(vector=[0.1, 0.2, 0.3]) for _ in values])
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "unknown"
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}

    def __init__(
        self,
        *,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a BaseEmbeddingClient instance.

        Args:
            additional_properties: Additional properties to pass to the client.
            **kwargs: Additional keyword arguments passed to parent classes (for MRO).
        """
        self.additional_properties = additional_properties or {}
        super().__init__(**kwargs)

    @abstractmethod
    async def get_embeddings(
        self,
        values: Sequence[EmbeddingInputT],
        *,
        options: EmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[EmbeddingT]:
        """Generate embeddings for the given values.

        Args:
            values: The values to generate embeddings for.
            options: Optional embedding generation options.

        Returns:
            Generated embeddings with metadata.
        """
        ...


# endregion

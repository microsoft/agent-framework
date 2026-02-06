# Copyright (c) Microsoft. All rights reserved.

import sys
from abc import ABC, abstractmethod
from collections.abc import (
    AsyncIterable,
    Awaitable,
    Callable,
    Mapping,
    MutableMapping,
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

from ._logging import get_logger
from ._memory import ContextProvider
from ._serialization import SerializationMixin
from ._threads import ChatMessageStoreProtocol
from ._tools import (
    FunctionInvocationConfiguration,
    ToolProtocol,
)
from ._types import (
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ResponseStream,
    prepare_messages,
    validate_chat_options,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover


if TYPE_CHECKING:
    from ._agents import ChatAgent
    from ._middleware import (
        MiddlewareTypes,
    )
    from ._types import ChatOptions


TInput = TypeVar("TInput", contravariant=True)

TEmbedding = TypeVar("TEmbedding")
TBaseChatClient = TypeVar("TBaseChatClient", bound="BaseChatClient")

logger = get_logger()

__all__ = [
    "BaseChatClient",
    "ChatClientProtocol",
]


# region ChatClientProtocol Protocol

# Contravariant for the Protocol
TOptions_contra = TypeVar(
    "TOptions_contra",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    contravariant=True,
)

# Used for the overloads that capture the response model type from options
TResponseModelT = TypeVar("TResponseModelT", bound=BaseModel)


@runtime_checkable
class ChatClientProtocol(Protocol[TOptions_contra]):
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

            from agent_framework import ChatClientProtocol, ChatResponse, ChatMessage


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
            assert isinstance(client, ChatClientProtocol)
    """

    additional_properties: dict[str, Any]

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[False] = ...,
        options: "ChatOptions[TResponseModelT]",
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[TResponseModelT]]: ...

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[False] = ...,
        options: "TOptions_contra | ChatOptions[None] | None" = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[True],
        options: "TOptions_contra | ChatOptions[Any] | None" = None,
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: bool = False,
        options: "TOptions_contra | ChatOptions[Any] | None" = None,
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
TOptions_co = TypeVar(
    "TOptions_co",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    covariant=True,
)


class BaseChatClient(SerializationMixin, ABC, Generic[TOptions_co]):
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

            from agent_framework import BaseChatClient, ChatResponse, ChatMessage
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
                            messages=[ChatMessage(role="assistant", text="Hello!")], response_id="custom-response"
                        )


            # Create an instance of your custom client
            client = CustomChatClient()

            # Use the client to get responses
            response = await client.get_response("Hello, how are you?")
            # Or stream responses
            async for update in client.get_response("Hello!", stream=True):
                print(update)
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "unknown"
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}
    # This is used for OTel setup, should be overridden in subclasses

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
        messages: Sequence[ChatMessage],
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
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[False] = ...,
        options: "ChatOptions[TResponseModelT]",
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[TResponseModelT]]: ...

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[False] = ...,
        options: "TOptions_co | ChatOptions[None] | None" = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[True],
        options: "TOptions_co | ChatOptions[Any] | None" = None,
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: bool = False,
        options: "TOptions_co | ChatOptions[Any] | None" = None,
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
        prepared_messages = prepare_messages(messages)
        return self._inner_get_response(
            messages=prepared_messages,
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
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        default_options: TOptions_co | Mapping[str, Any] | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStoreProtocol] | None = None,
        context_provider: ContextProvider | None = None,
        middleware: Sequence["MiddlewareTypes"] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> "ChatAgent[TOptions_co]":
        """Create a ChatAgent with this client.

        This is a convenience method that creates a ChatAgent instance with this
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
            chat_message_store_factory: Factory function to create an instance of ChatMessageStoreProtocol.
                If not provided, the default in-memory store will be used.
            context_provider: Context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            function_invocation_configuration: Optional function invocation configuration override.
            kwargs: Any additional keyword arguments. Will be stored as ``additional_properties``.

        Returns:
            A ChatAgent instance configured with this chat client.

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
        from ._agents import ChatAgent

        return ChatAgent(
            chat_client=self,
            id=id,
            name=name,
            description=description,
            instructions=instructions,
            tools=tools,
            default_options=cast(Any, default_options),
            chat_message_store_factory=chat_message_store_factory,
            context_provider=context_provider,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            **kwargs,
        )

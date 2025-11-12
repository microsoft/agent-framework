# Copyright (c) Microsoft. All rights reserved.

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Callable, MutableMapping, MutableSequence, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from ._logging import get_logger
from ._mcp import MCPTool
from ._memory import AggregateContextProvider, ContextProvider
from ._middleware import (
    ChatMiddleware,
    ChatMiddlewareCallable,
    FunctionMiddleware,
    FunctionMiddlewareCallable,
    Middleware,
)
from ._serialization import SerializationMixin
from ._threads import ChatMessageStoreProtocol
from ._tools import FUNCTION_INVOKING_CHAT_CLIENT_MARKER, FunctionInvocationConfiguration, ToolProtocol
from ._types import ChatMessage, ChatOptions, ChatResponse, ChatResponseUpdate, ToolMode, prepare_messages

if TYPE_CHECKING:
    from ._agents import ChatAgent


TInput = TypeVar("TInput", contravariant=True)
TEmbedding = TypeVar("TEmbedding")
TBaseChatClient = TypeVar("TBaseChatClient", bound="BaseChatClient")

logger = get_logger()

__all__ = [
    "BaseChatClient",
    "ChatClientProtocol",
]


# region ChatClientProtocol Protocol


@runtime_checkable
class ChatClientProtocol(Protocol):
    """A protocol for a chat client that can generate responses.

    This protocol defines the interface that all chat clients must implement,
    including methods for generating both streaming and non-streaming responses.

    Note:
        Protocols use structural subtyping (duck typing). Classes don't need
        to explicitly inherit from this protocol to be considered compatible.

    Examples:
        .. code-block:: python

            from agent_framework import ChatClientProtocol, ChatResponse, ChatMessage


            # Any class implementing the required methods is compatible
            class CustomChatClient:
                @property
                def additional_properties(self) -> dict[str, Any]:
                    return {}

                async def get_response(self, messages, **kwargs):
                    # Your custom implementation
                    return ChatResponse(messages=[], response_id="custom")

                def get_streaming_response(self, messages, **kwargs):
                    async def _stream():
                        from agent_framework import ChatResponseUpdate

                        yield ChatResponseUpdate()

                    return _stream()


            # Verify the instance satisfies the protocol
            client = CustomChatClient()
            assert isinstance(client, ChatClientProtocol)
    """

    @property
    def additional_properties(self) -> dict[str, Any]:
        """Get additional properties associated with the client."""
        ...

    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model_id: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send input and return the response.

        Args:
            messages: The sequence of input messages to send.

        Keyword Args:
            frequency_penalty: The frequency penalty to use.
            logit_bias: The logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: Additional metadata to include in the request.
            model_id: The model_id to use for the agent.
            presence_penalty: The presence penalty to use.
            response_format: The format of the response.
            seed: The random seed to use.
            stop: The stop sequence(s) for the request.
            store: Whether to store the response.
            temperature: The sampling temperature to use.
            tool_choice: The tool choice for the request.
            tools: The tools to use for the request.
            top_p: The nucleus sampling probability to use.
            user: The user to associate with the request.
            additional_properties: Additional properties to include in the request.
            kwargs: Any additional keyword arguments.
                Will only be passed to functions that are called.

        Returns:
            The response messages generated by the client.

        Raises:
            ValueError: If the input message sequence is ``None``.
        """
        ...

    def get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model_id: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Send input messages and stream the response.

        Args:
            messages: The sequence of input messages to send.

        Keyword Args:
            frequency_penalty: The frequency penalty to use.
            logit_bias: The logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: Additional metadata to include in the request.
            model_id: The model_id to use for the agent.
            presence_penalty: The presence penalty to use.
            response_format: The format of the response.
            seed: The random seed to use.
            stop: The stop sequence(s) for the request.
            store: Whether to store the response.
            temperature: The sampling temperature to use.
            tool_choice: The tool choice for the request.
            tools: The tools to use for the request.
            top_p: The nucleus sampling probability to use.
            user: The user to associate with the request.
            additional_properties: Additional properties to include in the request.
            kwargs: Any additional keyword arguments.
                Will only be passed to functions that are called.

        Yields:
            ChatResponseUpdate: An async iterable of chat response updates containing
                the content of the response messages generated by the client.

        Raises:
            ValueError: If the input message sequence is ``None``.
        """
        ...


# region ChatClientBase


def _merge_chat_options(
    *,
    base_chat_options: ChatOptions | Any | None,
    model_id: str | None = None,
    frequency_penalty: float | None = None,
    logit_bias: dict[str | int, float] | None = None,
    max_tokens: int | None = None,
    metadata: dict[str, Any] | None = None,
    presence_penalty: float | None = None,
    response_format: type[BaseModel] | None = None,
    seed: int | None = None,
    stop: str | Sequence[str] | None = None,
    store: bool | None = None,
    temperature: float | None = None,
    tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
    tools: list[ToolProtocol | dict[str, Any] | Callable[..., Any]] | None = None,
    top_p: float | None = None,
    user: str | None = None,
    additional_properties: dict[str, Any] | None = None,
) -> ChatOptions:
    """Merge base chat options with direct parameters to create a new ChatOptions instance.

    When both base_chat_options and individual parameters are provided, the individual
    parameters take precedence and override the corresponding values in base_chat_options.
    Tools from both sources are combined into a single list.

    Keyword Args:
        base_chat_options: Optional base ChatOptions to merge with direct parameters.
        model_id: The model_id to use for the agent.
        frequency_penalty: The frequency penalty to use.
        logit_bias: The logit bias to use.
        max_tokens: The maximum number of tokens to generate.
        metadata: Additional metadata to include in the request.
        presence_penalty: The presence penalty to use.
        response_format: The format of the response.
        seed: The random seed to use.
        stop: The stop sequence(s) for the request.
        store: Whether to store the response.
        temperature: The sampling temperature to use.
        tool_choice: The tool choice for the request.
        tools: The normalized tools to use for the request.
        top_p: The nucleus sampling probability to use.
        user: The user to associate with the request.
        additional_properties: Additional properties to include in the request.

    Returns:
        A new ChatOptions instance with merged values.

    Raises:
        TypeError: If base_chat_options is not None and not an instance of ChatOptions.
    """
    # Validate base_chat_options type if provided
    if base_chat_options is not None and not isinstance(base_chat_options, ChatOptions):
        raise TypeError("chat_options must be an instance of ChatOptions")

    if base_chat_options is None:
        base_chat_options = ChatOptions()

    return base_chat_options & ChatOptions(
        model_id=model_id,
        frequency_penalty=frequency_penalty,
        logit_bias=logit_bias,
        max_tokens=max_tokens,
        metadata=metadata,
        presence_penalty=presence_penalty,
        response_format=response_format,
        seed=seed,
        stop=stop,
        store=store,
        temperature=temperature,
        top_p=top_p,
        tool_choice=tool_choice,
        tools=tools,
        user=user,
        additional_properties=additional_properties,
    )


class BaseChatClient(SerializationMixin, ABC):
    """Base class for chat clients.

    This abstract base class provides core functionality for chat client implementations,
    including middleware support, message preparation, and tool normalization.

    Note:
        BaseChatClient cannot be instantiated directly as it's an abstract base class.
        Subclasses must implement ``_inner_get_response()`` and ``_inner_get_streaming_response()``.

    Examples:
        .. code-block:: python

            from agent_framework import BaseChatClient, ChatResponse, ChatMessage
            from collections.abc import AsyncIterable


            class CustomChatClient(BaseChatClient):
                async def _inner_get_response(self, *, messages, chat_options, **kwargs):
                    # Your custom implementation
                    return ChatResponse(
                        messages=[ChatMessage(role="assistant", text="Hello!")], response_id="custom-response"
                    )

                async def _inner_get_streaming_response(self, *, messages, chat_options, **kwargs):
                    # Your custom streaming implementation
                    from agent_framework import ChatResponseUpdate

                    yield ChatResponseUpdate(role="assistant", contents=[{"type": "text", "text": "Hello!"}])


            # Create an instance of your custom client
            client = CustomChatClient()

            # Use the client to get responses
            response = await client.get_response("Hello, how are you?")
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "unknown"
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}
    # This is used for OTel setup, should be overridden in subclasses

    def __init__(
        self,
        *,
        middleware: (
            ChatMiddleware
            | ChatMiddlewareCallable
            | FunctionMiddleware
            | FunctionMiddlewareCallable
            | list[ChatMiddleware | ChatMiddlewareCallable | FunctionMiddleware | FunctionMiddlewareCallable]
            | None
        ) = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a BaseChatClient instance.

        Keyword Args:
            middleware: Middleware for the client.
            additional_properties: Additional properties for the client.
            kwargs: Additional keyword arguments (merged into additional_properties).
        """
        # Merge kwargs into additional_properties
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs)

        self.middleware = middleware

        self.function_invocation_configuration = (
            FunctionInvocationConfiguration() if hasattr(self.__class__, FUNCTION_INVOKING_CHAT_CLIENT_MARKER) else None
        )

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

    def _filter_internal_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Filter out internal framework parameters that shouldn't be passed to chat client implementations.

        Keyword Args:
            kwargs: The original kwargs dictionary.

        Returns:
            A filtered kwargs dictionary without internal parameters.
        """
        return {k: v for k, v in kwargs.items() if not k.startswith("_")}

    @staticmethod
    async def _normalize_tools(
        tools: ToolProtocol
        | MutableMapping[str, Any]
        | Callable[..., Any]
        | Sequence[ToolProtocol | MutableMapping[str, Any] | Callable[..., Any]]
        | None = None,
    ) -> list[ToolProtocol | dict[str, Any] | Callable[..., Any]]:
        """Normalize tools input to a consistent list format.

        Expands MCP tools to their constituent functions, connecting them if needed.

        Args:
            tools: The tools in various supported formats.

        Returns:
            A normalized list of tools.
        """
        from typing import cast

        final_tools: list[ToolProtocol | dict[str, Any] | Callable[..., Any]] = []
        if not tools:
            return final_tools
        # Use cast when a sequence is passed (likely already a list)
        tools_list = (
            cast(list[ToolProtocol | MutableMapping[str, Any] | Callable[..., Any]], tools)
            if isinstance(tools, Sequence) and not isinstance(tools, (str, bytes))
            else [tools]
        )
        for tool in tools_list:  # type: ignore[reportUnknownType]
            if isinstance(tool, MCPTool):
                if not tool.is_connected:
                    await tool.connect()
                final_tools.extend(tool.functions)  # type: ignore
                continue
            final_tools.append(tool)  # type: ignore
        return final_tools

    # region Internal methods to be implemented by the derived classes

    @abstractmethod
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat request to the AI service.

        Keyword Args:
            messages: The chat messages to send.
            chat_options: The options for the request.
            kwargs: Any additional keyword arguments.

        Returns:
            The chat response contents representing the response(s).
        """

    @abstractmethod
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Send a streaming chat request to the AI service.

        Keyword Args:
            messages: The chat messages to send.
            chat_options: The chat_options for the request.
            kwargs: Any additional keyword arguments.

        Yields:
            ChatResponseUpdate: The streaming chat message contents.
        """
        # Below is needed for mypy: https://mypy.readthedocs.io/en/stable/more_types.html#asynchronous-iterators
        if False:
            yield
        await asyncio.sleep(0)  # pragma: no cover
        # This is a no-op, but it allows the method to be async and return an AsyncIterable.
        # The actual implementation should yield ChatResponseUpdate instances as needed.

    # endregion

    # region Public method

    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model_id: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a response from a chat client.

        When both ``chat_options`` (in kwargs) and individual parameters are provided,
        the individual parameters take precedence and override the corresponding values
        in ``chat_options``. Tools from both sources are combined into a single list.

        Args:
            messages: The message or messages to send to the model.

        Keyword Args:
            frequency_penalty: The frequency penalty to use.
            logit_bias: The logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: Additional metadata to include in the request.
            model_id: The model_id to use for the agent.
            presence_penalty: The presence penalty to use.
            response_format: The format of the response.
            seed: The random seed to use.
            stop: The stop sequence(s) for the request.
            store: Whether to store the response.
            temperature: The sampling temperature to use.
            tool_choice: The tool choice for the request.
            tools: The tools to use for the request.
            top_p: The nucleus sampling probability to use.
            user: The user to associate with the request.
            additional_properties: Additional properties to include in the request.
                Can be used for provider-specific parameters.
            kwargs: Any additional keyword arguments.
                May include ``chat_options`` which provides base values that can be overridden by direct parameters.

        Returns:
            A chat response from the model_id.
        """
        # Normalize tools and merge with base chat_options
        normalized_tools = await self._normalize_tools(tools)
        chat_options = _merge_chat_options(
            base_chat_options=kwargs.pop("chat_options", None),
            model_id=model_id,
            frequency_penalty=frequency_penalty,
            logit_bias=logit_bias,
            max_tokens=max_tokens,
            metadata=metadata,
            presence_penalty=presence_penalty,
            response_format=response_format,
            seed=seed,
            stop=stop,
            store=store,
            temperature=temperature,
            tool_choice=tool_choice,
            tools=normalized_tools,
            top_p=top_p,
            user=user,
            additional_properties=additional_properties,
        )

        # Validate that store is True when conversation_id is set
        if chat_options.conversation_id is not None and chat_options.store is not True:
            chat_options.store = True

        if chat_options.instructions:
            system_msg = ChatMessage(role="system", text=chat_options.instructions)
            prepped_messages = [system_msg, *prepare_messages(messages)]
        else:
            prepped_messages = prepare_messages(messages)
        self._prepare_tool_choice(chat_options=chat_options)

        filtered_kwargs = self._filter_internal_kwargs(kwargs)
        return await self._inner_get_response(messages=prepped_messages, chat_options=chat_options, **filtered_kwargs)

    async def get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model_id: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Get a streaming response from a chat client.

        When both ``chat_options`` (in kwargs) and individual parameters are provided,
        the individual parameters take precedence and override the corresponding values
        in ``chat_options``. Tools from both sources are combined into a single list.

        Args:
            messages: The message or messages to send to the model.

        Keyword Args:
            frequency_penalty: The frequency penalty to use.
            logit_bias: The logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: Additional metadata to include in the request.
            model_id: The model_id to use for the agent.
            presence_penalty: The presence penalty to use.
            response_format: The format of the response.
            seed: The random seed to use.
            stop: The stop sequence(s) for the request.
            store: Whether to store the response.
            temperature: The sampling temperature to use.
            tool_choice: The tool choice for the request.
            tools: The tools to use for the request.
            top_p: The nucleus sampling probability to use.
            user: The user to associate with the request.
            additional_properties: Additional properties to include in the request.
                Can be used for provider-specific parameters.
            kwargs: Any additional keyword arguments.
                May include ``chat_options`` which provides base values that can be overridden by direct parameters.

        Yields:
            ChatResponseUpdate: A stream representing the response(s) from the LLM.
        """
        # Normalize tools and merge with base chat_options
        normalized_tools = await self._normalize_tools(tools)
        chat_options = _merge_chat_options(
            base_chat_options=kwargs.pop("chat_options", None),
            model_id=model_id,
            frequency_penalty=frequency_penalty,
            logit_bias=logit_bias,
            max_tokens=max_tokens,
            metadata=metadata,
            presence_penalty=presence_penalty,
            response_format=response_format,
            seed=seed,
            stop=stop,
            store=store,
            temperature=temperature,
            tool_choice=tool_choice,
            tools=normalized_tools,
            top_p=top_p,
            user=user,
            additional_properties=additional_properties,
        )

        # Validate that store is True when conversation_id is set
        if chat_options.conversation_id is not None and chat_options.store is not True:
            chat_options.store = True

        if chat_options.instructions:
            system_msg = ChatMessage(role="system", text=chat_options.instructions)
            prepped_messages = [system_msg, *prepare_messages(messages)]
        else:
            prepped_messages = prepare_messages(messages)
        self._prepare_tool_choice(chat_options=chat_options)

        filtered_kwargs = self._filter_internal_kwargs(kwargs)
        async for update in self._inner_get_streaming_response(
            messages=prepped_messages, chat_options=chat_options, **filtered_kwargs
        ):
            yield update

    def _prepare_tool_choice(self, chat_options: ChatOptions) -> None:
        """Prepare the tools and tool choice for the chat options.

        This function should be overridden by subclasses to customize tool handling,
        as it currently parses only AIFunctions.

        Args:
            chat_options: The chat options to prepare.
        """
        chat_tool_mode = chat_options.tool_choice
        if chat_tool_mode is None or chat_tool_mode == ToolMode.NONE or chat_tool_mode == "none":
            chat_options.tools = None
            chat_options.tool_choice = ToolMode.NONE
            return
        if not chat_options.tools:
            chat_options.tool_choice = ToolMode.NONE
        else:
            chat_options.tool_choice = chat_tool_mode

    def service_url(self) -> str:
        """Get the URL of the service.

        Override this in the subclass to return the proper URL.
        If the service does not have a URL, return None.

        Returns:
            The service URL or 'Unknown' if not implemented.
        """
        return "Unknown"

    def create_agent(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStoreProtocol] | None = None,
        context_providers: ContextProvider | list[ContextProvider] | AggregateContextProvider | None = None,
        middleware: Middleware | list[Middleware] | None = None,
        allow_multiple_tool_calls: bool | None = None,
        conversation_id: str | None = None,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model_id: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_chat_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> "ChatAgent":
        """Create a ChatAgent with this client.

        This is a convenience method that creates a ChatAgent instance with this
        chat client already configured.

        Keyword Args:
            id: The unique identifier for the agent. Will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            instructions: Optional instructions for the agent.
                These will be put into the messages sent to the chat client service as a system message.
            chat_message_store_factory: Factory function to create an instance of ChatMessageStoreProtocol.
                If not provided, the default in-memory store will be used.
            context_providers: Context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            allow_multiple_tool_calls: Whether to allow multiple tool calls per agent turn.
            conversation_id: The conversation ID to associate with the agent's messages.
            frequency_penalty: The frequency penalty to use.
            logit_bias: The logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: Additional metadata to include in the request.
            model_id: The model_id to use for the agent.
            presence_penalty: The presence penalty to use.
            response_format: The format of the response.
            seed: The random seed to use.
            stop: The stop sequence(s) for the request.
            store: Whether to store the response.
            temperature: The sampling temperature to use.
            tool_choice: The tool choice for the request.
            tools: The tools to use for the request.
            top_p: The nucleus sampling probability to use.
            user: The user to associate with the request.
            additional_chat_options: A dictionary of other values that will be passed through
                to the chat_client ``get_response`` and ``get_streaming_response`` methods.
                This can be used to pass provider specific parameters.
            kwargs: Any additional keyword arguments. Will be stored as ``additional_properties``.

        Returns:
            A ChatAgent instance configured with this chat client.

        Examples:
            .. code-block:: python

                from agent_framework.clients import OpenAIChatClient

                # Create a client
                client = OpenAIChatClient(model_id="gpt-4")

                # Create an agent using the convenience method
                agent = client.create_agent(
                    name="assistant", instructions="You are a helpful assistant.", temperature=0.7
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
            chat_message_store_factory=chat_message_store_factory,
            context_providers=context_providers,
            middleware=middleware,
            allow_multiple_tool_calls=allow_multiple_tool_calls,
            conversation_id=conversation_id,
            frequency_penalty=frequency_penalty,
            logit_bias=logit_bias,
            max_tokens=max_tokens,
            metadata=metadata,
            model_id=model_id,
            presence_penalty=presence_penalty,
            response_format=response_format,
            seed=seed,
            stop=stop,
            store=store,
            temperature=temperature,
            tool_choice=tool_choice,
            tools=tools,
            top_p=top_p,
            user=user,
            additional_chat_options=additional_chat_options,
            **kwargs,
        )

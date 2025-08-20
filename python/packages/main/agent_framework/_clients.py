# Copyright (c) Microsoft. All rights reserved.

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable, MutableMapping, MutableSequence, Sequence
from functools import wraps
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from ._logging import get_logger
from ._pydantic import AFBaseModel
from ._threads import ChatMessageStore
from ._tools import AIFunction, AITool
from ._types import (
    AIContents,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatToolMode,
    FunctionCallContent,
    FunctionResultContent,
    GeneratedEmbeddings,
)

if TYPE_CHECKING:
    from ._agents import ChatClientAgent

TInput = TypeVar("TInput", contravariant=True)
TEmbedding = TypeVar("TEmbedding")
TChatClientBase = TypeVar("TChatClientBase", bound="ChatClientBase")

logger = get_logger()

__all__ = [
    "ChatClient",
    "ChatClientBase",
    "EmbeddingGenerator",
    "use_tool_calling",
]

# region Tool Calling Functions and Decorators


async def _auto_invoke_function(
    function_call_content: FunctionCallContent,
    custom_args: dict[str, Any] | None = None,
    *,
    tool_map: dict[str, AIFunction[BaseModel, Any]],
    sequence_index: int | None = None,
    request_index: int | None = None,
) -> AIContents:
    """Invoke a function call requested by the agent, applying filters that are defined in the agent."""
    tool: AIFunction[BaseModel, Any] | None = tool_map.get(function_call_content.name)
    if tool is None:
        raise KeyError(f"No tool or function named '{function_call_content.name}'")

    parsed_args: dict[str, Any] = dict(function_call_content.parse_arguments() or {})

    # Merge with user-supplied args; right-hand side dominates, so parsed args win on conflicts.
    merged_args: dict[str, Any] = (custom_args or {}) | parsed_args
    args = tool.input_model.model_validate(merged_args)
    exception = None
    try:
        function_result = await tool.invoke(arguments=args, tool_call_id=function_call_content.call_id)
    except Exception as ex:
        exception = ex
        function_result = None
    return FunctionResultContent(
        call_id=function_call_content.call_id,
        exception=exception,
        result=function_result,
    )


def _tool_call_non_streaming(
    func: Callable[..., Awaitable["ChatResponse"]],
) -> Callable[..., Awaitable["ChatResponse"]]:
    """Decorate the internal _inner_get_response method to enable tool calls."""

    @wraps(func)
    async def wrapper(
        self: "ChatClientBase",
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        response: ChatResponse | None = None
        fcc_messages: list[ChatMessage] = []
        for attempt_idx in range(getattr(self, "__maximum_iterations_per_request", 10)):
            response = await func(self, messages=messages, chat_options=chat_options, **kwargs)
            # if there are function calls, we will handle them first
            function_results = {
                it.call_id for it in response.messages[0].contents if isinstance(it, FunctionResultContent)
            }
            function_calls = [
                it
                for it in response.messages[0].contents
                if isinstance(it, FunctionCallContent) and it.call_id not in function_results
            ]
            if function_calls:
                # Run all function calls concurrently
                results = await asyncio.gather(*[
                    _auto_invoke_function(
                        function_call,
                        custom_args=kwargs,
                        tool_map={t.name: t for t in chat_options.tools or [] if isinstance(t, AIFunction)},  # type: ignore[reportPrivateUsage]
                        sequence_index=seq_idx,
                        request_index=attempt_idx,
                    )
                    for seq_idx, function_call in enumerate(function_calls)
                ])
                # add a single ChatMessage to the response with the results
                result_message = ChatMessage(role="tool", contents=results)
                response.messages.append(result_message)
                # response should contain 2 messages after this,
                # one with function call contents
                # and one with function result contents
                # the amount and call_id's should match
                # this runs in every but the first run
                # we need to keep track of all function call messages
                fcc_messages.extend(response.messages)
                # and add them as additional context to the messages
                if chat_options.store:
                    messages.clear()
                    messages.append(result_message)
                else:
                    messages.extend(response.messages)
                continue
            # If we reach this point, it means there were no function calls to handle,
            # we'll add the previous function call and responses
            # to the front of the list, so that the final response is the last one
            # TODO (eavanvalkenburg): control this behavior?
            if fcc_messages:
                for msg in reversed(fcc_messages):
                    response.messages.insert(0, msg)
            return response

        # Failsafe: give up on tools, ask model for plain answer
        chat_options.tool_choice = "none"
        self._prepare_tool_choice(chat_options=chat_options)  # type: ignore[reportPrivateUsage]
        response = await func(self, messages=messages, chat_options=chat_options, **kwargs)
        if fcc_messages:
            for msg in reversed(fcc_messages):
                response.messages.insert(0, msg)
        return response

    return wrapper


def _tool_call_streaming(
    func: Callable[..., AsyncIterable["ChatResponseUpdate"]],
) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
    """Decorate the internal _inner_get_response method to enable tool calls."""

    @wraps(func)
    async def wrapper(
        self: "ChatClientBase",
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Wrap the inner get streaming response method to handle tool calls."""
        for attempt_idx in range(getattr(self, "__maximum_iterations_per_request", 10)):
            function_call_returned = False
            all_messages: list[ChatResponseUpdate] = []
            async for update in func(self, messages=messages, chat_options=chat_options, **kwargs):
                if update.contents and any(isinstance(item, FunctionCallContent) for item in update.contents):
                    all_messages.append(update)
                    function_call_returned = True
                yield update

            if not function_call_returned:
                return

            # There is one FunctionCallContent response stream in the messages, combining now to create
            # the full completion depending on the prompt, the message may contain both function call
            # content and others
            response: ChatResponse = ChatResponse.from_chat_response_updates(all_messages)
            # add the single assistant response message to the history
            messages.append(response.messages[0])
            function_calls = [item for item in response.messages[0].contents if isinstance(item, FunctionCallContent)]

            # When conversation id is present, it means that messages are hosted on the server.
            # In this case, we need to update ChatOptions with conversation id and also clear messages
            if response.conversation_id is not None:
                chat_options.conversation_id = response.conversation_id
                messages = []

            if function_calls:
                # Run all function calls concurrently
                results = await asyncio.gather(*[
                    _auto_invoke_function(
                        function_call,
                        custom_args=kwargs,
                        tool_map={t.name: t for t in chat_options.tools or [] if isinstance(t, AIFunction)},  # type: ignore[reportPrivateUsage]
                        sequence_index=seq_idx,
                        request_index=attempt_idx,
                    )
                    for seq_idx, function_call in enumerate(function_calls)
                ])
                yield ChatResponseUpdate(contents=results, role="tool")
                function_result_msg = ChatMessage(role="tool", contents=results)
                response.messages.append(function_result_msg)
                messages.append(function_result_msg)
                continue

        # Failsafe: give up on tools, ask model for plain answer
        chat_options.tool_choice = "none"
        self._prepare_tool_choice(chat_options=chat_options)  # type: ignore[reportPrivateUsage]
        async for update in func(self, messages=messages, chat_options=chat_options, **kwargs):
            yield update

    return wrapper


def use_tool_calling(cls: type[TChatClientBase]) -> type[TChatClientBase]:
    """Class decorator that enables tool calling for a chat client.

    Remarks:
        This only works on classes that derive from ChatClientBase
        and the `_inner_get_response`
        and `_inner_get_streaming_response` methods.
        It also sets a `__maximum_iterations_per_request` attribute on the class.
        if you want to expose this to end_users, do a version of this:

            @property

            def maximum_iterations_per_request(self):
                return getattr(self, "__maximum_iterations_per_request", 10)

            @maximum_iterations_per_request.setter

            def maximum_iterations_per_request(self, value: int) -> None:
                setattr(self, "__maximum_iterations_per_request", value)

    """
    setattr(cls, "__maximum_iterations_per_request", 10)

    if inner_response := getattr(cls, "_inner_get_response", None):
        cls._inner_get_response = _tool_call_non_streaming(inner_response)  # type: ignore
    if inner_streaming_response := getattr(cls, "_inner_get_streaming_response", None):
        cls._inner_get_streaming_response = _tool_call_streaming(inner_streaming_response)  # type: ignore
    return cls


# region ChatClient Protocol


@runtime_checkable
class ChatClient(Protocol):
    """A protocol for a chat client that can generate responses."""

    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Sends input and returns the response.

        Args:
            messages: The sequence of input messages to send.
            response_format: the format of the response.
            frequency_penalty: the frequency penalty to use.
            logit_bias: the logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: additional metadata to include in the request.
            model: The model to use for the agent.
            presence_penalty: the presence penalty to use.
            seed: the random seed to use.
            stop: the stop sequence(s) for the request.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            additional_properties: additional properties to include in the request
            kwargs: any additional keyword arguments,
                will only be passed to functions that are called.

        Returns:
            The response messages generated by the client.

        Raises:
            ValueError: If the input message sequence is `None`.
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
        model: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Sends input messages and streams the response.

        Args:
            messages: The sequence of input messages to send.
            frequency_penalty: the frequency penalty to use.
            logit_bias: the logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: additional metadata to include in the request.
            model: The model to use for the agent.
            presence_penalty: the presence penalty to use.
            response_format: the format of the response.
            seed: the random seed to use.
            stop: the stop sequence(s) for the request.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            additional_properties: additional properties to include in the request
            kwargs: any additional keyword arguments,
                will only be passed to functions that are called.

        Yields:
            An async iterable of chat response updates containing the content of the response messages
            generated by the client.

        Raises:
            ValueError: If the input message sequence is `None`.
        """
        ...


class ChatClientBase(AFBaseModel, ABC):
    """Base class for chat clients."""

    MODEL_PROVIDER_NAME: str = "unknown"
    # This is used for OTel setup, should be overridden in subclasses

    def _prepare_messages(
        self, messages: str | ChatMessage | list[str] | list[ChatMessage]
    ) -> MutableSequence[ChatMessage]:
        """Turn the allowed input into a list of chat messages."""
        if isinstance(messages, str):
            return [ChatMessage(role="user", text=messages)]
        if isinstance(messages, ChatMessage):
            return [messages]
        return_messages: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, str):
                msg = ChatMessage(role="user", text=msg)
            return_messages.append(msg)
        return return_messages

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

        Args:
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

        Args:
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
        model: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a response from a chat client.

        Args:
            messages: the message or messages to send to the model
            frequency_penalty: the frequency penalty to use.
            logit_bias: the logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: additional metadata to include in the request.
            model: The model to use for the agent.
            presence_penalty: the presence penalty to use.
            response_format: the format of the response.
            seed: the random seed to use.
            stop: the stop sequence(s) for the request.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            additional_properties: additional properties to include in the request.
            kwargs: any additional keyword arguments,
                will only be passed to functions that are called.

        Returns:
            A chat response from the model.
        """
        if "chat_options" in kwargs:
            chat_options = kwargs.pop("chat_options")
            if not isinstance(chat_options, ChatOptions):
                raise TypeError("chat_options must be an instance of ChatOptions")
        else:
            chat_options = ChatOptions(
                ai_model_id=model,
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
                tools=tools,  # type: ignore
                user=user,
                additional_properties=additional_properties or {},
            )
        prepped_messages = self._prepare_messages(messages)
        self._prepare_tool_choice(chat_options=chat_options)
        return await self._inner_get_response(messages=prepped_messages, chat_options=chat_options, **kwargs)

    async def get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Get a streaming response from a chat client.

        Args:
            messages: the message or messages to send to the model
            frequency_penalty: the frequency penalty to use
            logit_bias: the logit bias to use
            max_tokens: The maximum number of tokens to generate.
            metadata: additional metadata to include in the request.
            model: The model to use for the agent.
            presence_penalty: the presence penalty to use.
            response_format: the format of the response.
            seed: the random seed to use.
            stop: the stop sequence(s) for the request.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            additional_properties: additional properties to include in the request
            kwargs: any additional keyword arguments

        Yields:
            A stream representing the response(s) from the LLM.
        """
        if "chat_options" in kwargs:
            chat_options = kwargs.pop("chat_options")
            if not isinstance(chat_options, ChatOptions):
                raise TypeError("chat_options must be an instance of ChatOptions")
        else:
            chat_options = ChatOptions(
                ai_model_id=model,
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
                tools=tools,  # type: ignore
                user=user,
                additional_properties=additional_properties or {},
                **kwargs,
            )
        prepped_messages = self._prepare_messages(messages)
        self._prepare_tool_choice(chat_options=chat_options)
        async for update in self._inner_get_streaming_response(
            messages=prepped_messages, chat_options=chat_options, **kwargs
        ):
            yield update

    def _prepare_tool_choice(self, chat_options: ChatOptions) -> None:
        """Prepare the tools and tool choice for the chat options.

        This function should be overridden by subclasses to customize tool handling.
        Because it currently parses only AIFunctions.
        """
        chat_tool_mode: ChatToolMode | None = chat_options.tool_choice  # type: ignore
        if chat_tool_mode is None or chat_tool_mode == ChatToolMode.NONE:
            chat_options.tools = None
            chat_options.tool_choice = ChatToolMode.NONE.mode
            return
        if not chat_options.tools:
            chat_options.tool_choice = ChatToolMode.NONE.mode
        else:
            chat_options.tool_choice = chat_tool_mode.mode

    def service_url(self) -> str | None:
        """Get the URL of the service.

        Override this in the subclass to return the proper URL.
        If the service does not have a URL, return None.
        """
        return None

    def create_agent(
        self,
        *,
        name: str | None = None,
        instructions: str | None = None,
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStore] | None = None,
        **kwargs: Any,
    ) -> "ChatClientAgent":
        """Create an agent with the given name and instructions.

        Args:
            name: The name of the agent.
            instructions: The instructions for the agent.
            tools: Optional list of tools to associate with the agent.
            chat_message_store_factory: Factory function to create an instance of ChatMessageStore. If not provided,
                the default in-memory store will be used.
            **kwargs: Additional keyword arguments to pass to the agent.
                See ChatClientAgent for all the available options.

        Returns:
            An instance of ChatClientAgent.
        """
        from ._agents import ChatClientAgent

        return ChatClientAgent(
            chat_client=self,
            name=name,
            instructions=instructions,
            tools=tools,
            chat_message_store_factory=chat_message_store_factory,
            **kwargs,
        )


# region Embedding Client


@runtime_checkable
class EmbeddingGenerator(Protocol, Generic[TInput, TEmbedding]):
    """A protocol for an embedding generator that can create embeddings from input data."""

    async def generate(
        self,
        input_data: Sequence[TInput],
        **kwargs: Any,
    ) -> GeneratedEmbeddings[TEmbedding]:
        """Generates an embedding for the given input data.

        Args:
            input_data: The input data to generate an embedding for.
            **kwargs: Additional options for the request.

        Returns:
            The generated embedding, this acts like a list, but has additional metadata and usage details.

        """
        ...

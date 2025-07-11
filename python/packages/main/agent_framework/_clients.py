# Copyright (c) Microsoft. All rights reserved.

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable, MutableSequence, Sequence
from functools import wraps
from typing import Annotated, Any, Generic, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, PrivateAttr, StringConstraints

from ._logging import get_logger
from ._pydantic import AFBaseModel
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

TInput = TypeVar("TInput", contravariant=True)
TEmbedding = TypeVar("TEmbedding")
TInnerGetResponse = TypeVar("TInnerGetResponse", bound=Callable[..., Awaitable[ChatResponse]])
TInnerGetStreamingResponse = TypeVar(
    "TInnerGetStreamingResponse", bound=Callable[..., AsyncIterable[ChatResponseUpdate]]
)

TChatClientBase = TypeVar("TChatClientBase", bound="ChatClientBase")

logger = get_logger()

# region: Tool Calling Functions and Decorators


def _merge_function_results(
    messages: list[ChatMessage],
) -> ChatMessage:
    """Combine multiple function result content types to one chat message content type.

    This method combines the FunctionResultContent items from separate ChatMessageContent messages,
    and is used in the event that the `context.terminate = True` condition is met.
    """
    contents: list[Any] = []
    for message in messages:
        contents.extend([item for item in message.contents if isinstance(item, FunctionResultContent)])

    return ChatMessage(
        role="tool",
        contents=contents,
    )


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
        function_result = await tool.invoke(arguments=args)
    except Exception as ex:
        exception = ex
        function_result = None
    return FunctionResultContent(
        call_id=function_call_content.call_id,
        exception=exception,
        result=function_result,
    )


def _tool_to_json_schema_spec(tool: AITool) -> dict[str, Any]:
    """Convert a AITool to the JSON Schema function specification format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters(),
        },
    }


def _prepare_tools_and_tool_choice(chat_options: ChatOptions) -> None:
    """Prepare the tools and tool choice for the chat options."""
    chat_tool_mode: ChatToolMode | None = chat_options.tool_choice  # type: ignore
    if chat_tool_mode is None or chat_tool_mode == ChatToolMode.NONE:
        chat_options.tools = None
        chat_options.tool_choice = ChatToolMode.NONE.mode
        return
    chat_options.tools = [
        (_tool_to_json_schema_spec(t) if isinstance(t, AITool) else t) for t in chat_options.tools or []
    ]
    chat_options.tool_choice = chat_tool_mode.mode


def _tool_call_non_streaming(func: TInnerGetResponse) -> TInnerGetResponse:
    """Decorate the internal _inner_get_response method to enable tool calls.

    Remarks:
        Relies on a class that has the _tool_map attribute for the executable tools to call.
    """

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
        for attempt_idx in range(self.maximum_iterations_per_request):
            response = await func(self, messages=messages, chat_options=chat_options)
            # if there are function calls, we will handle them first
            function_calls = [it for it in response.messages[0].contents if isinstance(it, FunctionCallContent)]
            if function_calls:
                # Run all function calls concurrently
                results = await asyncio.gather(*[
                    _auto_invoke_function(
                        function_call,
                        custom_args=kwargs,
                        tool_map=self._tool_map,
                        sequence_index=seq_idx,
                        request_index=attempt_idx,
                    )
                    for seq_idx, function_call in enumerate(function_calls)
                ])
                # add a single ChatMessage to the response with the results
                response.messages.append(ChatMessage(role="tool", contents=results))
                # response should contain 2 messages after this,
                # one with function call contents
                # and one with function result contents
                # the amount and call_id's should match
                # this runs in every but the first run
                # we need to keep track of all function call messages
                fcc_messages.extend(response.messages)
                # and add them as additional context to the messages
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
        _prepare_tools_and_tool_choice(chat_options=chat_options)
        response = await func(self, messages=messages, chat_options=chat_options)
        if fcc_messages:
            for msg in reversed(fcc_messages):
                response.messages.insert(0, msg)
        return response

    return wrapper  # type: ignore[reportReturnType, return-value]


def _tool_call_streaming(func: TInnerGetStreamingResponse) -> TInnerGetStreamingResponse:
    """Decorate the internal _inner_get_response method to enable tool calls.

    Remarks:
        Relies on a class that has the _tool_map attribute for the executable tools to call.
    """

    @wraps(func)
    async def wrapper(
        self: "ChatClientBase",
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        for attempt_idx in range(self.maximum_iterations_per_request):
            function_call_returned = False
            all_messages: list[ChatResponseUpdate] = []
            async for update in func(self, messages=messages, chat_options=chat_options):
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
            function_calls = [item for item in response.messages[0].contents if isinstance(item, FunctionCallContent)]
            messages.append(response.messages[0])

            if function_calls:
                # Run all function calls concurrently
                results = await asyncio.gather(*[
                    _auto_invoke_function(
                        function_call,
                        custom_args=kwargs,
                        tool_map=self._tool_map,
                        sequence_index=seq_idx,
                        request_index=attempt_idx,
                    )
                    for seq_idx, function_call in enumerate(function_calls)
                ])
                yield ChatResponseUpdate(contents=results, role="tool")
                response.messages.append(ChatMessage(role="tool", contents=results))
                messages.extend(response.messages)
                continue

        # Failsafe: give up on tools, ask model for plain answer
        chat_options.tool_choice = "none"
        _prepare_tools_and_tool_choice(chat_options=chat_options)
        async for update in func(self, messages=messages, chat_options=chat_options, **kwargs):
            yield update

    return wrapper  # type: ignore[reportReturnType, return-value]


def use_tool_calling(cls: type[TChatClientBase]) -> type[TChatClientBase]:
    inner_response = getattr(cls, "_inner_get_response", None)
    if inner_response is not None:
        cls._inner_get_response = _tool_call_non_streaming(inner_response)  # type: ignore
    inner_streaming_response = getattr(cls, "_inner_get_streaming_response", None)
    if inner_streaming_response is not None:
        cls._inner_get_streaming_response = _tool_call_streaming(inner_streaming_response)  # type: ignore
    return cls


# region: ChatClient Protocol


@runtime_checkable
class ChatClient(Protocol):
    """A protocol for a chat client that can generate responses."""

    async def get_response(
        self,
        messages: str | ChatMessage | Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        """Sends input and returns the response.

        Args:
            messages: The sequence of input messages to send.
            **kwargs: Additional options for the request, such as ai_model_id, temperature, etc.
                       See `ChatOptions` for more details.

        Returns:
            The response messages generated by the client.

        Raises:
            ValueError: If the input message sequence is `None`.
        """
        ...

    async def get_streaming_response(
        self,
        messages: str | ChatMessage | Sequence[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Sends input messages and streams the response.

        Args:
            messages: The sequence of input messages to send.
            **kwargs: Additional options for the request, such as ai_model_id, temperature, etc.
                       See `ChatOptions` for more details.

        Yields:
            An async iterable of chat response updates containing the content of the response messages
            generated by the client.

        Raises:
            ValueError: If the input message sequence is `None`.
        """
        ...


class ChatClientBase(AFBaseModel, ABC):
    """Base class for chat clients."""

    ai_model_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    maximum_iterations_per_request: int = 10
    _tool_map: dict[str, AIFunction[BaseModel, Any]] = PrivateAttr(default_factory=dict)  # type: ignore

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
        messages: str | ChatMessage | list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: Sequence[AITool] | None = None,
        response_format: type[BaseModel] | None = None,
        user: str | None = None,
        stop: str | Sequence[str] | None = None,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        store: bool | None = None,
        metadata: dict[str, Any] | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a response from a chat client.

        Args:
            messages: the message or messages to send to the model
            model: the model to use for the request
            max_tokens: the maximum number of tokens to generate
            temperature: the sampling temperature to use
            top_p: the nucleus sampling probability to use
            tool_choice: the tool choice for the request
            tools: the tools to use for the request
            response_format: the format of the response
            user: the user to associate with the request
            stop: the stop sequence(s) for the request
            frequency_penalty: the frequency penalty to use
            logit_bias: the logit bias to use
            presence_penalty: the presence penalty to use
            seed: the random seed to use
            store: whether to store the response
            metadata: additional metadata to include in the request
            additional_properties: additional properties to include in the request
            kwargs: any additional keyword arguments,
                will only be passed to functions that are called.

        Returns:
            A chat response from the model.
        """
        if tools is not None:
            self._tool_map = {tool.name: tool for tool in tools if isinstance(tool, AIFunction)}
        chat_options = ChatOptions(
            ai_model_id=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            tool_choice=tool_choice,
            tools=tools,
            response_format=response_format,
            user=user,
            stop=stop,
            frequency_penalty=frequency_penalty,
            logit_bias=logit_bias,
            presence_penalty=presence_penalty,
            seed=seed,
            store=store,
            metadata=metadata,
            additional_properties=additional_properties or {},
        )
        if isinstance(messages, str):
            messages = [ChatMessage(role="user", text=messages)]
        if isinstance(messages, ChatMessage):
            messages = [messages]
        _prepare_tools_and_tool_choice(chat_options=chat_options)
        return await self._inner_get_response(messages=messages, chat_options=chat_options, **kwargs)

    async def get_streaming_response(
        self,
        messages: str | ChatMessage | list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: Sequence[AITool] | None = None,
        response_format: type[BaseModel] | None = None,
        user: str | None = None,
        stop: str | Sequence[str] | None = None,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        store: bool | None = None,
        metadata: dict[str, Any] | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Get a streaming response from a chat client.

        Args:
            messages: the message or messages to send to the model
            model: the model to use for the request
            max_tokens: the maximum number of tokens to generate
            temperature: the sampling temperature to use
            top_p: the nucleus sampling probability to use
            tool_choice: the tool choice for the request
            tools: the tools to use for the request
            response_format: the format of the response
            user: the user to associate with the request
            stop: the stop sequence(s) for the request
            frequency_penalty: the frequency penalty to use
            logit_bias: the logit bias to use
            presence_penalty: the presence penalty to use
            seed: the random seed to use
            store: whether to store the response
            metadata: additional metadata to include in the request
            additional_properties: additional properties to include in the request
            kwargs: any additional keyword arguments

        Yields:
            A stream representing the response(s) from the LLM.
        """
        if tools is not None:
            self._tool_map = {tool.name: tool for tool in tools if isinstance(tool, AIFunction)}
        chat_options = ChatOptions(
            ai_model_id=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            tool_choice=tool_choice,
            tools=tools,
            response_format=response_format,
            user=user,
            stop=stop,
            frequency_penalty=frequency_penalty,
            logit_bias=logit_bias,
            presence_penalty=presence_penalty,
            seed=seed,
            store=store,
            metadata=metadata,
            additional_properties=additional_properties or {},
            **kwargs,
        )
        if isinstance(messages, str):
            messages = [ChatMessage(role="user", text=messages)]
        if isinstance(messages, ChatMessage):
            messages = [messages]
        _prepare_tools_and_tool_choice(chat_options=chat_options)
        async for update in self._inner_get_streaming_response(messages=messages, chat_options=chat_options, **kwargs):
            yield update


# region: Embedding Client


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

# Copyright (c) Microsoft. All rights reserved.

import inspect
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from copy import copy
from itertools import chain
from typing import Any, ClassVar, Literal, Protocol, TypeVar, cast, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field, create_model

from ._clients import BaseChatClient, ChatClientProtocol
from ._logging import get_logger
from ._mcp import MCPTool
from ._memory import AggregateContextProvider, Context, ContextProvider
from ._middleware import Middleware, use_agent_middleware
from ._serialization import SerializationMixin
from ._threads import AgentThread, ChatMessageStoreProtocol
from ._tools import FUNCTION_INVOKING_CHAT_CLIENT_MARKER, AIFunction, ToolProtocol
from ._types import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    ToolMode,
)
from .exceptions import AgentExecutionException
from .observability import use_agent_observability

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

logger = get_logger("agent_framework")

TThreadType = TypeVar("TThreadType", bound="AgentThread")

__all__ = ["AgentProtocol", "BaseAgent", "ChatAgent"]


# region Agent Protocol


@runtime_checkable
class AgentProtocol(Protocol):
    """A protocol for an agent that can be invoked."""

    @property
    def id(self) -> str:
        """Returns the ID of the agent."""
        ...

    @property
    def name(self) -> str | None:
        """Returns the name of the agent."""
        ...

    @property
    def display_name(self) -> str:
        """Returns the display name of the agent."""
        ...

    @property
    def description(self) -> str | None:
        """Returns the description of the agent."""
        ...

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single AgentRunResponse object. The caller is blocked until
        the final result is available.

        Note: For streaming responses, use the run_stream method, which returns
        intermediate steps and the final result as a stream of AgentRunResponseUpdate
        objects. Streaming only the final result is not feasible because the timing of
        the final result's availability is unknown, and blocking the caller until then
        is undesirable in streaming scenarios.

        Args:
            messages: The message(s) to send to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        ...

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Run the agent as a stream.

        This method will return the intermediate steps and final results of the
        agent's execution as a stream of AgentRunResponseUpdate objects to the caller.

        Note: An AgentRunResponseUpdate object contains a chunk of a message.

        Args:
            messages: The message(s) to send to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Yields:
            An agent response item.
        """
        ...

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        """Creates a new conversation thread for the agent."""
        ...


# region BaseAgent


class BaseAgent(SerializationMixin):
    """Base class for all Agent Framework agents."""

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}

    def __init__(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: ContextProvider | Sequence[ContextProvider] | None = None,
        middleware: Middleware | Sequence[Middleware] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Base class for all Agent Framework agents.

        Args:
            id: The unique identifier of the agent  If no id is provided,
                a new UUID will be generated.
            name: The name of the agent, can be None.
            description: The description of the agent.
            display_name: The display name of the agent, which is either the name or id.
            context_providers: The collection of multiple context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            additional_properties: Additional properties set on the agent.
            kwargs: Additional keyword arguments (merged into additional_properties).
        """
        if id is None:
            id = str(uuid4())
        self.id = id
        self.name = name
        self.description = description
        self.context_provider = self._prepare_context_providers(context_providers)
        if middleware is None or isinstance(middleware, Sequence):
            self.middleware: list[Middleware] | None = cast(list[Middleware], middleware) if middleware else None
        else:
            self.middleware = [middleware]

        # Merge kwargs into additional_properties
        self.additional_properties: dict[str, Any] = cast(dict[str, Any], additional_properties or {})
        self.additional_properties.update(kwargs)

    async def _notify_thread_of_new_messages(
        self,
        thread: AgentThread,
        input_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Notify the thread of new messages.

        This also calls the invoked method of a potential context provider on the thread.
        """
        if isinstance(input_messages, ChatMessage) or len(input_messages) > 0:
            await thread.on_new_messages(input_messages)
        if isinstance(response_messages, ChatMessage) or len(response_messages) > 0:
            await thread.on_new_messages(response_messages)
        if thread.context_provider:
            await thread.context_provider.invoked(input_messages, response_messages)

    @property
    def display_name(self) -> str:
        """Returns the display name of the agent.

        This is the name if present, otherwise the id.
        """
        return self.name or self.id

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        """Returns AgentThread instance that is compatible with the agent."""
        return AgentThread(**kwargs, context_provider=self.context_provider)

    async def deserialize_thread(self, serialized_thread: Any, **kwargs: Any) -> AgentThread:
        """Deserializes the thread."""
        thread: AgentThread = self.get_new_thread()
        await thread.update_from_thread_state(serialized_thread, **kwargs)
        return thread

    def as_tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        arg_name: str = "task",
        arg_description: str | None = None,
        stream_callback: Callable[[AgentRunResponseUpdate], None]
        | Callable[[AgentRunResponseUpdate], Awaitable[None]]
        | None = None,
    ) -> AIFunction[BaseModel, str]:
        """Create an AIFunction tool that wraps this agent.

        Args:
            name: The name for the tool. If None, uses the agent's name.
            description: The description for the tool. If None, uses the agent's description or empty string.
            arg_name: The name of the function argument (default: "task").
            arg_description: The description for the function argument.
                If None, defaults to "Input for {self.display_name}".
            stream_callback: Optional callback for streaming responses. If provided, uses run_stream.

        Returns:
            An AIFunction that can be used as a tool by other agents.
        """
        # Verify that self implements AgentProtocol
        if not isinstance(self, AgentProtocol):
            raise TypeError(f"Agent {self.__class__.__name__} must implement AgentProtocol to be used as a tool")

        tool_name = name or self.name
        if tool_name is None:
            raise ValueError("Agent tool name cannot be None. Either provide a name parameter or set the agent's name.")
        tool_description = description or self.description or ""
        argument_description = arg_description or f"Task for {tool_name}"

        # Create dynamic input model with the specified argument name
        field_info = Field(..., description=argument_description)
        input_model = create_model(f"{name or self.name or 'agent'}_task", **{arg_name: (str, field_info)})  # type: ignore[call-overload]

        # Check if callback is async once, outside the wrapper
        is_async_callback = stream_callback is not None and inspect.iscoroutinefunction(stream_callback)

        async def agent_wrapper(**kwargs: Any) -> str:
            """Wrapper function that calls the agent."""
            # Extract the input from kwargs using the specified arg_name
            input_text = kwargs.get(arg_name, "")

            if stream_callback is None:
                # Use non-streaming mode
                return (await self.run(input_text)).text

            # Use streaming mode - accumulate updates and create final response
            response_updates: list[AgentRunResponseUpdate] = []
            async for update in self.run_stream(input_text):
                response_updates.append(update)
                if is_async_callback:
                    await stream_callback(update)  # type: ignore[misc]
                else:
                    stream_callback(update)

            # Create final text from accumulated updates
            return AgentRunResponse.from_agent_run_response_updates(response_updates).text

        return AIFunction(
            name=tool_name,
            description=tool_description,
            func=agent_wrapper,
            input_model=input_model,
        )

    def _normalize_messages(
        self,
        messages: str | ChatMessage | Sequence[str] | Sequence[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        if messages is None:
            return []

        if isinstance(messages, str):
            return [ChatMessage(role=Role.USER, text=messages)]

        if isinstance(messages, ChatMessage):
            return [messages]

        return [ChatMessage(role=Role.USER, text=msg) if isinstance(msg, str) else msg for msg in messages]

    def _prepare_context_providers(
        self,
        context_providers: ContextProvider | Sequence[ContextProvider] | None = None,
    ) -> AggregateContextProvider | None:
        if not context_providers:
            return None

        if isinstance(context_providers, AggregateContextProvider):
            return context_providers

        return AggregateContextProvider(context_providers)


# region ChatAgent


@use_agent_middleware
@use_agent_observability
class ChatAgent(BaseAgent):
    """A Chat Client Agent."""

    AGENT_SYSTEM_NAME: ClassVar[str] = "microsoft.agent_framework"

    def __init__(
        self,
        chat_client: ChatClientProtocol,
        instructions: str | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStoreProtocol] | None = None,
        context_providers: ContextProvider | list[ContextProvider] | AggregateContextProvider | None = None,
        middleware: Middleware | list[Middleware] | None = None,
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
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        request_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a ChatAgent.

        Remarks:
            The set of attributes from frequency_penalty to additional_properties are used to
            call the chat client, they can also be passed to both run methods.
            When both are set, the ones passed to the run methods take precedence.

        Args:
            chat_client: The chat client to use for the agent.
            instructions: Optional instructions for the agent.
            These will be put into the messages sent to the chat client service as a system message.
            id: The unique identifier for the agent, will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            chat_message_store_factory: factory function to create an instance of ChatMessageStoreProtocol.
                If not provided, the default in-memory store will be used.
            context_providers: The collection of multiple context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
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
            request_kwargs: a dictionary of other values that will be passed through
                to the chat_client `get_response` and `get_streaming_response` methods.
            kwargs: any additional keyword arguments. Will be stored as `additional_properties`
        """
        if not hasattr(chat_client, FUNCTION_INVOKING_CHAT_CLIENT_MARKER) and isinstance(chat_client, BaseChatClient):
            logger.warning(
                "The provided chat client does not support function invoking, this might limit agent capabilities."
            )

        super().__init__(
            id=id,
            name=name,
            description=description,
            context_providers=context_providers,
            middleware=middleware,
            **kwargs,
        )
        self.chat_client = chat_client
        self.chat_message_store_factory = chat_message_store_factory

        # We ignore the MCP Servers here and store them separately,
        # we add their functions to the tools list at runtime
        normalized_tools: list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] = (  # type:ignore[reportUnknownVariableType]
            [] if tools is None else tools if isinstance(tools, list) else [tools]  # type: ignore[list-item]
        )
        self._local_mcp_tools = [tool for tool in normalized_tools if isinstance(tool, MCPTool)]
        agent_tools = [tool for tool in normalized_tools if not isinstance(tool, MCPTool)]
        self.chat_options = ChatOptions(
            model_id=model,
            frequency_penalty=frequency_penalty,
            instructions=instructions,
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
            tools=agent_tools,
            top_p=top_p,
            user=user,
            additional_properties=request_kwargs or {},  # type: ignore
        )
        self._async_exit_stack = AsyncExitStack()
        self._update_agent_name()

    async def __aenter__(self) -> "Self":
        """Async context manager entry.

        If any of the chat_client, local_mcp_tools, or context_providers are context managers,
        they will be entered into the async exit stack to ensure proper cleanup.

        This list might be extended in the future.
        """
        for context_manager in chain([self.chat_client], self._local_mcp_tools):
            if isinstance(context_manager, AbstractAsyncContextManager):
                await self._async_exit_stack.enter_async_context(context_manager)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit.

        Close the async exit stack to ensure all context managers are exited properly.
        """
        await self._async_exit_stack.aclose()

    def _update_agent_name(self) -> None:
        """Update the agent name in a chat client.

        Checks if there is a agent name, the implementation
        should check if there is already a agent name defined, and if not
        set it to this value.
        """
        if hasattr(self.chat_client, "_update_agent_name") and callable(self.chat_client._update_agent_name):  # type: ignore[reportAttributeAccessIssue, attr-defined]
            self.chat_client._update_agent_name(self.name)  # type: ignore[reportAttributeAccessIssue, attr-defined]

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
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
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Run the agent with the given messages and options.

        Remarks:
            Since you won't always call the agent.run directly, but it get's called
            through orchestration, it is advised to set your default values for
            all the chat client parameters in the agent constructor.
            If both parameters are used, the ones passed to the run methods take precedence.

        Args:
            messages: The messages to process.
            thread: The thread to use for the agent.
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
            kwargs: Additional keyword arguments for the agent.
                will only be passed to functions that are called.
        """
        input_messages = self._normalize_messages(messages)
        thread, run_chat_options, thread_messages = await self._prepare_thread_and_messages(
            thread=thread, input_messages=input_messages
        )
        normalized_tools: list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] = (  # type:ignore[reportUnknownVariableType]
            [] if tools is None else tools if isinstance(tools, list) else [tools]
        )
        agent_name = self._get_agent_name()

        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[ToolProtocol | Callable[..., Any] | dict[str, Any]] = []
        # Normalize tools argument to a list without mutating the original parameter
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                if not tool.is_connected:
                    await self._async_exit_stack.enter_async_context(tool)
                final_tools.extend(tool.functions)  # type: ignore
            else:
                final_tools.append(tool)  # type: ignore

        for mcp_server in self._local_mcp_tools:
            if not mcp_server.is_connected:
                await self._async_exit_stack.enter_async_context(mcp_server)
            final_tools.extend(mcp_server.functions)
        response = await self.chat_client.get_response(
            messages=thread_messages,
            chat_options=run_chat_options
            & ChatOptions(
                model_id=model,
                conversation_id=thread.service_thread_id,
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
                tools=final_tools,
                top_p=top_p,
                user=user,
                additional_properties=additional_properties or {},
            ),
            **kwargs,
        )

        await self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Ensure that the author name is set for each message in the response.
        for message in response.messages:
            if message.author_name is None:
                message.author_name = agent_name

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(thread, input_messages, response.messages)
        return AgentRunResponse(
            messages=response.messages,
            response_id=response.response_id,
            created_at=response.created_at,
            usage_details=response.usage_details,
            value=response.value,
            raw_representation=response,
            additional_properties=response.additional_properties,
        )

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
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
        tool_choice: ToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream the agent with the given messages and options.

        Remarks:
            Since you won't always call the agent.run_stream directly, but it get's called
            through orchestration, it is advised to set your default values for
            all the chat client parameters in the agent constructor.
            If both parameters are used, the ones passed to the run methods take precedence.

        Args:
            messages: The messages to process.
            thread: The thread to use for the agent.
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
            kwargs: any additional keyword arguments.
                will only be passed to functions that are called.

        """
        input_messages = self._normalize_messages(messages)
        thread, run_chat_options, thread_messages = await self._prepare_thread_and_messages(
            thread=thread, input_messages=input_messages
        )
        agent_name = self._get_agent_name()
        response_updates: list[ChatResponseUpdate] = []

        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[ToolProtocol | MutableMapping[str, Any] | Callable[..., Any]] = []
        normalized_tools: list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] = (  # type: ignore[reportUnknownVariableType]
            [] if tools is None else tools if isinstance(tools, list) else [tools]
        )
        # Normalize tools argument to a list without mutating the original parameter
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                if not tool.is_connected:
                    await self._async_exit_stack.enter_async_context(tool)
                final_tools.extend(tool.functions)  # type: ignore
            else:
                final_tools.append(tool)

        for mcp_server in self._local_mcp_tools:
            if not mcp_server.is_connected:
                await self._async_exit_stack.enter_async_context(mcp_server)
            final_tools.extend(mcp_server.functions)

        async for update in self.chat_client.get_streaming_response(
            messages=thread_messages,
            chat_options=run_chat_options
            & ChatOptions(
                conversation_id=thread.service_thread_id,
                frequency_penalty=frequency_penalty,
                logit_bias=logit_bias,
                max_tokens=max_tokens,
                metadata=metadata,
                model_id=model,
                presence_penalty=presence_penalty,
                response_format=response_format,
                seed=seed,
                stop=stop,
                store=store,
                temperature=temperature,
                tool_choice=tool_choice,
                tools=final_tools,
                top_p=top_p,
                user=user,
                additional_properties=additional_properties or {},
            ),
            **kwargs,
        ):
            response_updates.append(update)

            if update.author_name is None:
                update.author_name = agent_name

            yield AgentRunResponseUpdate(
                contents=update.contents,
                role=update.role,
                author_name=update.author_name,
                response_id=update.response_id,
                message_id=update.message_id,
                created_at=update.created_at,
                additional_properties=update.additional_properties,
                raw_representation=update,
            )

        response = ChatResponse.from_chat_response_updates(response_updates)
        await self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)
        await self._notify_thread_of_new_messages(thread, input_messages, response.messages)

    @override
    def get_new_thread(
        self,
        *,
        service_thread_id: str | None = None,
        **kwargs: Any,
    ) -> AgentThread:
        """Get a new conversation thread for the agent.

        If you supply a service_thread_id, the thread will be marked as service managed.

        If you don't supply a service_thread_id but have a chat_message_store_factory configured on the agent,
        that factory will be used to create a message store for the thread and the thread will be
        managed locally.

        When neither is present, the thread will be created without a service ID or message store,
        this will be updated based on usage, when you run the agent with this thread.
        If you run with store=True, the response will respond with a thread_id and that will be set.
        Otherwise a messages store is created from the default factory.

        Args:
            service_thread_id: Optional service managed thread ID.
            kwargs: not used at present.
        """
        if service_thread_id is not None:
            return AgentThread(
                service_thread_id=service_thread_id,
                context_provider=self.context_provider,
            )
        if self.chat_message_store_factory is not None:
            return AgentThread(
                message_store=self.chat_message_store_factory(),
                context_provider=self.context_provider,
            )
        return AgentThread(context_provider=self.context_provider)

    async def _update_thread_with_type_and_conversation_id(
        self, thread: AgentThread, response_conversation_id: str | None
    ) -> None:
        """Update thread with storage type and conversation ID.

        Args:
            thread: The thread to update.
            response_conversation_id: The conversation ID from the response, if any.

        Raises:
            AgentExecutionException: If conversation ID is missing for service-managed thread.
        """
        if response_conversation_id is None and thread.service_thread_id is not None:
            # We were passed a thread that is service managed, but we got no conversation id back from the chat client,
            # meaning the service doesn't support service managed threads,
            # so the thread cannot be used with this service.
            raise AgentExecutionException(
                "Service did not return a valid conversation id when using a service managed thread."
            )

        if response_conversation_id is not None:
            # If we got a conversation id back from the chat client, it means that the service
            # supports server side thread storage so we should update the thread with the new id.
            thread.service_thread_id = response_conversation_id
            if thread.context_provider:
                await thread.context_provider.thread_created(thread.service_thread_id)
        elif thread.message_store is None and self.chat_message_store_factory is not None:
            # If the service doesn't use service side thread storage (i.e. we got no id back from invocation), and
            # the thread has no message_store yet, and we have a custom messages store, we should update the thread
            # with the custom message_store so that it has somewhere to store the chat history.
            thread.message_store = self.chat_message_store_factory()

    async def _prepare_thread_and_messages(
        self,
        *,
        thread: AgentThread | None,
        input_messages: list[ChatMessage] | None = None,
    ) -> tuple[AgentThread, ChatOptions, list[ChatMessage]]:
        """Prepare the messages for agent execution.

        Also updates the chat_options of the agent, with

        Args:
            thread: The conversation thread.
            input_messages: Messages to process.

        Returns:
            The validated thread and normalized messages.

        Raises:
            AgentExecutionException: If the thread is not of the expected type.
        """
        chat_options = copy(self.chat_options) if self.chat_options else ChatOptions()
        thread = thread or self.get_new_thread()
        if thread.service_thread_id and thread.context_provider:
            await thread.context_provider.thread_created(thread.service_thread_id)
        thread_messages: list[ChatMessage] = []
        if thread.message_store:
            thread_messages.extend(await thread.message_store.list_messages() or [])
        context: Context | None = None
        if self.context_provider:
            async with self.context_provider:
                context = await self.context_provider.invoking(input_messages or [])
                if context:
                    if context.messages:
                        thread_messages.extend(context.messages)
                    if context.tools:
                        if chat_options.tools is not None:
                            chat_options.tools.extend(context.tools)
                        else:
                            chat_options.tools = list(context.tools)
                    if context.instructions:
                        chat_options.instructions = (
                            context.instructions
                            if not chat_options.instructions
                            else f"{chat_options.instructions}\n{context.instructions}"
                        )
        thread_messages.extend(input_messages or [])
        if (
            thread.service_thread_id
            and chat_options.conversation_id
            and thread.service_thread_id != chat_options.conversation_id
        ):
            raise AgentExecutionException(
                "The conversation_id set on the agent is different from the one set on the thread, "
                "only one ID can be used for a run."
            )
        return thread, chat_options, thread_messages

    def _get_agent_name(self) -> str:
        return self.name or "UnnamedAgent"

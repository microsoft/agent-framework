# Copyright (c) Microsoft. All rights reserved.

import inspect
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any, ClassVar, Literal, Protocol, TypeVar, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field, PrivateAttr, create_model

from ._clients import BaseChatClient, ChatClientProtocol
from ._logging import get_logger
from ._mcp import MCPTool
from ._memory import AggregateContextProvider, Context, ContextProvider
from ._middleware import Middleware, use_agent_middleware
from ._pydantic import AFBaseModel
from ._threads import AgentThread, ChatMessageStore, deserialize_thread_state, thread_on_new_messages
from ._tools import FUNCTION_INVOKING_CHAT_CLIENT_MARKER, AIFunction, ToolProtocol
from ._types import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatToolMode,
    Role,
)
from .exceptions import AgentExecutionException
from .observability import use_agent_observability

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

    def get_new_thread(self) -> AgentThread:
        """Creates a new conversation thread for the agent."""
        ...


# region BaseAgent


class BaseAgent(AFBaseModel):
    """Base class for all Agent Framework agents.

    Attributes:
       id: The unique identifier of the agent  If no id is provided,
           a new UUID will be generated.
       name: The name of the agent, can be None.
       description: The description of the agent.
       display_name: The display name of the agent, which is either the name or id.
       context_providers: The collection of multiple context providers to include during agent invocation.
       middleware: List of middleware to intercept agent and function invocations.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str | None = None
    description: str | None = None
    context_providers: AggregateContextProvider | None = None
    middleware: Middleware | list[Middleware] | None = None

    async def _notify_thread_of_new_messages(
        self, thread: AgentThread, new_messages: ChatMessage | Sequence[ChatMessage]
    ) -> None:
        """Notify the thread of new messages."""
        if isinstance(new_messages, ChatMessage) or len(new_messages) > 0:
            await thread_on_new_messages(thread, new_messages)

    @property
    def display_name(self) -> str:
        """Returns the display name of the agent.

        This is the name if present, otherwise the id.
        """
        return self.name or self.id

    def get_new_thread(self) -> AgentThread:
        """Returns AgentThread instance that is compatible with the agent."""
        return AgentThread()

    async def deserialize_thread(self, serialized_thread: Any, **kwargs: Any) -> AgentThread:
        """Deserializes the thread."""
        thread: AgentThread = self.get_new_thread()
        await deserialize_thread_state(thread, serialized_thread, **kwargs)
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

        return AIFunction(name=tool_name, description=tool_description, func=agent_wrapper, input_model=input_model)

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


# region ChatAgent


@use_agent_middleware
@use_agent_observability
class ChatAgent(BaseAgent):
    """A Chat Client Agent."""

    AGENT_SYSTEM_NAME: ClassVar[str] = "microsoft.agent_framework"
    chat_client: ChatClientProtocol
    instructions: str | None = None
    chat_options: ChatOptions
    chat_message_store_factory: Callable[[], ChatMessageStore] | None = None
    _local_mcp_tools: list[MCPTool] = PrivateAttr(default_factory=list)  # type: ignore[reportUnknownVariableType]
    _async_exit_stack: AsyncExitStack = PrivateAttr(default_factory=AsyncExitStack)

    def __init__(
        self,
        chat_client: ChatClientProtocol,
        instructions: str | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
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
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStore] | None = None,
        context_providers: ContextProvider | list[ContextProvider] | AggregateContextProvider | None = None,
        middleware: Middleware | list[Middleware] | None = None,
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
            chat_message_store_factory: factory function to create an instance of ChatMessageStore. If not provided,
                the default in-memory store will be used.
            context_providers: The collection of multiple context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            kwargs: any additional keyword arguments.
                Unused, can be used by subclasses of this Agent.
        """
        if not hasattr(chat_client, FUNCTION_INVOKING_CHAT_CLIENT_MARKER) and isinstance(chat_client, BaseChatClient):
            logger.warning(
                "The provided chat client does not support function invoking, this might limit agent capabilities."
            )

        kwargs.update(additional_properties or {})

        aggregate_context_providers = self._prepare_context_providers(context_providers)

        # We ignore the MCP Servers here and store them separately,
        # we add their functions to the tools list at runtime
        normalized_tools = [] if tools is None else tools if isinstance(tools, list) else [tools]
        local_mcp_tools = [tool for tool in normalized_tools if isinstance(tool, MCPTool)]
        final_tools = [tool for tool in normalized_tools if not isinstance(tool, MCPTool)]
        args: dict[str, Any] = {
            "chat_client": chat_client,
            "chat_message_store_factory": chat_message_store_factory,
            "context_providers": aggregate_context_providers,
            "middleware": middleware,
            "chat_options": ChatOptions(
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
                tool_choice=tool_choice,
                tools=final_tools,  # type: ignore[reportArgumentType]
                top_p=top_p,
                user=user,
                additional_properties=kwargs,
            ),
        }
        if instructions is not None:
            args["instructions"] = instructions
        if name is not None:
            args["name"] = name
        if description is not None:
            args["description"] = description
        if id is not None:
            args["id"] = id

        super().__init__(**args)
        self._update_agent_name()
        self._local_mcp_tools = local_mcp_tools  # type: ignore[assignment]

    async def __aenter__(self) -> "Self":
        """Async context manager entry.

        If any of the chat_client, local_mcp_tools, or context_providers are context managers,
        they will be entered into the async exit stack to ensure proper cleanup.

        This list might be extended in the future.
        """
        context_managers = [self.chat_client, *self._local_mcp_tools]
        if self.context_providers:
            context_managers.append(self.context_providers)

        for context_manager in context_managers:
            if isinstance(context_manager, AbstractAsyncContextManager):
                await self._async_exit_stack.enter_async_context(context_manager)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
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
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: ToolProtocol
        | list[ToolProtocol]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
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
        context = await self.context_providers.model_invoking(input_messages) if self.context_providers else None
        thread, thread_messages = await self._prepare_thread_and_messages(
            thread=thread, context=context, input_messages=input_messages
        )
        agent_name = self._get_agent_name()

        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[ToolProtocol | Callable[..., Any] | dict[str, Any]] = []
        # Normalize tools argument to a list without mutating the original parameter
        normalized_tools = [] if tools is None else tools if isinstance(tools, list) else [tools]
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                final_tools.extend(tool.functions)  # type: ignore
            else:
                final_tools.append(tool)  # type: ignore

        for mcp_server in self._local_mcp_tools:
            final_tools.extend(mcp_server.functions)

        response = await self.chat_client.get_response(
            messages=thread_messages,
            chat_options=self.chat_options
            & ChatOptions(
                ai_model_id=model,
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
                tools=final_tools,  # type: ignore[reportArgumentType]
                top_p=top_p,
                user=user,
                additional_properties=additional_properties or {},
            ),
            **kwargs,
        )

        self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Ensure that the author name is set for each message in the response.
        for message in response.messages:
            if message.author_name is None:
                message.author_name = agent_name

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

        if self.context_providers:
            await self.context_providers.thread_created(response.conversation_id)
            await self.context_providers.messages_adding(thread.service_thread_id, input_messages + response.messages)

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
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
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
        context = await self.context_providers.model_invoking(input_messages) if self.context_providers else None
        thread, thread_messages = await self._prepare_thread_and_messages(
            thread=thread, context=context, input_messages=input_messages
        )
        agent_name = self._get_agent_name()
        response_updates: list[ChatResponseUpdate] = []

        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[ToolProtocol | MutableMapping[str, Any] | Callable[..., Any]] = []
        # Normalize tools argument to a list without mutating the original parameter
        normalized_tools = [] if tools is None else tools if isinstance(tools, list) else [tools]
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                final_tools.extend(tool.functions)  # type: ignore
            else:
                final_tools.append(tool)

        for mcp_server in self._local_mcp_tools:
            final_tools.extend(mcp_server.functions)

        async for update in self.chat_client.get_streaming_response(
            messages=thread_messages,
            chat_options=self.chat_options
            & ChatOptions(
                conversation_id=thread.service_thread_id,
                frequency_penalty=frequency_penalty,
                logit_bias=logit_bias,
                max_tokens=max_tokens,
                metadata=metadata,
                ai_model_id=model,
                presence_penalty=presence_penalty,
                response_format=response_format,
                seed=seed,
                stop=stop,
                store=store,
                temperature=temperature,
                tool_choice=tool_choice,
                tools=final_tools,  # type: ignore[reportArgumentType]
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

        self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

        if self.context_providers:
            await self.context_providers.thread_created(response.conversation_id)
            await self.context_providers.messages_adding(thread.service_thread_id, input_messages + response.messages)

    def get_new_thread(self) -> AgentThread:
        message_store: ChatMessageStore | None = None

        if self.chat_message_store_factory:
            message_store = self.chat_message_store_factory()

        return AgentThread() if message_store is None else AgentThread(message_store=message_store)

    def _update_thread_with_type_and_conversation_id(
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
        elif thread.message_store is None and self.chat_message_store_factory is not None:
            # If the service doesn't use service side thread storage (i.e. we got no id back from invocation), and
            # the thread has no message_store yet, and we have a custom messages store, we should update the thread
            # with the custom message_store so that it has somewhere to store the chat history.
            thread.message_store = self.chat_message_store_factory()

    async def _prepare_thread_and_messages(
        self,
        *,
        thread: AgentThread | None,
        context: Context | None,
        input_messages: list[ChatMessage] | None = None,
    ) -> tuple[AgentThread, list[ChatMessage]]:
        """Prepare the messages for agent execution.

        Args:
            thread: The conversation thread.
            context: Context to include in messages.
            input_messages: Messages to process.

        Returns:
            The validated thread and normalized messages.

        Raises:
            AgentExecutionException: If the thread is not of the expected type.
        """
        thread = thread or self.get_new_thread()

        messages: list[ChatMessage] = []
        if self.instructions:
            messages.append(ChatMessage(role=Role.SYSTEM, text=self.instructions))
        if context and context.contents:
            messages.append(ChatMessage(role=Role.SYSTEM, contents=context.contents))
        if thread.message_store:
            messages.extend(await thread.message_store.list_messages() or [])
        messages.extend(input_messages or [])
        return thread, messages

    def _get_agent_name(self) -> str:
        return self.name or "UnnamedAgent"

    def _prepare_context_providers(
        self,
        context_providers: ContextProvider | list[ContextProvider] | AggregateContextProvider | None = None,
    ) -> AggregateContextProvider | None:
        if not context_providers:
            return None

        if isinstance(context_providers, AggregateContextProvider):
            return context_providers

        if isinstance(context_providers, ContextProvider):
            return AggregateContextProvider([context_providers])

        return AggregateContextProvider(context_providers)

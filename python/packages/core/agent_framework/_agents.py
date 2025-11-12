# Copyright (c) Microsoft. All rights reserved.

import inspect
import re
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from copy import copy
from itertools import chain
from typing import Any, ClassVar, Literal, Protocol, TypeVar, cast, runtime_checkable
from uuid import uuid4

from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import McpError
from pydantic import BaseModel, Field, create_model

from ._clients import BaseChatClient, ChatClientProtocol
from ._logging import get_logger
from ._mcp import LOG_LEVEL_MAPPING, MCPTool
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
from .exceptions import AgentExecutionException, AgentInitializationError
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


def _sanitize_agent_name(agent_name: str | None) -> str | None:
    """Sanitize agent name for use as a function name.

    Replaces spaces and special characters with underscores to create
    a valid Python identifier.

    Args:
        agent_name: The agent name to sanitize.

    Returns:
        The sanitized agent name with invalid characters replaced by underscores.
        If the input is None, returns None.
        If sanitization results in an empty string (e.g., agent_name="@@@"), returns "agent" as a default.
    """
    if agent_name is None:
        return None

    # Replace any character that is not alphanumeric or underscore with underscore
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", agent_name)

    # Replace multiple consecutive underscores with a single underscore
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    # Handle empty string case
    if not sanitized:
        return "agent"

    # Prefix with underscore if the sanitized name starts with a digit
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"

    return sanitized


__all__ = ["AgentProtocol", "BaseAgent", "ChatAgent"]


# region Agent Protocol


@runtime_checkable
class AgentProtocol(Protocol):
    """A protocol for an agent that can be invoked.

    This protocol defines the interface that all agents must implement,
    including properties for identification and methods for execution.

    Note:
        Protocols use structural subtyping (duck typing). Classes don't need
        to explicitly inherit from this protocol to be considered compatible.
        This allows you to create completely custom agents without using
        any Agent Framework base classes.

    Examples:
        .. code-block:: python

            from agent_framework import AgentProtocol


            # Any class implementing the required methods is compatible
            # No need to inherit from AgentProtocol or use any framework classes
            class CustomAgent:
                def __init__(self):
                    self._id = "custom-agent-001"
                    self._name = "Custom Agent"

                @property
                def id(self) -> str:
                    return self._id

                @property
                def name(self) -> str | None:
                    return self._name

                @property
                def display_name(self) -> str:
                    return self.name or self.id

                @property
                def description(self) -> str | None:
                    return "A fully custom agent implementation"

                async def run(self, messages=None, *, thread=None, **kwargs):
                    # Your custom implementation
                    from agent_framework import AgentRunResponse

                    return AgentRunResponse(messages=[], response_id="custom-response")

                def run_stream(self, messages=None, *, thread=None, **kwargs):
                    # Your custom streaming implementation
                    async def _stream():
                        from agent_framework import AgentRunResponseUpdate

                        yield AgentRunResponseUpdate()

                    return _stream()

                def get_new_thread(self, **kwargs):
                    # Return your own thread implementation
                    return {"id": "custom-thread", "messages": []}


            # Verify the instance satisfies the protocol
            instance = CustomAgent()
            assert isinstance(instance, AgentProtocol)
    """

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

        Keyword Args:
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

        Keyword Args:
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
    """Base class for all Agent Framework agents.

    This class provides core functionality for agent implementations, including
    context providers, middleware support, and thread management.

    Note:
        BaseAgent cannot be instantiated directly as it doesn't implement the
        ``run()``, ``run_stream()``, and other methods required by AgentProtocol.
        Use a concrete implementation like ChatAgent or create a subclass.

    Examples:
        .. code-block:: python

            from agent_framework import BaseAgent, AgentThread, AgentRunResponse


            # Create a concrete subclass that implements the protocol
            class SimpleAgent(BaseAgent):
                async def run(self, messages=None, *, thread=None, **kwargs):
                    # Custom implementation
                    return AgentRunResponse(messages=[], response_id="simple-response")

                def run_stream(self, messages=None, *, thread=None, **kwargs):
                    async def _stream():
                        # Custom streaming implementation
                        yield AgentRunResponseUpdate()

                    return _stream()


            # Now instantiate the concrete subclass
            agent = SimpleAgent(name="my-agent", description="A simple agent implementation")

            # Create with specific ID and additional properties
            agent = SimpleAgent(
                id="custom-id-123",
                name="configured-agent",
                description="An agent with custom configuration",
                additional_properties={"version": "1.0", "environment": "production"},
            )

            # Access agent properties
            print(agent.id)  # Custom or auto-generated UUID
            print(agent.display_name)  # Returns name or id
    """

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
        """Initialize a BaseAgent instance.

        Keyword Args:
            id: The unique identifier of the agent. If no id is provided,
                a new UUID will be generated.
            name: The name of the agent, can be None.
            description: The description of the agent.
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

        Args:
            thread: The thread to notify of new messages.
            input_messages: The input messages to notify about.
            response_messages: The response messages to notify about.
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
        """Return a new AgentThread instance that is compatible with the agent.

        Keyword Args:
            kwargs: Additional keyword arguments passed to AgentThread.

        Returns:
            A new AgentThread instance configured with the agent's context provider.
        """
        return AgentThread(**kwargs, context_provider=self.context_provider)

    async def deserialize_thread(self, serialized_thread: Any, **kwargs: Any) -> AgentThread:
        """Deserialize a thread from its serialized state.

        Args:
            serialized_thread: The serialized thread data.

        Keyword Args:
            kwargs: Additional keyword arguments.

        Returns:
            A new AgentThread instance restored from the serialized state.
        """
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

        Keyword Args:
            name: The name for the tool. If None, uses the agent's name.
            description: The description for the tool. If None, uses the agent's description or empty string.
            arg_name: The name of the function argument (default: "task").
            arg_description: The description for the function argument.
                If None, defaults to "Task for {tool_name}".
            stream_callback: Optional callback for streaming responses. If provided, uses run_stream.

        Returns:
            An AIFunction that can be used as a tool by other agents.

        Raises:
            TypeError: If the agent does not implement AgentProtocol.
            ValueError: If the agent tool name cannot be determined.

        Examples:
            .. code-block:: python

                from agent_framework import ChatAgent

                # Create an agent
                agent = ChatAgent(chat_client=client, name="research-agent", description="Performs research tasks")

                # Convert the agent to a tool
                research_tool = agent.as_tool()

                # Use the tool with another agent
                coordinator = ChatAgent(chat_client=client, name="coordinator", tools=research_tool)
        """
        # Verify that self implements AgentProtocol
        if not isinstance(self, AgentProtocol):
            raise TypeError(f"Agent {self.__class__.__name__} must implement AgentProtocol to be used as a tool")

        tool_name = name or _sanitize_agent_name(self.name)
        if tool_name is None:
            raise ValueError("Agent tool name cannot be None. Either provide a name parameter or set the agent's name.")
        tool_description = description or self.description or ""
        argument_description = arg_description or f"Task for {tool_name}"

        # Create dynamic input model with the specified argument name
        field_info = Field(..., description=argument_description)
        model_name = f"{name or _sanitize_agent_name(self.name) or 'agent'}_task"
        input_model = create_model(model_name, **{arg_name: (str, field_info)})  # type: ignore[call-overload]

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
            input_model=input_model,  # type: ignore
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
    """A Chat Client Agent.

    This is the primary agent implementation that uses a chat client to interact
    with language models. It supports tools, context providers, middleware, and
    both streaming and non-streaming responses.

    Examples:
        Basic usage:

        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework.clients import OpenAIChatClient

            # Create a basic chat agent
            client = OpenAIChatClient(model_id="gpt-4")
            agent = ChatAgent(chat_client=client, name="assistant", description="A helpful assistant")

            # Run the agent with a simple message
            response = await agent.run("Hello, how are you?")
            print(response.text)

        With tools and streaming:

        .. code-block:: python

            # Create an agent with tools and instructions
            def get_weather(location: str) -> str:
                return f"The weather in {location} is sunny."


            agent = ChatAgent(
                chat_client=client,
                name="weather-agent",
                instructions="You are a weather assistant.",
                tools=get_weather,
                temperature=0.7,
                max_tokens=500,
            )

            # Use streaming responses
            async for update in agent.run_stream("What's the weather in Paris?"):
                print(update.text, end="")

        With additional provider specific options:

        .. code-block:: python

            agent = ChatAgent(
                chat_client=client,
                name="reasoning-agent",
                instructions="You are a reasoning assistant.",
                model_id="gpt-5",
                temperature=0.7,
                max_tokens=500,
                additional_chat_options={
                    "reasoning": {"effort": "high", "summary": "concise"}
                },  # OpenAI Responses specific.
            )

            # Use streaming responses
            async for update in agent.run_stream("How do you prove the pythagorean theorem?"):
                print(update.text, end="")
    """

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
        # chat option params
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
    ) -> None:
        """Initialize a ChatAgent instance.

        Note:
            The set of parameters from frequency_penalty to request_kwargs are used to
            call the chat client. They can also be passed to both run methods.
            When both are set, the ones passed to the run methods take precedence.

        Args:
            chat_client: The chat client to use for the agent.
            instructions: Optional instructions for the agent.
                These will be put into the messages sent to the chat client service as a system message.

        Keyword Args:
            id: The unique identifier for the agent. Will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            chat_message_store_factory: Factory function to create an instance of ChatMessageStoreProtocol.
                If not provided, the default in-memory store will be used.
            context_providers: The collection of multiple context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            allow_multiple_tool_calls: Whether to allow multiple tool calls in a single response.
            conversation_id: The conversation ID for service-managed threads.
                Cannot be used together with chat_message_store_factory.
            frequency_penalty: The frequency penalty to use.
            logit_bias: The logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: Additional metadata to include in the request.
            model_id: The model_id to use for the agent.
                This overrides the model_id set in the chat client if it contains one.
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

        Raises:
            AgentInitializationError: If both conversation_id and chat_message_store_factory are provided.
        """
        if conversation_id is not None and chat_message_store_factory is not None:
            raise AgentInitializationError(
                "Cannot specify both conversation_id and chat_message_store_factory. "
                "Use conversation_id for service-managed threads or chat_message_store_factory for local storage."
            )

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
            model_id=model_id or (str(chat_client.model_id) if hasattr(chat_client, "model_id") else None),
            allow_multiple_tool_calls=allow_multiple_tool_calls,
            conversation_id=conversation_id,
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
            additional_properties=additional_chat_options or {},  # type: ignore
        )
        self._async_exit_stack = AsyncExitStack()
        self._update_agent_name()

    async def __aenter__(self) -> "Self":
        """Enter the async context manager.

        If any of the chat_client or local_mcp_tools are context managers,
        they will be entered into the async exit stack to ensure proper cleanup.

        Note:
            This list might be extended in the future.

        Returns:
            The ChatAgent instance.
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
        """Exit the async context manager.

        Close the async exit stack to ensure all context managers are exited properly.

        Args:
            exc_type: The exception type if an exception was raised, None otherwise.
            exc_val: The exception value if an exception was raised, None otherwise.
            exc_tb: The exception traceback if an exception was raised, None otherwise.
        """
        await self._async_exit_stack.aclose()

    def _update_agent_name(self) -> None:
        """Update the agent name in the chat client.

        Checks if the chat client supports agent name updates. The implementation
        should check if there is already an agent name defined, and if not
        set it to this value.
        """
        if hasattr(self.chat_client, "_update_agent_name") and callable(self.chat_client._update_agent_name):  # type: ignore[reportAttributeAccessIssue, attr-defined]
            self.chat_client._update_agent_name(self.name)  # type: ignore[reportAttributeAccessIssue, attr-defined]

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        allow_multiple_tool_calls: bool | None = None,
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
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_chat_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Run the agent with the given messages and options.

        Note:
            Since you won't always call ``agent.run()`` directly (it gets called
            through workflows), it is advised to set your default values for
            all the chat client parameters in the agent constructor.
            If both parameters are used, the ones passed to the run methods take precedence.

        Args:
            messages: The messages to process.

        Keyword Args:
            thread: The thread to use for the agent.
            allow_multiple_tool_calls: Whether to allow multiple tool calls in a single response.
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
            additional_chat_options: Additional properties to include in the request.
                Use this field for provider-specific parameters.
            kwargs: Additional keyword arguments for the agent.
                Will only be passed to functions that are called.

        Returns:
            An AgentRunResponse containing the agent's response.
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

        co = run_chat_options & ChatOptions(
            model_id=model_id,
            conversation_id=thread.service_thread_id,
            allow_multiple_tool_calls=allow_multiple_tool_calls,
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
            **(additional_chat_options or {}),
        )
        response = await self.chat_client.get_response(messages=thread_messages, chat_options=co, **kwargs)

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
        allow_multiple_tool_calls: bool | None = None,
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
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_chat_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream the agent with the given messages and options.

        Note:
            Since you won't always call ``agent.run_stream()`` directly (it gets called
            through orchestration), it is advised to set your default values for
            all the chat client parameters in the agent constructor.
            If both parameters are used, the ones passed to the run methods take precedence.

        Args:
            messages: The messages to process.

        Keyword Args:
            thread: The thread to use for the agent.
            allow_multiple_tool_calls: Whether to allow multiple tool calls in a single response.
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
            additional_chat_options: Additional properties to include in the request.
                Use this field for provider-specific parameters.
            kwargs: Any additional keyword arguments.
                Will only be passed to functions that are called.

        Yields:
            AgentRunResponseUpdate objects containing chunks of the agent's response.
        """
        input_messages = self._normalize_messages(messages)
        thread, run_chat_options, thread_messages = await self._prepare_thread_and_messages(
            thread=thread, input_messages=input_messages
        )
        agent_name = self._get_agent_name()
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

        co = run_chat_options & ChatOptions(
            conversation_id=thread.service_thread_id,
            allow_multiple_tool_calls=allow_multiple_tool_calls,
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
            tools=final_tools,
            top_p=top_p,
            user=user,
            **(additional_chat_options or {}),
        )

        response_updates: list[ChatResponseUpdate] = []
        async for update in self.chat_client.get_streaming_response(
            messages=thread_messages, chat_options=co, **kwargs
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

        response = ChatResponse.from_chat_response_updates(response_updates, output_format_type=co.response_format)
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

        If you don't supply a service_thread_id but have a conversation_id configured on the agent,
        that conversation_id will be used to create a service-managed thread.

        If you don't supply a service_thread_id but have a chat_message_store_factory configured on the agent,
        that factory will be used to create a message store for the thread and the thread will be
        managed locally.

        When neither is present, the thread will be created without a service ID or message store.
        This will be updated based on usage when you run the agent with this thread.
        If you run with ``store=True``, the response will include a thread_id and that will be set.
        Otherwise a message store is created from the default factory.

        Keyword Args:
            service_thread_id: Optional service managed thread ID.
            kwargs: Not used at present.

        Returns:
            A new AgentThread instance.
        """
        if service_thread_id is not None:
            return AgentThread(
                service_thread_id=service_thread_id,
                context_provider=self.context_provider,
            )
        if self.chat_options.conversation_id is not None:
            return AgentThread(
                service_thread_id=self.chat_options.conversation_id,
                context_provider=self.context_provider,
            )
        if self.chat_message_store_factory is not None:
            return AgentThread(
                message_store=self.chat_message_store_factory(),
                context_provider=self.context_provider,
            )
        return AgentThread(context_provider=self.context_provider)

    def as_mcp_server(
        self,
        *,
        server_name: str = "Agent",
        version: str | None = None,
        instructions: str | None = None,
        lifespan: Callable[["Server[Any]"], AbstractAsyncContextManager[Any]] | None = None,
        **kwargs: Any,
    ) -> "Server[Any]":
        """Create an MCP server from an agent instance.

        This function automatically creates a MCP server from an agent instance, it uses the provided arguments to
        configure the server and exposes the agent as a single MCP tool.

        Keyword Args:
            server_name: The name of the server.
            version: The version of the server.
            instructions: The instructions to use for the server.
            lifespan: The lifespan of the server.
            **kwargs: Any extra arguments to pass to the server creation.

        Returns:
            The MCP server instance.
        """
        server_args: dict[str, Any] = {
            "name": server_name,
            "version": version,
            "instructions": instructions,
        }
        if lifespan:
            server_args["lifespan"] = lifespan
        if kwargs:
            server_args.update(kwargs)

        server: "Server[Any]" = Server(**server_args)  # type: ignore[call-arg]

        agent_tool = self.as_tool(name=self._get_agent_name())

        async def _log(level: types.LoggingLevel, data: Any) -> None:
            """Log a message to the server and logger."""
            # Log to the local logger
            logger.log(LOG_LEVEL_MAPPING[level], data)
            if server and server.request_context and server.request_context.session:
                try:
                    await server.request_context.session.send_log_message(level=level, data=data)
                except Exception as e:
                    logger.error("Failed to send log message to server: %s", e)

        @server.list_tools()  # type: ignore
        async def _list_tools() -> list[types.Tool]:  # type: ignore
            """List all tools in the agent."""
            # Get the JSON schema from the Pydantic model
            schema = agent_tool.input_model.model_json_schema()

            tool = types.Tool(
                name=agent_tool.name,
                description=agent_tool.description,
                inputSchema={
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            )

            await _log(level="debug", data=f"Agent tool: {agent_tool}")
            return [tool]

        @server.call_tool()  # type: ignore
        async def _call_tool(  # type: ignore
            name: str, arguments: dict[str, Any]
        ) -> Sequence[types.TextContent | types.ImageContent | types.AudioContent | types.EmbeddedResource]:
            """Call a tool in the agent."""
            await _log(level="debug", data=f"Calling tool with args: {arguments}")

            if name != agent_tool.name:
                raise McpError(
                    error=types.ErrorData(
                        code=types.INTERNAL_ERROR,
                        message=f"Tool {name} not found",
                    ),
                )

            # Create an instance of the input model with the arguments
            try:
                args_instance = agent_tool.input_model(**arguments)
                result = await agent_tool.invoke(arguments=args_instance)
            except Exception as e:
                raise McpError(
                    error=types.ErrorData(
                        code=types.INTERNAL_ERROR,
                        message=f"Error calling tool {name}: {e}",
                    ),
                ) from e

            # Convert result to MCP content
            if isinstance(result, str):
                return [types.TextContent(type="text", text=result)]

            return [types.TextContent(type="text", text=str(result))]

        @server.set_logging_level()  # type: ignore
        async def _set_logging_level(level: types.LoggingLevel) -> None:  # type: ignore
            """Set the logging level for the server."""
            logger.setLevel(LOG_LEVEL_MAPPING[level])
            # emit this log with the new minimum level
            await _log(level=level, data=f"Log level set to {level}")

        return server

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
        """Prepare the thread and messages for agent execution.

        This method prepares the conversation thread, merges context provider data,
        and assembles the final message list for the chat client.

        Keyword Args:
            thread: The conversation thread.
            input_messages: Messages to process.

        Returns:
            A tuple containing:
                - The validated or created thread
                - The merged chat options
                - The complete list of messages for the chat client

        Raises:
            AgentExecutionException: If the conversation IDs on the thread and agent don't match.
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
        """Get the agent name for message attribution.

        Returns:
            The agent's name, or 'UnnamedAgent' if no name is set.
        """
        return self.name or "UnnamedAgent"

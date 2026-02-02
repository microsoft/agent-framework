# Copyright (c) Microsoft. All rights reserved.

import inspect
import re
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from copy import deepcopy
from itertools import chain
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Protocol,
    cast,
    overload,
    runtime_checkable,
)
from uuid import uuid4

from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import McpError
from pydantic import BaseModel, Field, create_model

from ._clients import BaseChatClient, ChatClientProtocol
from ._logging import get_logger
from ._mcp import LOG_LEVEL_MAPPING, MCPTool
from ._memory import Context, ContextProvider
from ._middleware import Middleware, use_agent_middleware
from ._serialization import SerializationMixin
from ._threads import AgentThread, ChatMessageStoreProtocol
from ._tools import FUNCTION_INVOKING_CHAT_CLIENT_MARKER, FunctionTool, ToolProtocol
from ._types import (
    AgentResponse,
    AgentResponseUpdate,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    normalize_messages,
)
from .exceptions import AgentExecutionException, AgentInitializationError
from .observability import use_agent_instrumentation

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
    from ._types import ChatOptions


TResponseModel = TypeVar("TResponseModel", bound=BaseModel | None, default=None, covariant=True)
TResponseModelT = TypeVar("TResponseModelT", bound=BaseModel)


logger = get_logger("agent_framework")

TThreadType = TypeVar("TThreadType", bound="AgentThread")
TOptions_co = TypeVar(
    "TOptions_co",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions",
    covariant=True,
)


def _merge_options(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge two options dicts, with override values taking precedence.

    Args:
        base: The base options dict.
        override: The override options dict (values take precedence).

    Returns:
        A new merged options dict.
    """
    result = dict(base)
    for key, value in override.items():
        if value is None:
            continue
        if key == "tools" and result.get("tools"):
            # Combine tool lists, avoiding duplicates by name
            existing_names = {getattr(t, "name", None) for t in result["tools"]}
            unique_new = [t for t in value if getattr(t, "name", None) not in existing_names]
            result["tools"] = list(result["tools"]) + unique_new
        elif key == "logit_bias" and result.get("logit_bias"):
            # Merge logit_bias dicts
            result["logit_bias"] = {**result["logit_bias"], **value}
        elif key == "metadata" and result.get("metadata"):
            # Merge metadata dicts
            result["metadata"] = {**result["metadata"], **value}
        elif key == "instructions" and result.get("instructions"):
            # Concatenate instructions
            result["instructions"] = f"{result['instructions']}\n{value}"
        else:
            result[key] = value
    return result


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
                    self.id = "custom-agent-001"
                    self.name = "Custom Agent"
                    self.description = "A fully custom agent implementation"

                async def run(self, messages=None, *, thread=None, **kwargs):
                    # Your custom implementation
                    from agent_framework import AgentResponse

                    return AgentResponse(messages=[], response_id="custom-response")

                def run_stream(self, messages=None, *, thread=None, **kwargs):
                    # Your custom streaming implementation
                    async def _stream():
                        from agent_framework import AgentResponseUpdate

                        yield AgentResponseUpdate()

                    return _stream()

                def get_new_thread(self, **kwargs):
                    # Return your own thread implementation
                    return {"id": "custom-thread", "messages": []}


            # Verify the instance satisfies the protocol
            instance = CustomAgent()
            assert isinstance(instance, AgentProtocol)
    """

    id: str
    name: str | None
    description: str | None

    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single AgentResponse object. The caller is blocked until
        the final result is available.

        Note: For streaming responses, use the run_stream method, which returns
        intermediate steps and the final result as a stream of AgentResponseUpdate
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
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Run the agent as a stream.

        This method will return the intermediate steps and final results of the
        agent's execution as a stream of AgentResponseUpdate objects to the caller.

        Note: An AgentResponseUpdate object contains a chunk of a message.

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

            from agent_framework import BaseAgent, AgentThread, AgentResponse


            # Create a concrete subclass that implements the protocol
            class SimpleAgent(BaseAgent):
                async def run(self, messages=None, *, thread=None, **kwargs):
                    # Custom implementation
                    return AgentResponse(messages=[], response_id="simple-response")

                def run_stream(self, messages=None, *, thread=None, **kwargs):
                    async def _stream():
                        # Custom streaming implementation
                        yield AgentResponseUpdate()

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
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}

    def __init__(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_provider: ContextProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a BaseAgent instance.

        Keyword Args:
            id: The unique identifier of the agent. If no id is provided,
                a new UUID will be generated.
            name: The name of the agent, can be None.
            description: The description of the agent.
            context_provider: The context provider to include during agent invocation.
            middleware: List of middleware.
            additional_properties: Additional properties set on the agent.
            kwargs: Additional keyword arguments (merged into additional_properties).
        """
        if id is None:
            id = str(uuid4())
        self.id = id
        self.name = name
        self.description = description
        self.context_provider = context_provider
        self.middleware: list[Middleware] | None = (
            cast(list[Middleware], middleware) if middleware is not None else None
        )

        # Merge kwargs into additional_properties
        self.additional_properties: dict[str, Any] = cast(dict[str, Any], additional_properties or {})
        self.additional_properties.update(kwargs)

    async def _notify_thread_of_new_messages(
        self,
        thread: AgentThread,
        input_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage],
        **kwargs: Any,
    ) -> None:
        """Notify the thread of new messages.

        This also calls the invoked method of a potential context provider on the thread.

        Args:
            thread: The thread to notify of new messages.
            input_messages: The input messages to notify about.
            response_messages: The response messages to notify about.
            **kwargs: Any extra arguments to pass from the agent run.
        """
        if isinstance(input_messages, ChatMessage) or len(input_messages) > 0:
            await thread.on_new_messages(input_messages)
        if isinstance(response_messages, ChatMessage) or len(response_messages) > 0:
            await thread.on_new_messages(response_messages)
        if thread.context_provider:
            await thread.context_provider.invoked(input_messages, response_messages, **kwargs)

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
        stream_callback: Callable[[AgentResponseUpdate], None]
        | Callable[[AgentResponseUpdate], Awaitable[None]]
        | None = None,
    ) -> FunctionTool[BaseModel, str]:
        """Create a FunctionTool that wraps this agent.

        Keyword Args:
            name: The name for the tool. If None, uses the agent's name.
            description: The description for the tool. If None, uses the agent's description or empty string.
            arg_name: The name of the function argument (default: "task").
            arg_description: The description for the function argument.
                If None, defaults to "Task for {tool_name}".
            stream_callback: Optional callback for streaming responses. If provided, uses run_stream.

        Returns:
            A FunctionTool that can be used as a tool by other agents.

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

            # Forward runtime context kwargs, excluding arg_name and conversation_id.
            forwarded_kwargs = {k: v for k, v in kwargs.items() if k not in (arg_name, "conversation_id")}

            if stream_callback is None:
                # Use non-streaming mode
                return (await self.run(input_text, **forwarded_kwargs)).text

            # Use streaming mode - accumulate updates and create final response
            response_updates: list[AgentResponseUpdate] = []
            async for update in self.run_stream(input_text, **forwarded_kwargs):
                response_updates.append(update)
                if is_async_callback:
                    await stream_callback(update)  # type: ignore[misc]
                else:
                    stream_callback(update)

            # Create final text from accumulated updates
            return AgentResponse.from_agent_run_response_updates(response_updates).text

        agent_tool: FunctionTool[BaseModel, str] = FunctionTool(
            name=tool_name,
            description=tool_description,
            func=agent_wrapper,
            input_model=input_model,  # type: ignore
            approval_mode="never_require",
        )
        agent_tool._forward_runtime_kwargs = True  # type: ignore
        return agent_tool


# region ChatAgent


@use_agent_middleware
@use_agent_instrumentation(capture_usage=False)  # type: ignore[arg-type,misc]
class ChatAgent(BaseAgent, Generic[TOptions_co]):  # type: ignore[misc]
    """A Chat Client Agent.

    This is the primary agent implementation that uses a chat client to interact
    with language models. It supports tools, context providers, middleware, and
    both streaming and non-streaming responses.

    The generic type parameter TOptions specifies which options TypedDict this agent
    accepts. This enables IDE autocomplete and type checking for provider-specific options.

    Examples:
        Basic usage:

        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework.openai import OpenAIChatClient

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

        With typed options for IDE autocomplete:

        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

            client = OpenAIChatClient(model_id="gpt-4o")
            agent: ChatAgent[OpenAIChatOptions] = ChatAgent(
                chat_client=client,
                name="reasoning-agent",
                instructions="You are a reasoning assistant.",
                options={
                    "temperature": 0.7,
                    "max_tokens": 500,
                    "reasoning_effort": "high",  # OpenAI-specific, IDE will autocomplete!
                },
            )

            # Or pass options at runtime
            response = await agent.run(
                "What is 25 * 47?",
                options={"temperature": 0.0, "logprobs": True},
            )
    """

    AGENT_PROVIDER_NAME: ClassVar[str] = "microsoft.agent_framework"

    def __init__(
        self,
        chat_client: ChatClientProtocol[TOptions_co],
        instructions: str | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        default_options: TOptions_co | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStoreProtocol] | None = None,
        context_provider: ContextProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a ChatAgent instance.

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
            context_provider: The context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            default_options: A TypedDict containing chat options. When using a typed agent like
                ``ChatAgent[OpenAIChatOptions]``, this enables IDE autocomplete for
                provider-specific options including temperature, max_tokens, model_id,
                tool_choice, and provider-specific options like reasoning_effort.
                You can also create your own TypedDict for custom chat clients.
                Note: response_format typing does not flow into run outputs when set via default_options.
                These can be overridden at runtime via the ``options`` parameter of ``run()`` and ``run_stream()``.
            tools: The tools to use for the request.
            kwargs: Any additional keyword arguments. Will be stored as ``additional_properties``.

        Raises:
            AgentInitializationError: If both conversation_id and chat_message_store_factory are provided.
        """
        # Extract conversation_id from options for validation
        opts = dict(default_options) if default_options else {}
        conversation_id = opts.get("conversation_id")

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
            context_provider=context_provider,
            middleware=middleware,
            **kwargs,
        )
        self.chat_client: ChatClientProtocol[TOptions_co] = chat_client
        self.chat_message_store_factory = chat_message_store_factory

        # Get tools from options or named parameter (named param takes precedence)
        tools_ = tools if tools is not None else opts.pop("tools", None)
        tools_ = cast(
            ToolProtocol
            | Callable[..., Any]
            | MutableMapping[str, Any]
            | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
            | None,
            tools_,
        )

        # Handle instructions - named parameter takes precedence over options
        instructions_ = instructions if instructions is not None else opts.pop("instructions", None)

        # We ignore the MCP Servers here and store them separately,
        # we add their functions to the tools list at runtime
        normalized_tools: list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] = (  # type:ignore[reportUnknownVariableType]
            [] if tools_ is None else tools_ if isinstance(tools_, list) else [tools_]  # type: ignore[list-item]
        )
        self.mcp_tools: list[MCPTool] = [tool for tool in normalized_tools if isinstance(tool, MCPTool)]
        agent_tools = [tool for tool in normalized_tools if not isinstance(tool, MCPTool)]

        # Build chat options dict
        self.default_options: dict[str, Any] = {
            "model_id": opts.pop("model_id", None) or (getattr(self.chat_client, "model_id", None)),
            "allow_multiple_tool_calls": opts.pop("allow_multiple_tool_calls", None),
            "conversation_id": conversation_id,
            "frequency_penalty": opts.pop("frequency_penalty", None),
            "instructions": instructions_,
            "logit_bias": opts.pop("logit_bias", None),
            "max_tokens": opts.pop("max_tokens", None),
            "metadata": opts.pop("metadata", None),
            "presence_penalty": opts.pop("presence_penalty", None),
            "response_format": opts.pop("response_format", None),
            "seed": opts.pop("seed", None),
            "stop": opts.pop("stop", None),
            "store": opts.pop("store", None),
            "temperature": opts.pop("temperature", None),
            "tool_choice": opts.pop("tool_choice", "auto"),
            "tools": agent_tools,
            "top_p": opts.pop("top_p", None),
            "user": opts.pop("user", None),
            **opts,  # Remaining options are provider-specific
        }
        # Remove None values from chat_options
        self.default_options = {k: v for k, v in self.default_options.items() if v is not None}
        self._async_exit_stack = AsyncExitStack()
        self._update_agent_name_and_description()

    async def __aenter__(self) -> "Self":
        """Enter the async context manager.

        If any of the chat_client or local_mcp_tools are context managers,
        they will be entered into the async exit stack to ensure proper cleanup.

        Note:
            This list might be extended in the future.

        Returns:
            The ChatAgent instance.
        """
        for context_manager in chain([self.chat_client], self.mcp_tools):
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

    def _update_agent_name_and_description(self) -> None:
        """Update the agent name in the chat client.

        Checks if the chat client supports agent name updates. The implementation
        should check if there is already an agent name defined, and if not
        set it to this value.
        """
        if hasattr(self.chat_client, "_update_agent_name_and_description") and callable(
            self.chat_client._update_agent_name_and_description
        ):  # type: ignore[reportAttributeAccessIssue, attr-defined]
            self.chat_client._update_agent_name_and_description(self.name, self.description)  # type: ignore[reportAttributeAccessIssue, attr-defined]

    @overload
    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        options: "ChatOptions[TResponseModelT]",
        **kwargs: Any,
    ) -> AgentResponse[TResponseModelT]: ...

    @overload
    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        options: TOptions_co | Mapping[str, Any] | "ChatOptions[Any]" | None = None,
        **kwargs: Any,
    ) -> AgentResponse[Any]: ...

    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        options: TOptions_co | Mapping[str, Any] | "ChatOptions[Any]" | None = None,
        **kwargs: Any,
    ) -> AgentResponse[Any]:
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
            tools: The tools to use for this specific run (merged with default tools).
            options: A TypedDict containing chat options. When using a typed agent like
                ``ChatAgent[OpenAIChatOptions]``, this enables IDE autocomplete for
                provider-specific options including temperature, max_tokens, model_id,
                tool_choice, and provider-specific options like reasoning_effort.
            kwargs: Additional keyword arguments for the agent.
                Will only be passed to functions that are called.

        Returns:
            An AgentResponse containing the agent's response.
        """
        # Build options dict from provided options
        opts = dict(options) if options else {}

        # Get tools from options or named parameter (named param takes precedence)
        tools_ = tools if tools is not None else opts.pop("tools", None)
        tools_ = cast(
            ToolProtocol
            | Callable[..., Any]
            | MutableMapping[str, Any]
            | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
            | None,
            tools_,
        )

        input_messages = normalize_messages(messages)
        thread, run_chat_options, thread_messages = await self._prepare_thread_and_messages(
            thread=thread, input_messages=input_messages, **kwargs
        )
        normalized_tools: list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] = (  # type:ignore[reportUnknownVariableType]
            [] if tools_ is None else tools_ if isinstance(tools_, list) else [tools_]
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

        for mcp_server in self.mcp_tools:
            if not mcp_server.is_connected:
                await self._async_exit_stack.enter_async_context(mcp_server)
            final_tools.extend(mcp_server.functions)

        # Build options dict from run() options merged with provided options
        run_opts: dict[str, Any] = {
            "model_id": opts.pop("model_id", None),
            "conversation_id": thread.service_thread_id,
            "allow_multiple_tool_calls": opts.pop("allow_multiple_tool_calls", None),
            "frequency_penalty": opts.pop("frequency_penalty", None),
            "logit_bias": opts.pop("logit_bias", None),
            "max_tokens": opts.pop("max_tokens", None),
            "metadata": opts.pop("metadata", None),
            "presence_penalty": opts.pop("presence_penalty", None),
            "response_format": opts.pop("response_format", None),
            "seed": opts.pop("seed", None),
            "stop": opts.pop("stop", None),
            "store": opts.pop("store", None),
            "temperature": opts.pop("temperature", None),
            "tool_choice": opts.pop("tool_choice", None),
            "tools": final_tools,
            "top_p": opts.pop("top_p", None),
            "user": opts.pop("user", None),
            **opts,  # Remaining options are provider-specific
        }
        # Remove None values and merge with chat_options
        run_opts = {k: v for k, v in run_opts.items() if v is not None}
        co = _merge_options(run_chat_options, run_opts)

        # Ensure thread is forwarded in kwargs for tool invocation
        kwargs["thread"] = thread
        # Filter chat_options from kwargs to prevent duplicate keyword argument
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "chat_options"}
        response = await self.chat_client.get_response(
            messages=thread_messages,
            options=co,  # type: ignore[arg-type]
            **filtered_kwargs,
        )

        await self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Ensure that the author name is set for each message in the response.
        for message in response.messages:
            if message.author_name is None:
                message.author_name = agent_name

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(
            thread,
            input_messages,
            response.messages,
            **{k: v for k, v in kwargs.items() if k != "thread"},
        )
        response_format = co.get("response_format")
        if not (
            response_format is not None and isinstance(response_format, type) and issubclass(response_format, BaseModel)
        ):
            response_format = None

        return AgentResponse(
            messages=response.messages,
            response_id=response.response_id,
            created_at=response.created_at,
            usage_details=response.usage_details,
            value=response.value,
            response_format=response_format,
            raw_representation=response,
            additional_properties=response.additional_properties,
        )

    async def run_stream(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        options: TOptions_co | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
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
            tools: The tools to use for this specific run (merged with agent-level tools).
            options: A TypedDict containing chat options. When using a typed agent like
                ``ChatAgent[OpenAIChatOptions]``, this enables IDE autocomplete for
                provider-specific options including temperature, max_tokens, model_id,
                tool_choice, and provider-specific options like reasoning_effort.
            kwargs: Additional keyword arguments for the agent.
                Will only be passed to functions that are called.

        Yields:
            AgentResponseUpdate objects containing chunks of the agent's response.
        """
        # Build options dict from provided options
        opts = dict(options) if options else {}

        # Get tools from options or named parameter (named param takes precedence)
        tools_ = tools if tools is not None else opts.pop("tools", None)

        input_messages = normalize_messages(messages)
        thread, run_chat_options, thread_messages = await self._prepare_thread_and_messages(
            thread=thread, input_messages=input_messages, **kwargs
        )
        agent_name = self._get_agent_name()
        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[ToolProtocol | MutableMapping[str, Any] | Callable[..., Any]] = []
        normalized_tools: list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] = (  # type: ignore[reportUnknownVariableType]
            [] if tools_ is None else tools_ if isinstance(tools_, list) else [tools_]
        )
        # Normalize tools argument to a list without mutating the original parameter
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                if not tool.is_connected:
                    await self._async_exit_stack.enter_async_context(tool)
                final_tools.extend(tool.functions)  # type: ignore
            else:
                final_tools.append(tool)

        for mcp_server in self.mcp_tools:
            if not mcp_server.is_connected:
                await self._async_exit_stack.enter_async_context(mcp_server)
            final_tools.extend(mcp_server.functions)

        # Build options dict from run_stream() options merged with provided options
        run_opts: dict[str, Any] = {
            "model_id": opts.pop("model_id", None),
            "conversation_id": thread.service_thread_id,
            "allow_multiple_tool_calls": opts.pop("allow_multiple_tool_calls", None),
            "frequency_penalty": opts.pop("frequency_penalty", None),
            "logit_bias": opts.pop("logit_bias", None),
            "max_tokens": opts.pop("max_tokens", None),
            "metadata": opts.pop("metadata", None),
            "presence_penalty": opts.pop("presence_penalty", None),
            "response_format": opts.pop("response_format", None),
            "seed": opts.pop("seed", None),
            "stop": opts.pop("stop", None),
            "store": opts.pop("store", None),
            "temperature": opts.pop("temperature", None),
            "tool_choice": opts.pop("tool_choice", None),
            "tools": final_tools,
            "top_p": opts.pop("top_p", None),
            "user": opts.pop("user", None),
            **opts,  # Remaining options are provider-specific
        }
        # Remove None values and merge with chat_options
        run_opts = {k: v for k, v in run_opts.items() if v is not None}
        co = _merge_options(run_chat_options, run_opts)

        # Ensure thread is forwarded in kwargs for tool invocation
        kwargs["thread"] = thread
        # Filter chat_options from kwargs to prevent duplicate keyword argument
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "chat_options"}
        response_updates: list[ChatResponseUpdate] = []
        async for update in self.chat_client.get_streaming_response(
            messages=thread_messages,
            options=co,  # type: ignore[arg-type]
            **filtered_kwargs,
        ):
            response_updates.append(update)

            if update.author_name is None:
                update.author_name = agent_name

            yield AgentResponseUpdate(
                contents=update.contents,
                role=update.role,
                author_name=update.author_name,
                response_id=update.response_id,
                message_id=update.message_id,
                created_at=update.created_at,
                additional_properties=update.additional_properties,
                raw_representation=update,
            )

        response = ChatResponse.from_chat_response_updates(
            response_updates, output_format_type=co.get("response_format")
        )
        await self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        await self._notify_thread_of_new_messages(
            thread,
            input_messages,
            response.messages,
            **{k: v for k, v in kwargs.items() if k != "thread"},
        )

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
        if self.default_options.get("conversation_id") is not None:
            return AgentThread(
                service_thread_id=self.default_options["conversation_id"],
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
                return [types.TextContent(type="text", text=result)]  # type: ignore[attr-defined]

            return [types.TextContent(type="text", text=str(result))]  # type: ignore[attr-defined]

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
        **kwargs: Any,
    ) -> tuple[AgentThread, dict[str, Any], list[ChatMessage]]:
        """Prepare the thread and messages for agent execution.

        This method prepares the conversation thread, merges context provider data,
        and assembles the final message list for the chat client.

        Keyword Args:
            thread: The conversation thread.
            input_messages: Messages to process.
            **kwargs: Any extra arguments to pass from the agent run.

        Returns:
            A tuple containing:
                - The validated or created thread
                - The merged chat options
                - The complete list of messages for the chat client

        Raises:
            AgentExecutionException: If the conversation IDs on the thread and agent don't match.
        """
        # Create a shallow copy of options and deep copy non-tool values
        # Tools containing HTTP clients or other non-copyable objects cannot be deep copied
        if self.default_options:
            chat_options: dict[str, Any] = {}
            for key, value in self.default_options.items():
                if key == "tools":
                    # Keep tool references as-is (don't deep copy)
                    chat_options[key] = list(value) if value else []
                else:
                    # Deep copy other options to prevent mutation
                    chat_options[key] = deepcopy(value)
        else:
            chat_options = {}
        thread = thread or self.get_new_thread()
        if thread.service_thread_id and thread.context_provider:
            await thread.context_provider.thread_created(thread.service_thread_id)
        thread_messages: list[ChatMessage] = []
        if thread.message_store:
            thread_messages.extend(await thread.message_store.list_messages() or [])
        context: Context | None = None
        if self.context_provider:
            # Note: We don't use 'async with' here because the context provider's lifecycle
            # should be managed by the user (via async with) or persist across multiple invocations.
            # Using async with here would close resources (like retrieval clients) after each query.
            context = await self.context_provider.invoking(input_messages or [], **kwargs)
            if context:
                if context.messages:
                    thread_messages.extend(context.messages)
                if context.tools:
                    if chat_options.get("tools") is not None:
                        chat_options["tools"].extend(context.tools)
                    else:
                        chat_options["tools"] = list(context.tools)
                if context.instructions:
                    chat_options["instructions"] = (
                        context.instructions
                        if "instructions" not in chat_options
                        else f"{chat_options['instructions']}\n{context.instructions}"
                    )
        thread_messages.extend(input_messages or [])
        if (
            thread.service_thread_id
            and chat_options.get("conversation_id")
            and thread.service_thread_id != chat_options["conversation_id"]
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

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import logging
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from copy import deepcopy
from functools import partial
from itertools import chain
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
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

from ._clients import BaseChatClient, SupportsChatGetResponse
from ._mcp import LOG_LEVEL_MAPPING, MCPTool
from ._middleware import AgentMiddlewareLayer, MiddlewareTypes
from ._serialization import SerializationMixin
from ._sessions import AgentSession, BaseContextProvider, BaseHistoryProvider, InMemoryHistoryProvider, SessionContext
from ._tools import (
    FunctionInvocationLayer,
    FunctionTool,
    ToolTypes,
    normalize_tools,
)
from ._types import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    ResponseStream,
    map_chat_to_agent_update,
    normalize_messages,
)
from .exceptions import AgentExecutionException
from .observability import AgentTelemetryLayer

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    pass  # type: ignore # pragma: no cover
else:
    pass  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self, TypedDict  # pragma: no cover
else:
    from typing_extensions import Self, TypedDict  # pragma: no cover

if TYPE_CHECKING:
    from ._types import ChatOptions

logger = logging.getLogger("agent_framework")

ResponseModelBoundT = TypeVar("ResponseModelBoundT", bound=BaseModel)
OptionsCoT = TypeVar(
    "OptionsCoT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
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


class _RunContext(TypedDict):
    session: AgentSession | None
    session_context: SessionContext
    input_messages: list[Message]
    session_messages: list[Message]
    agent_name: str
    chat_options: dict[str, Any]
    filtered_kwargs: dict[str, Any]
    finalize_kwargs: dict[str, Any]


# region Agent Protocol


@runtime_checkable
class SupportsAgentRun(Protocol):
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

            from agent_framework import SupportsAgentRun


            # Any class implementing the required methods is compatible
            # No need to inherit from SupportsAgentRun or use any framework classes
            class CustomAgent:
                def __init__(self):
                    self.id = "custom-agent-001"
                    self.name = "Custom Agent"
                    self.description = "A fully custom agent implementation"

                async def run(self, messages=None, *, stream=False, session=None, **kwargs):
                    if stream:
                        # Your custom streaming implementation
                        async def _stream():
                            from agent_framework import AgentResponseUpdate

                            yield AgentResponseUpdate()

                        return _stream()
                    else:
                        # Your custom implementation
                        from agent_framework import AgentResponse

                        return AgentResponse(messages=[], response_id="custom-response")

                def create_session(self, **kwargs):
                    from agent_framework import AgentSession

                    return AgentSession(**kwargs)

                def get_session(self, *, service_session_id, **kwargs):
                    from agent_framework import AgentSession

                    return AgentSession(service_session_id=service_session_id, **kwargs)


            # Verify the instance satisfies the protocol
            instance = CustomAgent()
            assert isinstance(instance, SupportsAgentRun)
    """

    id: str
    name: str | None
    description: str | None

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]:
        """Get a response from the agent (non-streaming)."""
        ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Get a streaming response from the agent."""
        ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Get a response from the agent.

        This method can return either a complete response or stream partial updates
        depending on the stream parameter. Streaming returns a ResponseStream that
        can be iterated for updates and finalized for the full response.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            stream: Whether to stream the response. Defaults to False.
            session: The conversation session associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            When stream=False: An AgentResponse with the final result.
            When stream=True: A ResponseStream of AgentResponseUpdate items with
                ``get_final_response()`` for the final AgentResponse.
        """
        ...

    def create_session(self, **kwargs: Any) -> AgentSession:
        """Creates a new conversation session."""
        ...

    def get_session(self, *, service_session_id: str, **kwargs: Any) -> AgentSession:
        """Gets or creates a session for a service-managed session ID."""
        ...


# region BaseAgent


class BaseAgent(SerializationMixin):
    """Base class for all Agent Framework agents.

    This is the minimal base class without middleware or telemetry layers.
    For most use cases, prefer :class:`Agent` which includes all standard layers.

    This class provides core functionality for agent implementations, including
    context providers, middleware support, and session management.

    Note:
        BaseAgent cannot be instantiated directly as it doesn't implement the
        ``run()`` and other methods required by SupportsAgentRun.
        Use a concrete implementation like Agent or create a subclass.

    Examples:
        .. code-block:: python

            from agent_framework import BaseAgent, AgentSession, AgentResponse


            # Create a concrete subclass that implements the protocol
            class SimpleAgent(BaseAgent):
                async def run(self, messages=None, *, stream=False, session=None, **kwargs):
                    if stream:

                        async def _stream():
                            # Custom streaming implementation
                            yield AgentResponseUpdate()

                        return _stream()
                    else:
                        # Custom implementation
                        return AgentResponse(messages=[], response_id="simple-response")


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
        context_providers: Sequence[BaseContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a BaseAgent instance.

        Keyword Args:
            id: The unique identifier of the agent. If no id is provided,
                a new UUID will be generated.
            name: The name of the agent, can be None.
            description: The description of the agent.
            context_providers: Context providers to include during agent invocation.
            middleware: List of middleware.
            additional_properties: Additional properties set on the agent.
            kwargs: Additional keyword arguments (merged into additional_properties).
        """
        if id is None:
            id = str(uuid4())
        self.id = id
        self.name = name
        self.description = description
        self.context_providers: list[BaseContextProvider] = list(context_providers or [])
        self.middleware: list[MiddlewareTypes] | None = (
            cast(list[MiddlewareTypes], middleware) if middleware is not None else None
        )

        # Merge kwargs into additional_properties
        self.additional_properties: dict[str, Any] = cast(dict[str, Any], additional_properties or {})
        self.additional_properties.update(kwargs)

    def create_session(self, *, session_id: str | None = None, **kwargs: Any) -> AgentSession:
        """Create a new lightweight session.

        Keyword Args:
            session_id: Optional session ID (generated if not provided).
            kwargs: Additional keyword arguments.

        Returns:
            A new AgentSession instance.
        """
        return AgentSession(session_id=session_id)

    def get_session(self, *, service_session_id: str, session_id: str | None = None, **kwargs: Any) -> AgentSession:
        """Get or create a session for a service-managed session ID.

        Args:
            service_session_id: The service-managed session ID.

        Keyword Args:
            session_id: Optional local session ID (generated if not provided).
            kwargs: Additional keyword arguments.

        Returns:
            A new AgentSession instance with service_session_id set.
        """
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    async def _run_after_providers(
        self,
        *,
        session: AgentSession | None,
        context: SessionContext,
    ) -> None:
        """Run after_run on all context providers in reverse order.

        Keyword Args:
            session: The conversation session.
            context: The invocation context with response populated.
        """
        provider_session = session
        if provider_session is None and self.context_providers:
            provider_session = AgentSession()

        for provider in reversed(self.context_providers):
            if provider_session is None:
                raise RuntimeError("Provider session must be available when context providers are configured.")
            await provider.after_run(
                agent=self,  # type: ignore[arg-type]
                session=provider_session,
                context=context,
                state=provider_session.state.setdefault(provider.source_id, {}),
            )

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
    ) -> FunctionTool:
        """Create a FunctionTool that wraps this agent.

        Keyword Args:
            name: The name for the tool. If None, uses the agent's name.
            description: The description for the tool. If None, uses the agent's description or empty string.
            arg_name: The name of the function argument (default: "task").
            arg_description: The description for the function argument.
                If None, defaults to "Task for {tool_name}".
            stream_callback: Optional callback for streaming responses. If provided, uses run(..., stream=True).

        Returns:
            A FunctionTool that can be used as a tool by other agents.

        Raises:
            TypeError: If the agent does not implement SupportsAgentRun.
            ValueError: If the agent tool name cannot be determined.

        Examples:
            .. code-block:: python

                from agent_framework import Agent

                # Create an agent
                agent = Agent(client=client, name="research-agent", description="Performs research tasks")

                # Convert the agent to a tool
                research_tool = agent.as_tool()

                # Use the tool with another agent
                coordinator = Agent(client=client, name="coordinator", tools=research_tool)
        """
        # Verify that self implements SupportsAgentRun
        if not isinstance(self, SupportsAgentRun):
            raise TypeError(f"Agent {self.__class__.__name__} must implement SupportsAgentRun to be used as a tool")

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
            forwarded_kwargs = {k: v for k, v in kwargs.items() if k not in (arg_name, "conversation_id", "options")}

            if stream_callback is None:
                # Use non-streaming mode
                return (await self.run(input_text, stream=False, **forwarded_kwargs)).text

            # Use streaming mode - accumulate updates and create final response
            response_updates: list[AgentResponseUpdate] = []
            async for update in self.run(input_text, stream=True, **forwarded_kwargs):
                response_updates.append(update)
                if is_async_callback:
                    await stream_callback(update)  # type: ignore[misc]
                else:
                    stream_callback(update)

            # Create final text from accumulated updates
            return AgentResponse.from_updates(response_updates).text

        agent_tool: FunctionTool = FunctionTool(
            name=tool_name,
            description=tool_description,
            func=agent_wrapper,
            input_model=input_model,  # type: ignore
            approval_mode="never_require",
        )
        agent_tool._forward_runtime_kwargs = True  # type: ignore
        return agent_tool


# region Agent


class RawAgent(BaseAgent, Generic[OptionsCoT]):  # type: ignore[misc]
    """A Chat Client Agent without middleware or telemetry layers.

    This is the core chat agent implementation. For most use cases,
    prefer :class:`Agent` which includes all standard layers.

    This is the primary agent implementation that uses a chat client to interact
    with language models. It supports tools, context providers, middleware, and
    both streaming and non-streaming responses.

    The generic type parameter TOptions specifies which options TypedDict this agent
    accepts. This enables IDE autocomplete and type checking for provider-specific options.

    Examples:
        Basic usage:

        .. code-block:: python

            from agent_framework import Agent
            from agent_framework.openai import OpenAIChatClient

            # Create a basic chat agent
            client = OpenAIChatClient(model_id="gpt-4")
            agent = Agent(client=client, name="assistant", description="A helpful assistant")

            # Run the agent with a simple message
            response = await agent.run("Hello, how are you?")
            print(response.text)

        With tools and streaming:

        .. code-block:: python

            # Create an agent with tools and instructions
            def get_weather(location: str) -> str:
                return f"The weather in {location} is sunny."


            agent = Agent(
                client=client,
                name="weather-agent",
                instructions="You are a weather assistant.",
                tools=get_weather,
                temperature=0.7,
                max_tokens=500,
            )

            # Use streaming responses
            stream = agent.run("What's the weather in Paris?", stream=True)
            async for update in stream:
                print(update.text, end="")
            final = await stream.get_final_response()

        With typed options for IDE autocomplete:

        .. code-block:: python

            from agent_framework import Agent
            from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

            client = OpenAIChatClient(model_id="gpt-4o")
            agent: Agent[OpenAIChatOptions] = Agent(
                client=client,
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
        client: SupportsChatGetResponse[OptionsCoT],
        instructions: str | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsCoT | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a Agent instance.

        Args:
            client: The chat client to use for the agent.
            instructions: Optional instructions for the agent.
                These will be put into the messages sent to the chat client service as a system message.

        Keyword Args:
            id: The unique identifier for the agent. Will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            context_providers: Context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            default_options: A TypedDict containing chat options. When using a typed agent like
                ``Agent[OpenAIChatOptions]``, this enables IDE autocomplete for
                provider-specific options including temperature, max_tokens, model_id,
                tool_choice, and provider-specific options like reasoning_effort.
                You can also create your own TypedDict for custom chat clients.
                Note: response_format typing does not flow into run outputs when set via default_options.
                These can be overridden at runtime via the ``options`` parameter of ``run()``.
            tools: The tools to use for the request.
            kwargs: Any additional keyword arguments. Will be stored as ``additional_properties``.
        """
        opts = dict(default_options) if default_options else {}

        if not isinstance(client, FunctionInvocationLayer) and isinstance(client, BaseChatClient):
            logger.warning(
                "The provided chat client does not support function invoking, this might limit agent capabilities."
            )

        super().__init__(
            id=id,
            name=name,
            description=description,
            context_providers=context_providers,
            **kwargs,
        )
        self.client = client

        # Get tools from options or named parameter (named param takes precedence)
        tools_ = tools if tools is not None else opts.pop("tools", None)

        # Handle instructions - named parameter takes precedence over options
        instructions_ = instructions if instructions is not None else opts.pop("instructions", None)

        # We ignore the MCP Servers here and store them separately,
        # we add their functions to the tools list at runtime
        normalized_tools = normalize_tools(tools_)
        self.mcp_tools: list[MCPTool] = [tool for tool in normalized_tools if isinstance(tool, MCPTool)]
        agent_tools = [tool for tool in normalized_tools if not isinstance(tool, MCPTool)]

        # Build chat options dict
        self.default_options: dict[str, Any] = {
            "model_id": opts.pop("model_id", None) or (getattr(self.client, "model_id", None)),
            "allow_multiple_tool_calls": opts.pop("allow_multiple_tool_calls", None),
            "conversation_id": opts.pop("conversation_id", None),
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

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        If any of the client or local_mcp_tools are context managers,
        they will be entered into the async exit stack to ensure proper cleanup.

        Note:
            This list might be extended in the future.

        Returns:
            The Agent instance.
        """
        for context_manager in chain([self.client], self.mcp_tools):
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
        if hasattr(self.client, "_update_agent_name_and_description") and callable(
            self.client._update_agent_name_and_description
        ):  # type: ignore[reportAttributeAccessIssue, attr-defined]
            self.client._update_agent_name_and_description(self.name, self.description)  # type: ignore[reportAttributeAccessIssue, attr-defined]

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: ChatOptions[ResponseModelBoundT],
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[ResponseModelBoundT]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: OptionsCoT | ChatOptions[None] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Run the agent with the given messages and options.

        Note:
            Since you won't always call ``agent.run()`` directly (it gets called
            through workflows), it is advised to set your default values for
            all the chat client parameters in the agent constructor.
            If both parameters are used, the ones passed to the run methods take precedence.

        Args:
            messages: The messages to process.
            stream: Whether to stream the response. Defaults to False.

        Keyword Args:
            session: The session to use for the agent.
                If None, and no settings for the chat client that indicate otherwise,
                the run will be stateless.
            tools: The tools to use for this specific run (merged with default tools).
            options: A TypedDict containing chat options. When using a typed agent like
                ``Agent[OpenAIChatOptions]``, this enables IDE autocomplete for
                provider-specific options including temperature, max_tokens, model_id,
                tool_choice, and provider-specific options like reasoning_effort.
            kwargs: Additional keyword arguments for the agent.
                Will only be passed to functions that are called.

        Returns:
            When stream=False: An Awaitable[AgentResponse] containing the agent's response.
            When stream=True: A ResponseStream of AgentResponseUpdate items with
                ``get_final_response()`` for the final AgentResponse.
        """
        if not stream:

            async def _run_non_streaming() -> AgentResponse[Any]:
                ctx = await self._prepare_run_context(
                    messages=messages,
                    session=session,
                    tools=tools,
                    options=options,
                    kwargs=kwargs,
                )
                response = await self.client.get_response(  # type: ignore[call-overload]
                    messages=ctx["session_messages"],
                    stream=False,
                    options=ctx["chat_options"],
                    **ctx["filtered_kwargs"],
                )

                if not response:
                    raise AgentExecutionException("Chat client did not return a response.")

                await self._finalize_response(
                    response=response,
                    agent_name=ctx["agent_name"],
                    session=ctx["session"],
                    session_context=ctx["session_context"],
                )
                response_format = ctx["chat_options"].get("response_format")
                if not (
                    response_format is not None
                    and isinstance(response_format, type)
                    and issubclass(response_format, BaseModel)
                ):
                    response_format = None

                return AgentResponse(
                    messages=response.messages,
                    response_id=response.response_id,
                    created_at=response.created_at,
                    usage_details=response.usage_details,
                    value=response.value,
                    response_format=response_format,
                    continuation_token=response.continuation_token,
                    raw_representation=response,
                    additional_properties=response.additional_properties,
                )

            return _run_non_streaming()

        # Use a holder to capture the context created during stream initialization
        ctx_holder: dict[str, _RunContext | None] = {"ctx": None}

        async def _post_hook(response: AgentResponse) -> None:
            ctx = ctx_holder["ctx"]
            if ctx is None:
                return  # No context available (shouldn't happen in normal flow)

            # Update thread with conversation_id derived from streaming raw updates.
            # Using response_id here can break function-call continuation for APIs
            # where response IDs are not valid conversation handles.
            conversation_id = self._extract_conversation_id_from_streaming_response(response)
            # Ensure author names are set for all messages
            for message in response.messages:
                if message.author_name is None:
                    message.author_name = ctx["agent_name"]

            # Propagate conversation_id back to session from streaming updates.
            # For Responses-style APIs this can rotate every turn (response_id-based continuation),
            # so refresh when a newer value is returned.
            sess = ctx["session"]
            if sess and conversation_id and sess.service_session_id != conversation_id:
                sess.service_session_id = conversation_id

            # Run after_run providers (reverse order)
            session_context = ctx["session_context"]
            session_context._response = AgentResponse(  # type: ignore[assignment]
                messages=response.messages,
                response_id=response.response_id,
            )
            await self._run_after_providers(session=ctx["session"], context=session_context)

        async def _get_stream() -> ResponseStream[ChatResponseUpdate, ChatResponse]:
            ctx_holder["ctx"] = await self._prepare_run_context(
                messages=messages,
                session=session,
                tools=tools,
                options=options,
                kwargs=kwargs,
            )
            ctx: _RunContext = ctx_holder["ctx"]  # type: ignore[assignment]  # Safe: we just assigned it
            return self.client.get_response(  # type: ignore[call-overload, no-any-return]
                messages=ctx["session_messages"],
                stream=True,
                options=ctx["chat_options"],
                **ctx["filtered_kwargs"],
            )

        return (
            ResponseStream
            .from_awaitable(_get_stream())
            .map(
                transform=partial(
                    map_chat_to_agent_update,
                    agent_name=self.name,
                ),
                finalizer=partial(
                    self._finalize_response_updates, response_format=options.get("response_format") if options else None
                ),
            )
            .with_result_hook(_post_hook)
        )

    def _finalize_response_updates(
        self,
        updates: Sequence[AgentResponseUpdate],
        *,
        response_format: Any | None = None,
    ) -> AgentResponse:
        """Finalize response updates into a single AgentResponse."""
        output_format_type = response_format if isinstance(response_format, type) else None
        return AgentResponse.from_updates(updates, output_format_type=output_format_type)

    @staticmethod
    def _extract_conversation_id_from_streaming_response(response: AgentResponse[Any]) -> str | None:
        """Extract conversation_id from streaming raw updates, if present."""
        raw = response.raw_representation
        if raw is None:
            return None

        raw_items: list[Any] = raw if isinstance(raw, list) else [raw]
        for item in reversed(raw_items):
            if isinstance(item, Mapping):
                value = item.get("conversation_id")
                if isinstance(value, str) and value:
                    return value
                continue

            value = getattr(item, "conversation_id", None)
            if isinstance(value, str) and value:
                return value

        return None

    async def _prepare_run_context(
        self,
        *,
        messages: AgentRunInputs | None,
        session: AgentSession | None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
        options: Mapping[str, Any] | None,
        kwargs: dict[str, Any],
    ) -> _RunContext:
        opts = dict(options) if options else {}

        # Get tools from options or named parameter (named param takes precedence)
        tools_ = tools if tools is not None else opts.pop("tools", None)

        input_messages = normalize_messages(messages)

        # Auto-inject InMemoryHistoryProvider when session is provided, no context providers
        # registered, and no service-side storage indicators
        if (
            session is not None
            and not self.context_providers
            and not session.service_session_id
            and not opts.get("conversation_id")
            and not opts.get("store")
            and not (getattr(self.client, "STORES_BY_DEFAULT", False) and opts.get("store") is not False)
        ):
            self.context_providers.append(InMemoryHistoryProvider())

        active_session = session
        if active_session is None and self.context_providers:
            active_session = AgentSession()

        session_context, chat_options = await self._prepare_session_and_messages(
            session=active_session,
            input_messages=input_messages,
            options=opts,
        )

        # Normalize tools
        normalized_tools = normalize_tools(tools_)
        agent_name = self._get_agent_name()

        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[FunctionTool | Callable[..., Any] | dict[str, Any] | Any] = []
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
            "conversation_id": active_session.service_session_id
            if active_session
            else opts.pop("conversation_id", None),
            "allow_multiple_tool_calls": opts.pop("allow_multiple_tool_calls", None),
            "additional_function_arguments": opts.pop("additional_function_arguments", None),
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
        co = _merge_options(chat_options, run_opts)

        # Build session_messages from session context: context messages + input messages
        session_messages: list[Message] = session_context.get_messages(include_input=True)

        # Ensure session is forwarded in kwargs for tool invocation
        finalize_kwargs = dict(kwargs)
        finalize_kwargs["session"] = active_session
        # Filter chat_options from kwargs to prevent duplicate keyword argument
        filtered_kwargs = {k: v for k, v in finalize_kwargs.items() if k != "chat_options"}

        return {
            "session": active_session,
            "session_context": session_context,
            "input_messages": input_messages,
            "session_messages": session_messages,
            "agent_name": agent_name,
            "chat_options": co,
            "filtered_kwargs": filtered_kwargs,
            "finalize_kwargs": finalize_kwargs,
        }

    async def _finalize_response(
        self,
        response: ChatResponse,
        agent_name: str,
        session: AgentSession | None,
        session_context: SessionContext,
    ) -> None:
        """Finalize response by setting author names and running after_run providers.

        Args:
            response: The chat response to finalize.
            agent_name: The name of the agent to set as author.
            session: The conversation session.
            session_context: The invocation context.
        """
        # Ensure that the author name is set for each message in the response.
        for message in response.messages:
            if message.author_name is None:
                message.author_name = agent_name

        # Propagate conversation_id back to session (e.g. thread ID from Assistants API).
        # For Responses-style APIs this can rotate every turn (response_id-based continuation),
        # so refresh when a newer value is returned.
        if session and response.conversation_id and session.service_session_id != response.conversation_id:
            session.service_session_id = response.conversation_id

        # Set the response on the context for after_run providers
        session_context._response = AgentResponse(  # type: ignore[assignment]
            messages=response.messages,
            response_id=response.response_id,
        )

        # Run after_run providers (reverse order)
        await self._run_after_providers(session=session, context=session_context)

    async def _prepare_session_and_messages(
        self,
        *,
        session: AgentSession | None,
        input_messages: list[Message] | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[SessionContext, dict[str, Any]]:
        """Prepare the session context and messages for agent execution.

        Runs the before_run pipeline on all context providers and assembles
        the chat options from default options and provider-contributed context.

        Keyword Args:
            session: The conversation session (None for stateless invocation).
            input_messages: Messages to process.
            options: Runtime options dict (already copied, safe to mutate).

        Returns:
            A tuple containing:
                - The SessionContext with provider context populated
                - The merged chat options dict
        """
        # Create a shallow copy of options and deep copy non-tool values
        if self.default_options:
            chat_options: dict[str, Any] = {}
            for key, value in self.default_options.items():
                if key == "tools":
                    chat_options[key] = list(value) if value else []
                else:
                    chat_options[key] = deepcopy(value)
        else:
            chat_options = {}

        provider_session = session
        if provider_session is None and self.context_providers:
            provider_session = AgentSession()

        session_context = SessionContext(
            session_id=provider_session.session_id if provider_session else None,
            service_session_id=provider_session.service_session_id if provider_session else None,
            input_messages=input_messages or [],
            options=options or {},
        )

        # Run before_run providers (forward order, skip BaseHistoryProvider with load_messages=False)
        for provider in self.context_providers:
            if isinstance(provider, BaseHistoryProvider) and not provider.load_messages:
                continue
            if provider_session is None:
                raise RuntimeError("Provider session must be available when context providers are configured.")
            await provider.before_run(
                agent=self,  # type: ignore[arg-type]
                session=provider_session,
                context=session_context,
                state=provider_session.state.setdefault(provider.source_id, {}),
            )

        # Merge provider-contributed tools into chat_options
        if session_context.tools:
            if chat_options.get("tools") is not None:
                chat_options["tools"].extend(session_context.tools)
            else:
                chat_options["tools"] = list(session_context.tools)

        # Merge provider-contributed instructions into chat_options
        if session_context.instructions:
            combined_instructions = "\n".join(session_context.instructions)
            if "instructions" in chat_options:
                chat_options["instructions"] = f"{chat_options['instructions']}\n{combined_instructions}"
            else:
                chat_options["instructions"] = combined_instructions

        return session_context, chat_options

    def as_mcp_server(
        self,
        *,
        server_name: str = "Agent",
        version: str | None = None,
        instructions: str | None = None,
        lifespan: Callable[[Server[Any]], AbstractAsyncContextManager[Any]] | None = None,
        **kwargs: Any,
    ) -> Server[Any]:
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

        server: Server[Any] = Server(**server_args)  # type: ignore[call-arg]

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
            schema = agent_tool.parameters()

            tool = types.Tool(
                name=agent_tool.name,
                description=agent_tool.description,
                inputSchema=schema,
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
                args_instance: BaseModel | dict[str, Any] = (
                    agent_tool.input_model(**arguments) if agent_tool.input_model is not None else arguments
                )
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

    def _get_agent_name(self) -> str:
        """Get the agent name for message attribution.

        Returns:
            The agent's name, or 'UnnamedAgent' if no name is set.
        """
        return self.name or "UnnamedAgent"


class Agent(
    AgentTelemetryLayer,
    AgentMiddlewareLayer,
    RawAgent[OptionsCoT],
    Generic[OptionsCoT],
):
    """A Chat Client Agent with middleware, telemetry, and full layer support.

    This is the recommended agent class for most use cases. It includes:
    - Agent middleware support for request/response interception
    - OpenTelemetry-based telemetry for observability

    For a minimal implementation without these features, use :class:`RawAgent`.
    """

    def __init__(
        self,
        client: SupportsChatGetResponse[OptionsCoT],
        instructions: str | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsCoT | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a Agent instance."""
        super().__init__(
            client=client,
            instructions=instructions,
            id=id,
            name=name,
            description=description,
            tools=tools,
            default_options=default_options,
            context_providers=context_providers,
            middleware=middleware,
            **kwargs,
        )

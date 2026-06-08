# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

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

from pydantic import BaseModel

from . import _tools as _tool_utils  # pyright: ignore[reportPrivateUsage]
from ._clients import BaseChatClient, SupportsChatGetResponse
from ._docstrings import apply_layered_docstring
from ._mcp import LOG_LEVEL_MAPPING, MCPTool
from ._middleware import AgentMiddlewareLayer, FunctionInvocationContext, MiddlewareTypes, categorize_middleware
from ._serialization import SerializationMixin
from ._sessions import (
    AgentSession,
    ContextProvider,
    HistoryProvider,
    InMemoryHistoryProvider,
    PerServiceCallHistoryPersistingMiddleware,
    SessionContext,
    is_local_history_conversation_id,
)
from ._tools import FunctionInvocationLayer, FunctionTool, ToolTypes, normalize_tools
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
from .exceptions import AgentInvalidRequestException, AgentInvalidResponseException, UserInputRequiredException
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
    from mcp import types
    from mcp.server.lowlevel import Server

    from ._compaction import CompactionStrategy, TokenizerProtocol
    from ._types import ChatOptions

logger = logging.getLogger("agent_framework")

_append_unique_tools = _tool_utils._append_unique_tools  # pyright: ignore[reportPrivateUsage]
_get_tool_name = _tool_utils._get_tool_name  # pyright: ignore[reportPrivateUsage]

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
        if key == "tools" and (result.get("tools") or value):
            base_tools = normalize_tools(result.get("tools"))
            override_tools = normalize_tools(value)
            result["tools"] = _append_unique_tools(
                list(base_tools),
                override_tools,
                duplicate_error_message="Tool names must be unique.",
            )
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
    input_messages: Sequence[Message]
    session_messages: Sequence[Message]
    agent_name: str
    suppress_response_id: bool
    chat_options: MutableMapping[str, Any]
    compaction_strategy: CompactionStrategy | None
    tokenizer: TokenizerProtocol | None
    client_kwargs: Mapping[str, Any]
    function_invocation_kwargs: Mapping[str, Any]


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

                def create_session(self, *, session_id: str | None = None):
                    from agent_framework import AgentSession

                    return AgentSession(session_id=session_id)

                def get_session(self, service_session_id: str, *, session_id: str | None = None):
                    from agent_framework import AgentSession

                    return AgentSession(service_session_id=service_session_id, session_id=session_id)


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
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
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
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Get a streaming response from the agent."""
        ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
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
            function_invocation_kwargs: Keyword arguments forwarded to tool invocation.
            client_kwargs: Additional client-specific keyword arguments.

        Returns:
            When stream=False: An AgentResponse with the final result.
            When stream=True: A ResponseStream of AgentResponseUpdate items with
                ``get_final_response()`` for the final AgentResponse.
        """
        ...

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        """Creates a new conversation session."""
        ...

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> AgentSession:
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
                async def run(
                    self,
                    messages=None,
                    *,
                    stream=False,
                    session=None,
                    function_invocation_kwargs=None,
                    client_kwargs=None,
                ):
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
    require_per_service_call_history_persistence: bool = False

    def __init__(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
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
        """
        if id is None:
            id = str(uuid4())
        self.id = id
        self.name = name
        self.description = description
        self.context_providers: list[ContextProvider] = list(context_providers or [])
        self.middleware: list[MiddlewareTypes] | None = (
            cast(list[MiddlewareTypes], middleware) if middleware is not None else None
        )
        self.additional_properties: dict[str, Any] = cast(dict[str, Any], additional_properties or {})

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        """Create a new lightweight session.

        This will be used by an agent to hold the persisted session.
        This depends on the service used, in some cases, or with store=True
        this will add the ``service_session_id`` based on the response,
        which is then fed back to the API on the next call.

        In other cases, if there is a HistoryProvider setup in the agent,
        that is used and it can store state in the session.

        If there is no HistoryProvider and store=False or the default of a service is False.
        Then a ``InMemoryHistoryProvider`` instance is added to the agent and used with the session automatically.
        The ``InMemoryHistoryProvider`` stores the messages as `state` in the session by default.

        Keyword Args:
            session_id: Optional session ID (generated if not provided).

        Returns:
            A new AgentSession instance.
        """
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> AgentSession:
        """Get a session for a service-managed session ID.

        Only use this to create a session continuing that session id from a service.
        Otherwise use ``create_session``.

        Args:
            service_session_id: The service-managed session ID.

        Keyword Args:
            session_id: Optional local session ID (generated if not provided).

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

        per_service_call_history_required = self.require_per_service_call_history_persistence and any(
            isinstance(provider, HistoryProvider) for provider in self.context_providers
        )
        for provider in reversed(self.context_providers):
            if per_service_call_history_required and isinstance(provider, HistoryProvider):
                continue
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
        approval_mode: Literal["always_require", "never_require"] = "never_require",
        stream_callback: Callable[[AgentResponseUpdate], Awaitable[None] | None] | None = None,
        propagate_session: bool = False,
    ) -> FunctionTool:
        """Create a FunctionTool that wraps this agent.

        Keyword Args:
            name: The name for the tool. If None, uses the agent's name.
            description: The description for the tool. If None, uses the agent's description or empty string.
            arg_name: The name of the function argument (default: "task").
            arg_description: The description for the function argument.
                If None, defaults to "Task for {tool_name}".
            approval_mode: Whether this delegated tool requires approval before execution.
            stream_callback: Optional callback for streaming responses. If provided, uses run(..., stream=True).
            propagate_session: If True, the parent agent's session is forwarded
                to this sub-agent's ``run()`` call so both agents share the
                same session. Defaults to False.

        Returns:
            A FunctionTool that can be used as a tool by other agents.

        Examples:
            .. code-block:: python

                from agent_framework import Agent

                # Create an agent
                agent = Agent(client=client, name="research-agent", description="Performs research tasks")

                # Convert the agent to a tool (independent session)
                research_tool = agent.as_tool()

                # Convert the agent to a tool (shared session with parent)
                research_tool = agent.as_tool(propagate_session=True)

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

        input_schema = {
            "type": "object",
            "properties": {
                arg_name: {
                    "type": "string",
                    "description": argument_description,
                }
            },
            "required": [arg_name],
            "additionalProperties": False,
        }

        async def _agent_wrapper(ctx: FunctionInvocationContext, **kwargs: Any) -> str:
            """Wrapper function that calls the agent.

            Args:
                ctx: the function invocation context used
                **kwargs: only used to dynamically load the argument that is defined for this tool.
            """
            stream = self.run(
                str(kwargs.get(arg_name, "")),
                stream=True,
                session=ctx.session if propagate_session else None,
                function_invocation_kwargs=dict(ctx.kwargs),
            )
            if stream_callback is not None:
                stream.with_transform_hook(stream_callback)
            final_response = await stream.get_final_response()
            if final_response.user_input_requests:
                raise UserInputRequiredException(contents=final_response.user_input_requests)
            # TODO(Copilot): update once #4331 merges
            return final_response.text

        return FunctionTool(
            name=tool_name,
            description=tool_description,
            func=_agent_wrapper,
            input_model=input_schema,
            approval_mode=approval_mode,
        )


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
            client = OpenAIChatClient(model="gpt-4")
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

            client = OpenAIChatClient(model="gpt-4o")
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
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        require_per_service_call_history_persistence: bool = False,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
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
            require_per_service_call_history_persistence: When True, history providers are invoked
                around each model call instead of once per ``run()`` when the service
                is not already storing history. If service-side storage is active for
                the run, the agent skips local history providers and relies on the
                service-managed conversation instead.
            default_options: A TypedDict containing chat options. When using a typed agent like
                ``Agent[OpenAIChatOptions]``, this enables IDE autocomplete for
                provider-specific options including temperature, max_tokens, model,
                tool_choice, and provider-specific options like reasoning_effort.
                You can also create your own TypedDict for custom chat clients.
                Note: response_format typing does not flow into run outputs when set via default_options.
                These can be overridden at runtime via the ``options`` parameter of ``run()``.
            tools: The tools to use for the request.
            compaction_strategy: Optional agent-level in-run compaction.
                If both this and a compaction_strategy on the underlying client are set, this one is used.
            tokenizer: Optional agent-level tokenizer.
                If both this and a tokenizer on the underlying client are set, this one is used.
            additional_properties: Additional properties stored on the agent.
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
            middleware=middleware,
            additional_properties=additional_properties,
        )
        self.client = client
        self.compaction_strategy = compaction_strategy
        self.require_per_service_call_history_persistence = require_per_service_call_history_persistence
        self.tokenizer = tokenizer

        # Get tools from options or named parameter (named param takes precedence)
        tools_ = tools if tools is not None else opts.pop("tools", None)

        # Handle instructions - named parameter takes precedence over options
        instructions_ = instructions if instructions is not None else opts.pop("instructions", None)

        # We ignore the MCP Servers here and store them separately,
        # we add their functions to the tools list at runtime
        normalized_tools = normalize_tools(tools_)
        self.mcp_tools: list[MCPTool] = [tool for tool in normalized_tools if isinstance(tool, MCPTool)]
        agent_tools = [tool for tool in normalized_tools if not isinstance(tool, MCPTool)]

        model = opts.pop("model", None) or getattr(self.client, "model", None)

        # Build chat options dict
        self.default_options: dict[str, Any] = {
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
        if model is not None:
            self.default_options["model"] = model
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

    def _get_history_providers(self) -> list[HistoryProvider]:
        return [provider for provider in self.context_providers if isinstance(provider, HistoryProvider)]

    def _resolve_per_service_call_history_providers(
        self,
        *,
        session: AgentSession | None,
        options: Mapping[str, Any] | None,
        service_stores_history: bool,
    ) -> list[HistoryProvider]:
        history_providers = self._get_history_providers()
        if not self.require_per_service_call_history_persistence or not history_providers:
            return []

        conversation_id = (
            session.service_session_id
            if session and session.service_session_id
            else cast(str | None, (options or {}).get("conversation_id") or self.default_options.get("conversation_id"))
        )
        if service_stores_history:
            return []

        if conversation_id is not None:
            raise AgentInvalidRequestException(
                "require_per_service_call_history_persistence cannot be used "
                "with an existing service-managed conversation."
            )
        return history_providers

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
        update_fn = getattr(self.client, "_update_agent_name_and_description", None)
        if callable(update_fn):
            update_fn(self.name, self.description)

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: ChatOptions[ResponseModelBoundT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
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
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
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
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
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
                provider-specific options including temperature, max_tokens, model,
                tool_choice, and provider-specific options like reasoning_effort.
            compaction_strategy: Optional per-run compaction override passed to
                ``client.get_response()``. When omitted, the agent-level override
                is used, falling back to the client default.
            tokenizer: Optional per-run tokenizer override passed to
                ``client.get_response()``. When omitted, the agent-level override
                is used, falling back to the client default.
            function_invocation_kwargs: Keyword arguments forwarded to tool invocation.
            client_kwargs: Additional client-specific keyword arguments for the chat client.

        Returns:
            When stream=False: An Awaitable[AgentResponse] containing the agent's response.
            When stream=True: A ResponseStream of AgentResponseUpdate items with
                ``get_final_response()`` for the final AgentResponse.
        """

        async def _prepare_run_context() -> _RunContext:
            return await self._prepare_run_context(
                messages=messages,
                session=session,
                tools=tools,
                options=options,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                function_invocation_kwargs=function_invocation_kwargs,
                client_kwargs=client_kwargs,
            )

        if not stream:

            async def _run_non_streaming() -> AgentResponse[Any]:
                ctx = await _prepare_run_context()
                response = await self._call_chat_client(ctx, stream=False)
                return await self._parse_non_streaming_response(ctx, response)

            return _run_non_streaming()

        async def _run_streaming() -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
            ctx = await _prepare_run_context()
            stream_response = self._call_chat_client(ctx, stream=True)
            return self._parse_streaming_response(ctx, stream_response)

        return cast(
            ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
            cast(Any, ResponseStream).from_awaitable(_run_streaming()),
        )

    @overload
    def _call_chat_client(
        self,
        context: _RunContext,
        *,
        stream: Literal[False],
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def _call_chat_client(
        self,
        context: _RunContext,
        *,
        stream: Literal[True],
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def _call_chat_client(
        self,
        context: _RunContext,
        *,
        stream: bool,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Invoke the downstream chat client for a prepared run context."""
        if stream:
            return self.client.get_response(  # type: ignore[call-overload, no-any-return]
                messages=context["session_messages"],
                stream=True,
                options=context["chat_options"],  # type: ignore[reportArgumentType]
                compaction_strategy=context["compaction_strategy"],
                tokenizer=context["tokenizer"],
                function_invocation_kwargs=context["function_invocation_kwargs"],
                client_kwargs=context["client_kwargs"],
            )

        return self.client.get_response(  # type: ignore[call-overload, no-any-return]
            messages=context["session_messages"],
            stream=False,
            options=context["chat_options"],  # type: ignore[reportArgumentType]
            compaction_strategy=context["compaction_strategy"],
            tokenizer=context["tokenizer"],
            function_invocation_kwargs=context["function_invocation_kwargs"],
            client_kwargs=context["client_kwargs"],
        )

    async def _parse_non_streaming_response(
        self,
        context: _RunContext,
        response: ChatResponse[Any],
    ) -> AgentResponse[Any]:
        """Finalize a non-streaming chat response into an AgentResponse."""
        if not response:
            raise AgentInvalidResponseException("Chat client did not return a response.")

        await self._finalize_response(
            response=response,
            agent_name=context["agent_name"],
            session=context["session"],
            session_context=context["session_context"],
            suppress_response_id=context["suppress_response_id"],
        )
        return AgentResponse(
            messages=response.messages,
            response_id=None if context["suppress_response_id"] else response.response_id,
            created_at=response.created_at,
            usage_details=response.usage_details,
            value=response.value,
            response_format=context["chat_options"].get("response_format"),
            continuation_token=response.continuation_token,
            raw_representation=response,
            additional_properties=response.additional_properties,
        )

    def _parse_streaming_response(
        self,
        context: _RunContext,
        stream_response: ResponseStream[ChatResponseUpdate, ChatResponse[Any]],
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Finalize a streaming chat response into an agent response stream."""

        async def _post_hook(response: AgentResponse) -> None:
            # Update thread with conversation_id derived from streaming raw updates.
            # Using response_id here can break function-call continuation for APIs
            # where response IDs are not valid conversation handles.
            conversation_id = self._extract_conversation_id_from_streaming_response(response)

            for message in response.messages:
                if message.author_name is None:
                    message.author_name = context["agent_name"]

            session = context["session"]
            if (
                session
                and conversation_id
                and not is_local_history_conversation_id(conversation_id)
                and session.service_session_id != conversation_id
            ):
                session.service_session_id = conversation_id

            suppress_response_id = context["suppress_response_id"]
            session_context = context["session_context"]
            session_context._response = AgentResponse(  # type: ignore[assignment]
                messages=response.messages,
                response_id=None if suppress_response_id else response.response_id,
            )
            await self._run_after_providers(session=session, context=session_context)

        def _propagate_conversation_id(update: AgentResponseUpdate) -> AgentResponseUpdate:
            """Eagerly propagate conversation_id to session as updates arrive."""
            session = context["session"]
            if session is None:
                return update
            raw = update.raw_representation
            conversation_id = getattr(raw, "conversation_id", None) if raw else None
            if (
                isinstance(conversation_id, str)
                and conversation_id
                and not is_local_history_conversation_id(conversation_id)
                and session.service_session_id != conversation_id
            ):
                session.service_session_id = conversation_id
            return update

        def _suppress_response_id(update: AgentResponseUpdate) -> AgentResponseUpdate:
            """Hide raw service response ids when local per-service-call persistence owns continuation."""
            update.response_id = None
            return update

        def _finalizer(updates: Sequence[AgentResponseUpdate]) -> AgentResponse[Any]:
            return self._finalize_response_updates(
                updates,
                response_format=context["chat_options"].get("response_format"),
            )

        stream = stream_response.map(
            transform=partial(
                map_chat_to_agent_update,
                agent_name=self.name,
            ),
            finalizer=_finalizer,
        )
        if context["suppress_response_id"]:
            stream = stream.with_transform_hook(_suppress_response_id)

        return stream.with_transform_hook(_propagate_conversation_id).with_result_hook(_post_hook)

    def _finalize_response_updates(
        self,
        updates: Sequence[AgentResponseUpdate],
        *,
        response_format: Any | None = None,
    ) -> AgentResponse[Any]:
        """Finalize response updates into a single AgentResponse."""
        return AgentResponse.from_updates(  # pyright: ignore[reportUnknownVariableType]
            updates,
            output_format_type=response_format,
        )

    @staticmethod
    def _extract_conversation_id_from_streaming_response(
        response: AgentResponse[Any],
    ) -> str | None:
        """Extract conversation_id from streaming raw updates, if present."""
        raw = response.raw_representation
        if raw is None:
            return None

        raw_items: list[Any] = list(cast(Any, raw)) if isinstance(raw, list) else [raw]
        for item in reversed(raw_items):
            if isinstance(item, Mapping):
                mapped_item = cast(Mapping[str, Any], item)
                value = mapped_item.get("conversation_id")
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
        compaction_strategy: CompactionStrategy | None,
        tokenizer: TokenizerProtocol | None,
        function_invocation_kwargs: Mapping[str, Any] | None,
        client_kwargs: Mapping[str, Any] | None,
    ) -> _RunContext:
        opts = dict(options) if options else {}
        existing_additional_args: dict[str, Any] = opts.pop("additional_function_arguments", None) or {}

        # Get tools from options or named parameter (named param takes precedence)
        tools_ = tools if tools is not None else opts.pop("tools", None)

        input_messages = normalize_messages(messages)

        # `store` in runtime or agent options takes precedence over client-level storage
        # indicators. An explicit `store=False` forces local (in-memory) history injection,
        # even if the client is configured to use service-side storage by default.
        store_ = opts.get("store", self.default_options.get("store", getattr(self.client, "STORES_BY_DEFAULT", False)))
        # Auto-inject InMemoryHistoryProvider when session is provided, no context providers
        # registered, and no service-side storage indicators
        if (
            session is not None
            and not self.context_providers
            and not session.service_session_id
            and not opts.get("conversation_id")
            and not store_
        ):
            self.context_providers.append(InMemoryHistoryProvider())

        active_session = session
        if active_session is None and self.context_providers:
            active_session = AgentSession()

        per_service_call_history_providers = self._resolve_per_service_call_history_providers(
            session=active_session,
            options=opts,
            service_stores_history=bool(store_),
        )

        session_context, chat_options = await self._prepare_session_and_messages(
            session=active_session,
            input_messages=input_messages,
            options=opts,
        )
        default_additional_args = chat_options.pop("additional_function_arguments", None)
        if isinstance(default_additional_args, Mapping):
            existing_additional_args = {
                **dict(cast(Mapping[str, Any], default_additional_args)),
                **existing_additional_args,
            }

        agent_name = self._get_agent_name()
        base_tools = normalize_tools(chat_options.pop("tools", None))
        mcp_duplicate_message = "Tool names must be unique. Consider setting `tool_name_prefix` on the MCPTool."

        # Normalize tools
        normalized_tools = normalize_tools(tools_)

        # Resolve final tool list (configured tools + runtime provided tools + local MCP server tools)
        final_tools = list(base_tools)
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                if not tool.is_connected:
                    await self._async_exit_stack.enter_async_context(tool)
                _append_unique_tools(
                    final_tools,
                    tool.functions,
                    duplicate_error_message=mcp_duplicate_message,
                )
            else:
                _append_unique_tools(final_tools, [tool])  # type: ignore[list-item]

        for mcp_server in self.mcp_tools:
            if not mcp_server.is_connected:
                await self._async_exit_stack.enter_async_context(mcp_server)
            _append_unique_tools(
                final_tools,
                mcp_server.functions,
                duplicate_error_message=mcp_duplicate_message,
            )

        effective_function_invocation_kwargs = (
            dict(function_invocation_kwargs) if function_invocation_kwargs is not None else {}
        )
        additional_function_arguments = {**effective_function_invocation_kwargs, **existing_additional_args}

        model = opts.pop("model", None)

        # Build options dict from run() options merged with provided options
        run_opts: dict[str, Any] = {
            "conversation_id": active_session.service_session_id
            if active_session
            else opts.pop("conversation_id", None),
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
            "tools": final_tools or None,
            "top_p": opts.pop("top_p", None),
            "user": opts.pop("user", None),
            **opts,  # Remaining options are provider-specific
        }
        if model is not None:
            run_opts["model"] = model
        # Remove None values and merge with chat_options
        run_opts = {k: v for k, v in run_opts.items() if v is not None}
        co = _merge_options(chat_options, run_opts)

        # Build session_messages from session context: context messages + input messages
        session_messages: list[Message] = session_context.get_messages(include_input=True)

        effective_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        if active_session is not None:
            effective_client_kwargs["session"] = active_session
        if per_service_call_history_providers and active_session is not None:
            per_service_call_history_middleware = PerServiceCallHistoryPersistingMiddleware(
                agent=self,
                session=active_session,
                providers=per_service_call_history_providers,
            )
            existing_middleware = effective_client_kwargs.get("middleware")
            if isinstance(existing_middleware, Sequence) and not isinstance(existing_middleware, (str, bytes)):
                effective_client_kwargs["middleware"] = [per_service_call_history_middleware, *existing_middleware]
            elif existing_middleware is not None:
                effective_client_kwargs["middleware"] = [
                    per_service_call_history_middleware,
                    cast(MiddlewareTypes, existing_middleware),
                ]
            else:
                effective_client_kwargs["middleware"] = [per_service_call_history_middleware]
        provider_middleware = session_context.get_middleware()
        if provider_middleware:
            middleware_list = categorize_middleware(provider_middleware)
            provider_function_chat_middleware = [
                *middleware_list["function"],
                *middleware_list["chat"],
            ]
            if provider_function_chat_middleware:
                existing_middleware = effective_client_kwargs.get("middleware")
                if isinstance(existing_middleware, Sequence) and not isinstance(existing_middleware, (str, bytes)):
                    effective_client_kwargs["middleware"] = [
                        *existing_middleware,
                        *provider_function_chat_middleware,
                    ]
                elif existing_middleware is not None:
                    effective_client_kwargs["middleware"] = [
                        cast(MiddlewareTypes, existing_middleware),
                        *provider_function_chat_middleware,
                    ]
                else:
                    effective_client_kwargs["middleware"] = provider_function_chat_middleware

        return {
            "session": active_session,
            "session_context": session_context,
            "input_messages": input_messages,
            "session_messages": session_messages,
            "agent_name": agent_name,
            "suppress_response_id": bool(per_service_call_history_providers),
            "chat_options": co,
            "compaction_strategy": compaction_strategy or self.compaction_strategy,
            "tokenizer": tokenizer or self.tokenizer,
            "client_kwargs": effective_client_kwargs,
            "function_invocation_kwargs": additional_function_arguments,
        }

    async def _finalize_response(
        self,
        response: ChatResponse,
        agent_name: str,
        session: AgentSession | None,
        session_context: SessionContext,
        suppress_response_id: bool = False,
    ) -> None:
        """Finalize response by setting author names and running after_run providers.

        Args:
            response: The chat response to finalize.
            agent_name: The name of the agent to set as author.
            session: The conversation session.
            session_context: The invocation context.
            suppress_response_id: When True, omit the raw service response ID from the public response.
        """
        # Ensure that the author name is set for each message in the response.
        for message in response.messages:
            if message.author_name is None:
                message.author_name = agent_name

        # Propagate conversation_id back to session (e.g. thread ID from Assistants API).
        # For Responses-style APIs this can rotate every turn (response_id-based continuation),
        # so refresh when a newer value is returned.
        if (
            session
            and response.conversation_id
            and not is_local_history_conversation_id(response.conversation_id)
            and session.service_session_id != response.conversation_id
        ):
            session.service_session_id = response.conversation_id

        # Set the response on the context for after_run providers
        session_context._response = AgentResponse(  # type: ignore[assignment]
            messages=response.messages,
            response_id=None if suppress_response_id else response.response_id,
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

        per_service_call_history_required = self.require_per_service_call_history_persistence and bool(
            self._get_history_providers()
        )

        # Run before_run providers (forward order, skip HistoryProvider when per-service-call persistence owns history)
        for provider in self.context_providers:
            if per_service_call_history_required and isinstance(provider, HistoryProvider):
                continue
            if isinstance(provider, HistoryProvider) and not provider.load_messages:
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
        try:
            from mcp import types
            from mcp.server.lowlevel import Server
            from mcp.shared.exceptions import McpError
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "`mcp` is required to use `Agent.as_mcp_server()`. Please install `mcp`."
            ) from exc

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

            # Convert result to MCP content.
            # Currently only text items are forwarded over MCP; rich content
            # (images, audio) is not yet supported in the MCP server path.
            mcp_content: list[types.TextContent | types.ImageContent | types.EmbeddedResource] = []  # type: ignore[attr-defined]
            for c in result:
                if c.type == "text" and c.text:
                    mcp_content.append(types.TextContent(type="text", text=c.text))  # type: ignore[attr-defined]
                elif c.type in ("data", "uri"):
                    logger.warning(
                        "MCP server does not yet forward rich content (images, audio) "
                        "in tool results. Rich content items will be omitted."
                    )
            return mcp_content or [types.TextContent(type="text", text="")]  # type: ignore[attr-defined]

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
    AgentMiddlewareLayer,
    AgentTelemetryLayer,
    RawAgent[OptionsCoT],
    Generic[OptionsCoT],
):
    """A Chat Client Agent with middleware, telemetry, and full layer support.

    This is the recommended agent class for most use cases. It includes:
    - Agent middleware support for request/response interception
    - OpenTelemetry-based telemetry for observability

    For a minimal implementation without these features, use :class:`RawAgent`.
    """

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: ChatOptions[ResponseModelBoundT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[ResponseModelBoundT]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: OptionsCoT | ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Run the agent."""
        super_run = cast(
            "Callable[..., Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]]",
            super().run,  # type: ignore[misc]
        )
        return super_run(  # type: ignore[no-any-return]
            messages=messages,
            stream=stream,
            session=session,
            middleware=middleware,
            tools=tools,
            options=options,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
        )

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
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        require_per_service_call_history_persistence: bool = False,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
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
            require_per_service_call_history_persistence=require_per_service_call_history_persistence,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
        )


def _apply_agent_docstrings() -> None:
    """Align public agent docstrings with the raw implementation."""
    apply_layered_docstring(
        AgentMiddlewareLayer.run,
        RawAgent.run,
        extra_keyword_args={
            "middleware": """
                Optional per-run agent, chat, and function middleware.
                Agent middleware wraps the run itself, while chat and function middleware are forwarded to the
                underlying chat-client stack for this call.
            """,
        },
    )
    apply_layered_docstring(AgentTelemetryLayer.run, AgentMiddlewareLayer.run)
    apply_layered_docstring(
        Agent.run,
        RawAgent.run,
        extra_keyword_args={
            "middleware": """
                Optional per-run agent, chat, and function middleware.
                Agent middleware wraps the run itself, while chat and function middleware are forwarded to the
                underlying chat-client stack for this call.
            """,
        },
    )
    apply_layered_docstring(Agent.__init__, RawAgent.__init__)


_apply_agent_docstrings()

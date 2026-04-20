# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, MutableMapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, cast, overload

from agent_framework import (
    AgentMiddlewareLayer,
    AgentMiddlewareTypes,
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    Content,
    ContextProvider,
    Message,
    MiddlewareTypes,
    ResponseStream,
    ToolTypes,
    load_settings,
    normalize_messages,
    normalize_tools,
)
from agent_framework.exceptions import AgentException
from agent_framework.observability import AgentTelemetryLayer
from codex_sdk import (
    Codex,
    CodexOptions,
    Thread,
    ThreadOptions,
)
from codex_sdk.events import (
    ItemUpdatedEvent,
    ThreadErrorEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
)
from codex_sdk.items import (
    AgentMessageItem,
    ErrorItem,
    ReasoningItem,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover

if TYPE_CHECKING:
    from codex_sdk import (
        ApprovalMode,
        ModelReasoningEffort,
        SandboxMode,
    )


logger = logging.getLogger("agent_framework.codex")


class CodexAgentSettings(TypedDict, total=False):
    """Codex Agent settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'CODEX_AGENT_'.

    Keys:
        codex_path: The path to Codex CLI executable.
        model: The model to use (codex-mini-latest, gpt-5.1-codex).
        cwd: The working directory for Codex CLI.
        approval_policy: Approval policy (default, full-auto, plan).
    """

    codex_path: str | None
    model: str | None
    cwd: str | None
    approval_policy: str | None


class CodexAgentOptions(TypedDict, total=False):
    """Codex Agent-specific options."""

    system_prompt: str
    """System prompt for the agent."""

    codex_path: str
    """Path to Codex CLI executable. Default: auto-detected."""

    cwd: str
    """Working directory for Codex CLI. Default: current working directory."""

    env: dict[str, str]
    """Environment variables to pass to CLI."""

    model: str
    """Model to use ("codex-mini-latest", "gpt-5.1-codex"). Default: "codex-mini-latest"."""

    sandbox_mode: SandboxMode
    """Sandbox mode for code execution."""

    model_reasoning_effort: ModelReasoningEffort
    """Model reasoning effort preset."""

    approval_policy: ApprovalMode
    """Approval policy for tool execution."""

    additional_directories: list[str]
    """Additional directories to add to context."""

    config_overrides: dict[str, Any]
    """Additional configuration overrides passed to the Codex CLI."""


OptionsT = TypeVar(
    "OptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="CodexAgentOptions",
    covariant=True,
)


class RawCodexAgent(BaseAgent, Generic[OptionsT]):
    """OpenAI Codex Agent using Codex CLI without telemetry layers.

    This is the core Codex agent implementation without OpenTelemetry instrumentation.
    For most use cases, prefer :class:`CodexAgent` which includes telemetry and
    middleware support.

    Wraps the Codex SDK to provide agentic coding capabilities including
    tool use, session management, and streaming responses.

    This agent communicates with Codex through the Codex CLI,
    enabling access to Codex's full agentic capabilities like file
    editing, code execution, and tool use.

    The agent can be used as an async context manager to ensure proper cleanup:

    Examples:
        Basic usage with context manager:

        .. code-block:: python

            from agent_framework_codex import CodexAgent

            async with CodexAgent(
                instructions="You are a helpful coding assistant.",
            ) as agent:
                response = await agent.run("Hello!")
                print(response.text)

        With streaming:

        .. code-block:: python

            async with CodexAgent() as agent:
                async for update in agent.run("Write a poem", stream=True):
                    print(update.text, end="", flush=True)

        With session management:

        .. code-block:: python

            async with CodexAgent() as agent:
                session = agent.create_session()
                await agent.run("Remember my name is Alice", session=session)
                response = await agent.run("What's my name?", session=session)
                # Codex will remember "Alice" from the same thread

        With Agent Framework tools:

        .. code-block:: python

            from agent_framework import tool

            @tool
            def greet(name: str) -> str:
                \"\"\"Greet someone by name.\"\"\"
                return f"Hello, {name}!"

            async with CodexAgent(tools=[greet]) as agent:
                response = await agent.run("Greet Alice")
    """

    AGENT_PROVIDER_NAME: ClassVar[str] = "openai"

    def __init__(
        self,
        instructions: str | None = None,
        *,
        client: Codex | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | str | Sequence[ToolTypes | Callable[..., Any] | str] | None = None,
        default_options: OptionsT | MutableMapping[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a RawCodexAgent instance.

        Args:
            instructions: System prompt for the agent.

        Keyword Args:
            client: Optional pre-configured Codex instance. If not provided,
                a new client will be created using the other parameters.
            id: Unique identifier for the agent.
            name: Name of the agent.
            description: Description of the agent.
            context_providers: Context providers for the agent.
            middleware: List of middleware.
            tools: Tools for the agent. Can be:
                - Strings for built-in tools (e.g., "Read", "Write", "Bash", "Glob")
                - Functions for custom tools
            default_options: Default CodexAgentOptions including system_prompt, model, etc.
            env_file_path: Path to .env file.
            env_file_encoding: Encoding of .env file.
        """
        super().__init__(
            id=id,
            name=name,
            description=description,
            context_providers=context_providers,
            middleware=middleware,
        )

        self._client = client
        self._owns_client = client is None

        # Parse options
        opts: dict[str, Any] = dict(default_options) if default_options else {}

        # Handle instructions parameter - set as system_prompt in options
        if instructions is not None:
            opts["system_prompt"] = instructions

        codex_path = opts.pop("codex_path", None)
        model = opts.pop("model", None)
        cwd = opts.pop("cwd", None)
        approval_policy = opts.pop("approval_policy", None)

        # Load settings from environment and options
        self._settings = load_settings(
            CodexAgentSettings,
            env_prefix="CODEX_AGENT_",
            codex_path=codex_path,
            model=model,
            cwd=cwd,
            approval_policy=approval_policy,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        # Separate built-in tools (strings) from custom tools (callables/FunctionTool)
        self._builtin_tools: list[str] = []
        self._custom_tools: list[ToolTypes] = []
        self._normalize_tools(tools)

        self._default_options = opts
        self._current_thread: Thread | None = None
        self._current_thread_id: str | None = None

    def _normalize_tools(
        self,
        tools: ToolTypes | Callable[..., Any] | str | Sequence[ToolTypes | Callable[..., Any] | str] | None,
    ) -> None:
        """Separate built-in tools (strings) from custom tools.

        Args:
            tools: Mixed list of tool names and custom tools.
        """
        if tools is None:
            return

        # Normalize to sequence
        if isinstance(tools, str):
            tools_list: Sequence[Any] = [tools]
        elif isinstance(tools, Sequence):
            tools_list = list(tools)
        else:
            tools_list = [tools]

        for tool in tools_list:
            if isinstance(tool, str):
                self._builtin_tools.append(tool)
            else:
                # Use normalize_tools for custom tools
                normalized = normalize_tools(tool)
                self._custom_tools.extend(normalized)

    async def __aenter__(self) -> RawCodexAgent[OptionsT]:
        """Start the agent when entering async context."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the agent when exiting async context."""
        await self.stop()

    async def start(self) -> None:
        """Start the Codex SDK client.

        This method initializes the Codex client. It is called automatically
        when using the agent as an async context manager.

        Raises:
            AgentException: If the client fails to start.
        """
        if self._client is None:
            try:
                self._client = self._create_codex_client()
                self._owns_client = True
            except Exception as ex:
                raise AgentException(f"Failed to create Codex client: {ex}") from ex

    async def stop(self) -> None:
        """Stop the Codex SDK client and clean up resources.

        Stops the client if owned by this agent. Called automatically when
        using the agent as an async context manager.
        """
        self._current_thread = None
        self._current_thread_id = None
        if self._owns_client:
            self._client = None

    def _create_codex_client(self) -> Codex:
        """Create a Codex client with configured options.

        Returns:
            A configured Codex instance.
        """
        codex_path = self._settings.get("codex_path")
        env = self._default_options.get("env")

        codex_opts = CodexOptions(
            codex_path_override=codex_path,
            env=env,
        )

        return Codex(options=codex_opts)

    def _prepare_thread_options(self) -> ThreadOptions:
        """Prepare ThreadOptions from settings and default options.

        Returns:
            ThreadOptions instance configured for the thread.
        """
        thread_opts_kwargs: dict[str, Any] = {}

        # Apply settings from environment
        if model := self._settings.get("model"):
            thread_opts_kwargs["model"] = model
        if cwd := self._settings.get("cwd"):
            thread_opts_kwargs["working_directory"] = cwd
        if approval_policy := self._settings.get("approval_policy"):
            thread_opts_kwargs["approval_policy"] = approval_policy

        # Apply default options (those not consumed by settings)
        for key in ("sandbox_mode", "model_reasoning_effort", "additional_directories", "config_overrides"):
            if key in self._default_options and self._default_options[key] is not None:
                thread_opts_kwargs[key] = self._default_options[key]

        # Pass system prompt via config_overrides if set
        system_prompt = self._default_options.get("system_prompt")
        if system_prompt:
            overrides = dict(thread_opts_kwargs.get("config_overrides") or {})
            overrides["instructions"] = system_prompt
            thread_opts_kwargs["config_overrides"] = overrides

        # Write a temporary instructions file if we have a system prompt
        if system_prompt and "model_instructions_file" not in thread_opts_kwargs:
            import os
            import tempfile

            fd, path = tempfile.mkstemp(suffix=".md", prefix="codex_instructions_")
            try:
                os.write(fd, system_prompt.encode("utf-8"))
            finally:
                os.close(fd)
            thread_opts_kwargs["model_instructions_file"] = path

        return ThreadOptions(**thread_opts_kwargs)

    def _get_or_create_thread(self, session_id: str | None = None) -> Thread:
        """Get or create a thread for the given session.

        If session_id matches the current thread, reuse it.
        Otherwise, create a new thread or resume an existing one.

        Args:
            session_id: The thread/session ID to resume, or None for a new thread.

        Returns:
            A Thread instance.
        """
        if self._client is None:
            raise RuntimeError("Codex client not initialized. Call start() first.")

        # Reuse current thread if session matches
        if self._current_thread is not None and session_id == self._current_thread_id:
            return self._current_thread

        thread_opts = self._prepare_thread_options()

        if session_id:
            thread = self._client.resume_thread(session_id, options=thread_opts)
        else:
            thread = self._client.start_thread(options=thread_opts)

        self._current_thread = thread
        self._current_thread_id = session_id

        return thread

    def _format_prompt(self, messages: list[Message] | None) -> str:
        """Format messages into a prompt string.

        Args:
            messages: List of chat messages.

        Returns:
            Formatted prompt string.
        """
        if not messages:
            return ""
        return "\n".join([msg.text or "" for msg in messages])

    @property
    def default_options(self) -> dict[str, Any]:
        """Expose options with ``instructions`` key.

        Maps ``system_prompt`` to ``instructions`` for compatibility with
        :class:`AgentTelemetryLayer`, which reads the system prompt from
        the ``instructions`` key.
        """
        opts = dict(self._default_options)
        system_prompt = opts.pop("system_prompt", None)
        if system_prompt is not None:
            opts["instructions"] = system_prompt
        return opts

    def _finalize_response(self, updates: Sequence[AgentResponseUpdate]) -> AgentResponse[Any]:
        """Build AgentResponse from collected updates.

        Args:
            updates: The collected stream updates.

        Returns:
            An AgentResponse built from the updates.
        """
        return AgentResponse.from_updates(updates)

    @overload
    def run(  # type: ignore[override]
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        options: OptionsT | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(  # type: ignore[override]
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        options: OptionsT | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        options: OptionsT | None = None,
        **kwargs: Any,  # type: ignore
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Run the agent with the given messages.

        Args:
            messages: The messages to process.

        Keyword Args:
            stream: If True, returns an async iterable of updates. If False (default),
                returns an awaitable AgentResponse.
            session: The conversation session. If session has service_session_id set,
                the agent will resume that thread.
            options: Runtime options (model can be changed per-request via config_overrides).
            kwargs: Additional keyword arguments for compatibility with the shared agent
                interface (e.g. compaction_strategy, tokenizer). Not used by CodexAgent.

        Returns:
            When stream=True: An ResponseStream for streaming updates.
            When stream=False: An Awaitable[AgentResponse] with the complete response.
        """
        response = ResponseStream(
            self._get_stream(messages, session=session, options=options),
            finalizer=self._finalize_response,
        )
        if stream:
            return response
        return response.get_final_response()

    async def _get_stream(
        self,
        messages: AgentRunInputs | None = None,
        *,
        session: AgentSession | None = None,
        options: OptionsT | None = None,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Internal streaming implementation."""
        session = session or self.create_session()

        # Ensure client is initialized
        if self._client is None:
            await self.start()

        # Get or create thread for this session
        thread = self._get_or_create_thread(session.service_session_id)

        prompt = self._format_prompt(normalize_messages(messages))

        async for event in thread.run_streamed_events(prompt):
            if isinstance(event, ItemUpdatedEvent):
                item = event.item
                if isinstance(item, AgentMessageItem):
                    # Yield text content from agent messages
                    if item.text:
                        yield AgentResponseUpdate(
                            role="assistant",
                            contents=[Content.from_text(text=item.text, raw_representation=event)],
                            raw_representation=event,
                        )
                elif isinstance(item, ReasoningItem):
                    # Yield reasoning/thinking content
                    if item.text:
                        yield AgentResponseUpdate(
                            role="assistant",
                            contents=[Content.from_text_reasoning(text=item.text, raw_representation=event)],
                            raw_representation=event,
                        )
                elif isinstance(item, ErrorItem):
                    raise AgentException(f"Codex API error: {item.message}")

            elif isinstance(event, TurnFailedEvent):
                error = event.error
                raise AgentException(f"Codex turn failed: {error}")

            elif isinstance(event, ThreadErrorEvent):
                raise AgentException(f"Codex thread error: {event}")

            elif isinstance(event, TurnCompletedEvent):
                # Turn completed — update session with thread ID
                if thread.id:
                    session.service_session_id = thread.id
                    self._current_thread_id = thread.id


class CodexAgent(AgentMiddlewareLayer, AgentTelemetryLayer, RawCodexAgent[OptionsT], Generic[OptionsT]):
    """OpenAI Codex Agent with middleware and OpenTelemetry instrumentation.

    This is the recommended agent class for most use cases. It includes
    OpenTelemetry-based telemetry for observability and middleware support
    for intercepting agent invocations. For a minimal implementation
    without telemetry or middleware, use :class:`RawCodexAgent`.

    Examples:
        Basic usage with context manager:

        .. code-block:: python

            from agent_framework_codex import CodexAgent

            async with CodexAgent(
                instructions="You are a helpful coding assistant.",
            ) as agent:
                response = await agent.run("Hello!")
                print(response.text)
    """

    def __init__(
        self,
        instructions: str | None = None,
        *,
        client: Codex | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | str | Sequence[ToolTypes | Callable[..., Any] | str] | None = None,
        default_options: OptionsT | MutableMapping[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a CodexAgent with middleware and telemetry.

        Args:
            instructions: System prompt for the agent.

        Keyword Args:
            client: Optional pre-configured Codex instance. If not provided,
                a new client will be created using the other parameters.
            id: Unique identifier for the agent.
            name: Name of the agent.
            description: Description of the agent.
            context_providers: Context providers for the agent.
            middleware: Optional agent-level middleware for intercepting invocations.
            tools: Tools for the agent. Can be:
                - Strings for built-in tools (e.g., "Read", "Write", "Bash", "Glob")
                - Functions for custom tools
            default_options: Default CodexAgentOptions including system_prompt, model, etc.
            env_file_path: Path to .env file.
            env_file_encoding: Encoding of .env file.
        """
        super().__init__(
            instructions=instructions,
            client=client,
            id=id,
            name=name,
            description=description,
            context_providers=context_providers,
            middleware=middleware,
            tools=tools,
            default_options=default_options,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

    @overload  # type: ignore[override]
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        options: OptionsT | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        compaction_strategy: Any = None,
        tokenizer: Any = None,
        function_invocation_kwargs: dict[str, Any] | None = None,
        client_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload  # type: ignore[override]
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        options: OptionsT | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        compaction_strategy: Any = None,
        tokenizer: Any = None,
        function_invocation_kwargs: dict[str, Any] | None = None,
        client_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(  # pyright: ignore[reportIncompatibleMethodOverride]  # type: ignore[override]
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        options: OptionsT | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        compaction_strategy: Any = None,
        tokenizer: Any = None,
        function_invocation_kwargs: dict[str, Any] | None = None,
        client_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Run the Codex agent with middleware and telemetry enabled."""
        super_run = cast(
            "Callable[..., Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]]",
            super().run,
        )
        return super_run(
            messages=messages,
            stream=stream,
            session=session,
            middleware=middleware,
            options=options,
            tools=tools,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
            **kwargs,
        )

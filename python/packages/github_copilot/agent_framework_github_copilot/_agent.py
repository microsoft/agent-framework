# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, MutableMapping, Sequence
from typing import Any, ClassVar, Generic, Literal, TypedDict, overload

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

from agent_framework import (
    AgentMiddlewareLayer,
    AgentMiddlewareTypes,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    ContextProvider,
    HistoryProvider,
    Message,
    ResponseStream,
    SessionContext,
    normalize_messages,
)
from agent_framework._settings import load_settings
from agent_framework._tools import FunctionTool, ToolTypes
from agent_framework._types import AgentRunInputs, normalize_tools
from agent_framework.exceptions import AgentException
from agent_framework.observability import AgentTelemetryLayer

try:
    from copilot import CopilotClient, CopilotSession, SubprocessConfig
    from copilot.generated.session_events import PermissionRequest, SessionEvent, SessionEventType
    from copilot.session import MCPServerConfig, PermissionRequestResult, ProviderConfig, SystemMessageConfig
    from copilot.tools import Tool as CopilotTool
    from copilot.tools import ToolInvocation, ToolResult
except ImportError as _copilot_import_error:
    raise ImportError(
        "GitHubCopilotAgent requires the 'github-copilot-sdk' package, which is only available on Python 3.11+. "
        "Please use Python 3.11 or later."
    ) from _copilot_import_error

if sys.version_info >= (3, 13):
    from typing import TypeVar
else:
    from typing_extensions import TypeVar


DEFAULT_TIMEOUT_SECONDS: float = 60.0
"""Default timeout in seconds for Copilot requests."""

PermissionHandlerType = Callable[[PermissionRequest, dict[str, str]], PermissionRequestResult]
"""Type for permission request handlers."""


FunctionApprovalCallback = Callable[[Content], "bool | Awaitable[bool]"]
"""Callback invoked by the agent before executing a FunctionTool that requires approval.

The callback receives a ``FunctionCallContent`` describing the pending call
(``name``, ``arguments``, and a synthetic ``call_id``) and must return ``True``
to allow execution or ``False`` to deny it. Both synchronous and ``await``-able
return values are supported.

The Copilot CLI manages its own tool-calling loop, so the framework cannot
round-trip a ``FunctionApprovalRequestContent`` / ``FunctionApprovalResponseContent``
pair the way the standard chat-client pipeline does. This callback is the
agent-level enforcement point for tools declared with
``approval_mode="always_require"``: when no callback is configured the agent
denies these calls by default.

Note: this is independent of ``on_permission_request``, which gates the
Copilot SDK's *built-in* shell/file actions; ``on_function_approval`` gates
agent-framework ``FunctionTool`` calls.
"""


async def _resolve_function_approval(
    callback: FunctionApprovalCallback | None,
    func_tool: FunctionTool,
    arguments: Mapping[str, Any] | None,
) -> bool:
    """Run the agent-level approval callback for a pending tool call.

    Returns ``True`` only when ``callback`` is configured and explicitly returns
    a truthy value. A missing callback or any callback failure is treated as a
    denial so the secure-by-default policy holds even if the user code raises.
    """
    if callback is None:
        return False
    request = Content.from_function_call(
        call_id=f"af-copilot-approval::{func_tool.name}",
        name=func_tool.name,
        arguments=None if arguments is None else dict(arguments),
    )
    try:
        outcome = callback(request)
        if inspect.isawaitable(outcome):
            outcome = await outcome
    except Exception:
        logger.exception(
            "on_function_approval callback raised for tool '%s'; denying execution.",
            func_tool.name,
        )
        return False
    return bool(outcome)


logger = logging.getLogger("agent_framework.github_copilot")


def _deny_all_permissions(
    _request: PermissionRequest,
    _invocation: dict[str, str],
) -> PermissionRequestResult:
    """Default permission handler that denies all requests."""
    return PermissionRequestResult()


class GitHubCopilotSettings(TypedDict, total=False):
    """GitHub Copilot model settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'GITHUB_COPILOT_'.

    Keys:
        cli_path: Path to the Copilot CLI executable.
            Can be set via environment variable GITHUB_COPILOT_CLI_PATH.
        model: Model to use (e.g., "gpt-5", "claude-sonnet-4").
            Can be set via environment variable GITHUB_COPILOT_MODEL.
        timeout: Request timeout in seconds.
            Can be set via environment variable GITHUB_COPILOT_TIMEOUT.
        log_level: CLI log level.
            Can be set via environment variable GITHUB_COPILOT_LOG_LEVEL.
        copilot_home: Directory where the CLI stores session state, configuration,
            and other persistent data. Can be set via environment variable
            GITHUB_COPILOT_COPILOT_HOME. Defaults to ~/.copilot when not set.
            Only applicable when the SDK spawns the CLI process (ignored when
            connecting to an external server via a pre-configured client).
    """

    cli_path: str | None
    model: str | None
    timeout: float | None
    log_level: str | None
    copilot_home: str | None


class GitHubCopilotOptions(TypedDict, total=False):
    """GitHub Copilot-specific options."""

    system_message: SystemMessageConfig
    """System message configuration for the session. Use mode 'append' to add to the default
    system prompt, or 'replace' to completely override it."""

    cli_path: str
    """Path to the Copilot CLI executable. Defaults to GITHUB_COPILOT_CLI_PATH environment variable
    or 'copilot' in PATH."""

    model: str
    """Model to use (e.g., "gpt-5", "claude-sonnet-4"). Defaults to GITHUB_COPILOT_MODEL environment variable."""

    timeout: float
    """Request timeout in seconds. Defaults to GITHUB_COPILOT_TIMEOUT environment variable or 60 seconds."""

    log_level: str
    """CLI log level. Defaults to GITHUB_COPILOT_LOG_LEVEL environment variable."""

    on_permission_request: PermissionHandlerType
    """Permission request handler.
    Called when Copilot requests permission to perform an action (shell, read, write, etc.).
    Takes a PermissionRequest and context dict, returns PermissionRequestResult.
    If not provided, all permission requests will be denied by default.
    """

    mcp_servers: dict[str, MCPServerConfig]
    """MCP (Model Context Protocol) server configurations.
    A dictionary mapping server names to their configurations.
    Supports both local (stdio) and remote (HTTP/SSE) servers.
    """

    provider: ProviderConfig
    """Custom API provider configuration for BYOK (Bring Your Own Key) scenarios.
    Allows routing requests through your own OpenAI, Azure, or Anthropic endpoint
    instead of the default GitHub Copilot backend.
    """

    instruction_directories: list[str]
    """Additional directories to search for custom instruction files.
    Lets applications point the CLI at project-specific or team-shared instruction
    files beyond the default locations.
    """

    on_function_approval: FunctionApprovalCallback
    """Approval callback for ``FunctionTool`` instances declared with
    ``approval_mode="always_require"``. The callback is awaited (sync or async)
    inside the SDK tool-handler before the tool is executed; a falsy return
    value denies the call. If omitted, calls to such tools are denied with an
    explanatory message returned to the model. This is independent of
    ``on_permission_request``, which gates the Copilot SDK's built-in actions."""


OptionsT = TypeVar(
    "OptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="GitHubCopilotOptions",
    covariant=True,
)


class RawGitHubCopilotAgent(BaseAgent, Generic[OptionsT]):
    """A GitHub Copilot Agent without telemetry layers.

    This is the core GitHub Copilot agent implementation without OpenTelemetry instrumentation.
    For most use cases, prefer :class:`GitHubCopilotAgent` which includes telemetry support.

    This agent wraps the GitHub Copilot SDK to provide Copilot agentic capabilities
    within the Agent Framework. It supports both streaming and non-streaming responses,
    custom tools, and session management.

    The agent can be used as an async context manager to ensure proper cleanup:

    Examples:
        Basic usage:

        .. code-block:: python

            async with RawGitHubCopilotAgent() as agent:
                response = await agent.run("Hello, world!")
                print(response)

        With explicitly typed options:

        .. code-block:: python

            from agent_framework_github_copilot import RawGitHubCopilotAgent, GitHubCopilotOptions

            agent: RawGitHubCopilotAgent[GitHubCopilotOptions] = RawGitHubCopilotAgent(
                default_options={"model": "claude-sonnet-4", "timeout": 120}
            )
    """

    AGENT_PROVIDER_NAME: ClassVar[str] = "github.copilot"

    def __init__(
        self,
        instructions: str | None = None,
        *,
        client: CopilotClient | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsT | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the GitHub Copilot Agent.

        Args:
            instructions: System message for the agent.

        Keyword Args:
            client: Optional pre-configured CopilotClient instance. If not provided,
                a new client will be created using the other parameters.
            id: ID of the RawGitHubCopilotAgent.
            name: Name of the RawGitHubCopilotAgent.
            description: Description of the RawGitHubCopilotAgent.
            context_providers: Context Providers, to be used by the agent.
            middleware: Agent middleware used by the agent.
            tools: Tools to use for the agent. Can be functions
                or tool definition dicts. These are converted to Copilot SDK tools internally.
            default_options: Default options for the agent. Can include cli_path, model,
                timeout, log_level, etc.
            env_file_path: Optional path to .env file for loading configuration.
            env_file_encoding: Encoding of the .env file, defaults to 'utf-8'.

        Raises:
            ValueError: If required configuration is missing or invalid.
        """
        super().__init__(
            id=id,
            name=name,
            description=description,
            context_providers=context_providers,
            middleware=list(middleware) if middleware else None,
        )

        self._client = client
        self._owns_client = client is None

        # Parse options
        opts: dict[str, Any] = dict(default_options) if default_options else {}

        # Handle instructions - direct parameter takes precedence over default_options.system_message
        self._prepare_system_message(instructions, opts)

        cli_path = opts.pop("cli_path", None)
        model = opts.pop("model", None)
        timeout = opts.pop("timeout", None)
        log_level = opts.pop("log_level", None)
        on_permission_request: PermissionHandlerType | None = opts.pop("on_permission_request", None)
        mcp_servers: dict[str, MCPServerConfig] | None = opts.pop("mcp_servers", None)
        provider: ProviderConfig | None = opts.pop("provider", None)
        instruction_directories: list[str] | None = opts.pop("instruction_directories", None)
        on_function_approval: FunctionApprovalCallback | None = opts.pop("on_function_approval", None)
        copilot_home = opts.pop("copilot_home", None)

        self._settings = load_settings(
            GitHubCopilotSettings,
            env_prefix="GITHUB_COPILOT_",
            cli_path=cli_path,
            model=model,
            timeout=timeout,
            log_level=log_level,
            copilot_home=copilot_home,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self._tools = normalize_tools(tools)
        self._permission_handler = on_permission_request
        self._function_approval_handler: FunctionApprovalCallback | None = on_function_approval
        self._mcp_servers = mcp_servers
        self._provider = provider
        self._instruction_directories = instruction_directories
        self._default_options = opts
        self._started = False

    async def __aenter__(self) -> Self:
        """Start the agent when entering async context."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the agent when exiting async context."""
        await self.stop()

    async def start(self) -> None:
        """Start the Copilot client.

        This method initializes the Copilot client and establishes a connection
        to the Copilot CLI server. It is called automatically when using the
        agent as an async context manager.

        Raises:
            AgentException: If the client fails to start.
        """
        if self._started:
            return

        if self._client is None:
            cli_path = self._settings.get("cli_path") or None
            log_level = self._settings.get("log_level") or None
            copilot_home = self._settings.get("copilot_home") or None

            subprocess_kwargs: dict[str, Any] = {"cli_path": cli_path}
            if log_level:
                subprocess_kwargs["log_level"] = log_level
            if copilot_home:
                subprocess_kwargs["copilot_home"] = copilot_home
            self._client = CopilotClient(SubprocessConfig(**subprocess_kwargs))

        try:
            await self._client.start()
            self._started = True
        except Exception as ex:
            raise AgentException(f"Failed to start GitHub Copilot client: {ex}") from ex

    async def stop(self) -> None:
        """Stop the Copilot client and clean up resources.

        Stops the Copilot client if owned by this agent. The client handles
        session cleanup internally. Called automatically when using the agent
        as an async context manager.
        """
        if self._client and self._owns_client:
            with contextlib.suppress(Exception):
                await self._client.stop()

        self._started = False

    @property
    def default_options(self) -> dict[str, Any]:
        """Expose default options including model from settings.

        Returns a merged dict of ``_default_options`` with the resolved ``model``
        from settings injected under the ``model`` key. This is read by
        :class:`AgentTelemetryLayer` to include the model name in span attributes.
        """
        opts = dict(self._default_options)
        model = self._settings.get("model")
        if model:
            opts["model"] = model
        return opts

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = False,
        session: AgentSession | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        options: OptionsT | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        options: OptionsT | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        options: OptionsT | None = None,
        **kwargs: Any,  # type: ignore[override]
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single AgentResponse object when stream=False. When stream=True,
        it returns a ResponseStream that yields AgentResponseUpdate objects.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            stream: Whether to stream the response. Defaults to False.
            session: The conversation session associated with the message(s).
            middleware: Not used by this agent directly. Accepted for interface
                compatibility; pass middleware via :class:`GitHubCopilotAgent` which
                forwards it through :class:`AgentTelemetryLayer`.
            options: Runtime options (model, timeout, etc.).
            kwargs: Additional keyword arguments for compatibility with the shared agent
                interface (e.g. compaction_strategy, tokenizer). Not used by this agent.

        Returns:
            When stream=False: An Awaitable[AgentResponse].
            When stream=True: A ResponseStream of AgentResponseUpdate items.

        Raises:
            AgentException: If the request fails.
        """
        if middleware:
            logger.warning(
                "Per-run middleware is not supported by RawGitHubCopilotAgent: the GitHub Copilot SDK "
                "handles tool execution internally, so chat/function middleware cannot be injected into "
                "the tool call path. Use agent-level middleware via the GitHubCopilotAgent constructor instead."
            )
        if stream:
            ctx_holder: dict[str, Any] = {}

            async def _after_run_hook(response: AgentResponse) -> None:
                session_context = ctx_holder.get("session_context")
                sess = ctx_holder.get("session")
                if session_context is not None and sess is not None:
                    session_context._response = response
                    try:
                        await self._run_after_providers(session=sess, context=session_context)
                    except Exception:
                        logger.exception("Error running after_run providers in streaming result hook")

            def _finalize(updates: Sequence[AgentResponseUpdate]) -> AgentResponse:
                return AgentResponse.from_updates(updates)

            return ResponseStream(
                self._stream_updates(messages=messages, session=session, options=options, _ctx_holder=ctx_holder),
                finalizer=_finalize,
                result_hooks=[_after_run_hook],
            )
        return self._run_impl(messages=messages, session=session, options=options)

    async def _run_impl(
        self,
        messages: AgentRunInputs | None = None,
        *,
        session: AgentSession | None = None,
        options: OptionsT | None = None,
    ) -> AgentResponse:
        """Non-streaming implementation of run."""
        if not self._started:
            await self.start()

        if not session:
            session = self.create_session()

        opts: dict[str, Any] = dict(options) if options else {}
        if "on_function_approval" in opts:
            raise ValueError(
                "on_function_approval is a security-sensitive option and must be set "
                "via default_options at agent construction time. It cannot be overridden "
                "per run."
            )
        timeout = opts.get("timeout") or self._settings.get("timeout") or DEFAULT_TIMEOUT_SECONDS

        input_messages = normalize_messages(messages)

        session_context = await self._run_before_providers(session=session, input_messages=input_messages, options=opts)

        # NOTE: session is created after providers run so that future provider-contributed
        # tools/config could be folded into runtime_options before session creation.
        copilot_session = await self._get_or_create_session(session, streaming=False, runtime_options=opts)

        # Build the prompt from the full set of messages in the session context,
        # so that any context/history provider-injected messages are included.
        context_messages = session_context.get_messages(include_input=True)
        prompt = "\n".join([message.text for message in context_messages])
        if session_context.instructions:
            prompt = "\n".join(session_context.instructions) + "\n" + prompt

        try:
            response_event = await copilot_session.send_and_wait(prompt, timeout=timeout)
        except Exception as ex:
            raise AgentException(f"GitHub Copilot request failed: {ex}") from ex

        response_messages: list[Message] = []
        response_id: str | None = None

        # send_and_wait returns only the final ASSISTANT_MESSAGE event;
        # other events (deltas, tool calls) are handled internally by the SDK.
        if response_event and response_event.type == SessionEventType.ASSISTANT_MESSAGE:
            data: Any = response_event.data
            message_id = data.message_id

            if data.content:
                response_messages.append(
                    Message(
                        role="assistant",
                        contents=[Content.from_text(data.content)],
                        message_id=message_id,
                        raw_representation=response_event,
                    )
                )
            response_id = message_id

        response = AgentResponse(messages=response_messages, response_id=response_id)
        session_context._response = response  # type: ignore[assignment]
        await self._run_after_providers(session=session, context=session_context)
        return response

    async def _stream_updates(
        self,
        messages: AgentRunInputs | None = None,
        *,
        session: AgentSession | None = None,
        options: OptionsT | None = None,
        _ctx_holder: dict[str, Any] | None = None,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Internal method to stream updates from GitHub Copilot.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            session: The conversation session associated with the message(s).
            options: Runtime options (model, timeout, etc.).
            _ctx_holder: Internal dict populated with session_context and session
                so that the caller (via a ResponseStream result_hook) can run
                after_run providers without duplicating the updates buffer.

        Yields:
            AgentResponseUpdate items.

        Raises:
            AgentException: If the request fails.
        """
        if not self._started:
            await self.start()

        if not session:
            session = self.create_session()

        opts: dict[str, Any] = dict(options) if options else {}
        if "on_function_approval" in opts:
            raise ValueError(
                "on_function_approval is a security-sensitive option and must be set "
                "via default_options at agent construction time. It cannot be overridden "
                "per run."
            )

        input_messages = normalize_messages(messages)

        session_context = await self._run_before_providers(session=session, input_messages=input_messages, options=opts)

        # NOTE: session is created after providers run so that future provider-contributed
        # tools/config could be folded into runtime_options before session creation.
        copilot_session = await self._get_or_create_session(session, streaming=True, runtime_options=opts)

        if _ctx_holder is not None:
            _ctx_holder["session_context"] = session_context
            _ctx_holder["session"] = session

        # Build the prompt from the full session context so provider-injected messages are included.
        context_messages = session_context.get_messages(include_input=True)
        prompt = "\n".join([message.text for message in context_messages])
        if session_context.instructions:
            prompt = "\n".join(session_context.instructions) + "\n" + prompt

        queue: asyncio.Queue[AgentResponseUpdate | Exception | None] = asyncio.Queue()

        def event_handler(event: SessionEvent) -> None:
            if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                data: Any = event.data
                if data.delta_content:
                    update = AgentResponseUpdate(
                        role="assistant",
                        contents=[Content.from_text(data.delta_content)],
                        response_id=data.message_id,
                        message_id=data.message_id,
                        raw_representation=event,
                    )
                    queue.put_nowait(update)
            elif event.type == SessionEventType.TOOL_EXECUTION_START:
                tool_call_id = getattr(event.data, "tool_call_id", None) or ""
                tool_name = getattr(event.data, "tool_name", None) or ""
                arguments = getattr(event.data, "arguments", None)
                fc = Content.from_function_call(
                    call_id=tool_call_id,
                    name=tool_name,
                    arguments=arguments,
                    raw_representation=event.data,
                )
                update = AgentResponseUpdate(
                    role="assistant",
                    contents=[fc],
                    raw_representation=event,
                )
                queue.put_nowait(update)
            elif event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
                tool_call_id = getattr(event.data, "tool_call_id", None) or ""
                result_obj = getattr(event.data, "result", None)
                result_text = getattr(result_obj, "content", "") if result_obj else ""
                success = getattr(event.data, "success", None)
                error_val = getattr(event.data, "error", None)
                exception = None
                if success is False and error_val is not None:
                    exception = error_val.message if hasattr(error_val, "message") else str(error_val)
                fr = Content.from_function_result(
                    call_id=tool_call_id,
                    result=result_text or "",
                    exception=exception,
                    raw_representation=event.data,
                )
                update = AgentResponseUpdate(
                    role="tool",
                    contents=[fr],
                    raw_representation=event,
                )
                queue.put_nowait(update)
            elif event.type == SessionEventType.SESSION_IDLE:
                queue.put_nowait(None)
            elif event.type == SessionEventType.SESSION_ERROR:
                error_data: Any = event.data
                error_msg = error_data.message or "Unknown error"
                queue.put_nowait(AgentException(f"GitHub Copilot session error: {error_msg}"))

        unsubscribe = copilot_session.on(event_handler)

        try:
            await copilot_session.send(prompt)

            while (item := await queue.get()) is not None:
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            unsubscribe()

    async def _run_before_providers(
        self,
        *,
        session: AgentSession,
        input_messages: list[Message],
        options: dict[str, Any],
    ) -> SessionContext:
        """Run before_run on all context providers and return the session context.

        Creates a SessionContext and invokes ``before_run`` on each provider in
        forward order.  ``HistoryProvider`` instances with
        ``load_messages=False`` are skipped.

        Keyword Args:
            session: The conversation session.
            input_messages: The normalized input messages.
            options: Runtime options dict.

        Returns:
            The SessionContext with provider context populated.
        """
        session_context = SessionContext(
            session_id=session.session_id,
            service_session_id=session.service_session_id,
            input_messages=input_messages,
            options=options,
        )

        for provider in self.context_providers:
            if isinstance(provider, HistoryProvider) and not provider.load_messages:
                continue
            await provider.before_run(
                agent=self,  # type: ignore[arg-type]
                session=session,
                context=session_context,
                state=session.state.setdefault(provider.source_id, {}),
            )

        return session_context

    @staticmethod
    def _prepare_system_message(
        instructions: str | None,
        opts: dict[str, Any],
    ) -> None:
        """Prepare system message configuration in opts.

        If instructions is provided, it takes precedence for content.
        If system_message is also provided, its mode is preserved.
        Modifies opts in place.

        Args:
            instructions: Direct instructions parameter for content.
            opts: Options dictionary to modify.
        """
        opts_system_message = opts.pop("system_message", None)
        if instructions is not None:
            # Use instructions for content, but preserve mode from system_message if provided
            mode = opts_system_message.get("mode", "append") if opts_system_message else "append"
            opts["system_message"] = {"mode": mode, "content": instructions}
        elif opts_system_message is not None:
            opts["system_message"] = opts_system_message

    def _prepare_tools(
        self,
        tools: Sequence[ToolTypes | CopilotTool],
    ) -> list[CopilotTool]:
        """Convert Agent Framework tools to Copilot SDK tools.

        Args:
            tools: List of Agent Framework tools.

        Returns:
            List of Copilot SDK tools.
        """
        copilot_tools: list[CopilotTool] = []

        for tool in tools:
            if isinstance(tool, CopilotTool):
                copilot_tools.append(tool)
            elif isinstance(tool, FunctionTool):
                copilot_tools.append(self._tool_to_copilot_tool(tool))  # type: ignore
            elif isinstance(tool, MutableMapping):
                copilot_tools.append(tool)  # type: ignore[arg-type]
            # Note: Other tool types (e.g., dict-based hosted tools) are skipped

        return copilot_tools

    def _tool_to_copilot_tool(self, ai_func: FunctionTool) -> CopilotTool:
        """Convert an FunctionTool to a Copilot SDK tool."""
        approval_handler = self._function_approval_handler
        requires_approval = ai_func.approval_mode == "always_require"

        async def handler(invocation: ToolInvocation) -> ToolResult:
            args: dict[str, Any] = invocation.arguments or {}
            try:
                if requires_approval and not await _resolve_function_approval(approval_handler, ai_func, args):
                    deny_text = (
                        f"Tool '{ai_func.name}' requires human approval "
                        "(approval_mode='always_require') and the request was denied."
                        if approval_handler is not None
                        else (
                            f"Tool '{ai_func.name}' requires human approval "
                            "(approval_mode='always_require') but no on_function_approval "
                            "callback is configured on the agent; the request was denied."
                        )
                    )
                    logger.info(
                        "Denying execution of tool '%s' (approval_mode='always_require', %s)",
                        ai_func.name,
                        "callback denied" if approval_handler is not None else "no callback configured",
                    )
                    return ToolResult(
                        text_result_for_llm=deny_text,
                        result_type="failure",
                        error="approval_denied",
                    )
                if ai_func.input_model:
                    args_instance = ai_func.input_model(**args)
                    result = await ai_func.invoke(arguments=args_instance)
                else:
                    result = await ai_func.invoke(arguments=args)
                rich = [c for c in result if c.type in ("data", "uri")]
                if rich:
                    logger.warning(
                        "GitHub Copilot does not support rich tool content; "
                        f"dropping {len(rich)} non-text item(s) from '{ai_func.name}'."
                    )
                text = "\n".join(c.text for c in result if c.type == "text" and c.text)
                return ToolResult(
                    text_result_for_llm=text or str(result),
                    result_type="success",
                )
            except Exception as e:
                return ToolResult(
                    text_result_for_llm=f"Error: {e}",
                    result_type="failure",
                    error=str(e),
                )

        return CopilotTool(
            name=ai_func.name,
            description=ai_func.description,
            handler=handler,
            parameters=ai_func.parameters(),
        )

    async def _get_or_create_session(
        self,
        agent_session: AgentSession,
        streaming: bool = False,
        runtime_options: dict[str, Any] | None = None,
    ) -> CopilotSession:
        """Get an existing session or create a new one for the session.

        Args:
            agent_session: The conversation session.
            streaming: Whether to enable streaming for the session.
            runtime_options: Runtime options from run that take precedence.

        Returns:
            A CopilotSession instance.

        Raises:
            AgentException: If the session cannot be created.
        """
        if not self._client:
            raise RuntimeError("GitHub Copilot client not initialized. Call start() first.")

        try:
            if agent_session.service_session_id:
                return await self._resume_session(agent_session.service_session_id, streaming, runtime_options)

            session = await self._create_session(streaming, runtime_options)
            agent_session.service_session_id = session.session_id
            return session
        except Exception as ex:
            raise AgentException(f"Failed to create GitHub Copilot session: {ex}") from ex

    async def _create_session(
        self,
        streaming: bool,
        runtime_options: dict[str, Any] | None = None,
    ) -> CopilotSession:
        """Create a new Copilot session.

        Args:
            streaming: Whether to enable streaming for the session.
            runtime_options: Runtime options that take precedence over default_options.
        """
        if not self._client:
            raise RuntimeError("GitHub Copilot client not initialized. Call start() first.")

        opts = runtime_options or {}
        model = opts.get("model") or self._settings.get("model") or None
        system_message = opts.get("system_message") or self._default_options.get("system_message") or None
        permission_handler: PermissionHandlerType = (
            opts.get("on_permission_request") or self._permission_handler or _deny_all_permissions
        )
        mcp_servers = opts.get("mcp_servers") or self._mcp_servers or None
        provider = opts.get("provider") or self._provider or None
        instruction_directories = opts.get("instruction_directories", self._instruction_directories)
        tools = self._prepare_tools(self._tools) if self._tools else None

        return await self._client.create_session(
            on_permission_request=permission_handler,
            streaming=streaming,
            model=model or None,
            system_message=system_message or None,
            tools=tools or None,
            mcp_servers=mcp_servers or None,
            provider=provider or None,
            instruction_directories=instruction_directories,
        )

    async def _resume_session(
        self,
        session_id: str,
        streaming: bool,
        runtime_options: dict[str, Any] | None = None,
    ) -> CopilotSession:
        """Resume an existing Copilot session by ID.

        Args:
            session_id: The session ID to resume.
            streaming: Whether to enable streaming for the session.
            runtime_options: Runtime options that take precedence over default_options.
        """
        if not self._client:
            raise RuntimeError("GitHub Copilot client not initialized. Call start() first.")

        opts = runtime_options or {}
        model = opts.get("model") or self._settings.get("model") or None
        system_message = opts.get("system_message") or self._default_options.get("system_message") or None
        permission_handler: PermissionHandlerType = (
            opts.get("on_permission_request") or self._permission_handler or _deny_all_permissions
        )
        mcp_servers = opts.get("mcp_servers") or self._mcp_servers or None
        provider = opts.get("provider") or self._provider or None
        instruction_directories = opts.get("instruction_directories", self._instruction_directories)
        tools = self._prepare_tools(self._tools) if self._tools else None

        return await self._client.resume_session(
            session_id,
            on_permission_request=permission_handler,
            streaming=streaming,
            model=model or None,
            system_message=system_message or None,
            tools=tools or None,
            mcp_servers=mcp_servers or None,
            provider=provider or None,
            instruction_directories=instruction_directories,
        )


class GitHubCopilotAgent(  # type: ignore[misc]
    AgentMiddlewareLayer,
    AgentTelemetryLayer,
    RawGitHubCopilotAgent[OptionsT],
    Generic[OptionsT],
):
    """A GitHub Copilot Agent with full middleware and telemetry support.

    This is the recommended agent class for most use cases. It includes
    middleware support and OpenTelemetry-based telemetry for observability,
    with middleware running outside the telemetry span so middleware execution
    time is not captured in traces. For a minimal implementation without these
    layers, use :class:`RawGitHubCopilotAgent`.

    Examples:
        Basic usage:

        .. code-block:: python

            async with GitHubCopilotAgent() as agent:
                response = await agent.run("Hello, world!")
                print(response)

        With explicitly typed options:

        .. code-block:: python

            from agent_framework_github_copilot import GitHubCopilotAgent, GitHubCopilotOptions

            agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
                default_options={"model": "claude-sonnet-4-5", "timeout": 120}
            )

        With observability:

        .. code-block:: python

            from agent_framework.observability import configure_otel_providers

            configure_otel_providers()
            async with GitHubCopilotAgent() as agent:
                response = await agent.run("Hello, world!")
    """

    def __init__(
        self,
        instructions: str | None = None,
        *,
        client: CopilotClient | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsT | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a GitHub Copilot Agent with full middleware and telemetry.

        Args:
            instructions: System message for the agent.

        Keyword Args:
            client: Optional pre-configured CopilotClient instance. If not provided,
                a new client will be created using the other parameters.
            id: ID of the agent.
            name: Name of the agent.
            description: Description of the agent.
            context_providers: Context providers to be used by the agent.
            middleware: Agent middleware used by the agent.
            tools: Tools to use for the agent. Can be functions or tool definition dicts.
                These are converted to Copilot SDK tools internally.
            default_options: Default options for the agent. Can include cli_path, model,
                timeout, log_level, etc.
            env_file_path: Optional path to .env file for loading configuration.
            env_file_encoding: Encoding of the .env file, defaults to 'utf-8'.
        """
        super().__init__(
            instructions,
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

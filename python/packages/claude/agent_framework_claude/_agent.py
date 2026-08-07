# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, cast, overload

from agent_framework import (
    AgentMiddlewareTypes,
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    Content,
    ContextProvider,
    FunctionTool,
    Message,
    ResponseStream,
    ToolTypes,
    UsageDetails,
    load_settings,
    normalize_messages,
    normalize_tools,
)
from agent_framework._telemetry import mark_feature_used
from agent_framework.exceptions import AgentException, AgentInvalidRequestException
from agent_framework.observability import AgentTelemetryLayer
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    SdkMcpTool,
    create_sdk_mcp_server,
)
from claude_agent_sdk import (
    ClaudeAgentOptions as SDKOptions,
)
from claude_agent_sdk.types import StreamEvent, TextBlock

from ._feature_usage import FeatureIndex

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover

if TYPE_CHECKING:
    from claude_agent_sdk import (
        AgentDefinition,
        CanUseTool,
        HookMatcher,
        McpServerConfig,
        PermissionMode,
        SandboxSettings,
        SdkBeta,
        SdkPluginConfig,
        SettingSource,
    )
    from claude_agent_sdk.types import ThinkingConfig


logger = logging.getLogger("agent_framework.claude")

FINISH_REASON_MAP: dict[str, str] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "refusal": "content_filter",
}


# Name of the in-process MCP server that hosts Agent Framework tools.
# FunctionTool instances are converted to SDK MCP tools and served
# through this server, as Claude Code CLI only supports tools via MCP.
TOOLS_MCP_SERVER_NAME = "_agent_framework_tools"


FunctionApprovalCallback = Callable[[Content], "bool | Awaitable[bool]"]
"""Callback invoked by the agent before executing a FunctionTool that requires approval.

The callback receives a ``FunctionCallContent`` describing the pending call
(``name``, ``arguments``, and a synthetic ``call_id``) and must return ``True``
to allow execution or ``False`` to deny it. Both synchronous and ``await``-able
return values are supported.

The Claude Agent SDK manages its own tool-calling loop, so the framework cannot
round-trip a ``FunctionApprovalRequestContent`` / ``FunctionApprovalResponseContent``
pair the way the standard chat-client pipeline does. This callback is the
agent-level enforcement point for tools declared with
``approval_mode="always_require"``: when no callback is configured the agent
denies these calls by default.
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
        call_id=f"af-claude-approval::{func_tool.name}",
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


class ClaudeAgentSettings(TypedDict, total=False):
    """Claude Agent settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'CLAUDE_AGENT_'.

    Keys:
        cli_path: The path to Claude CLI executable.
        model: The model to use (sonnet, opus, haiku).
        cwd: The working directory for Claude CLI.
        permission_mode: Permission mode (default, acceptEdits, plan, bypassPermissions).
        max_turns: Maximum number of conversation turns.
        max_budget_usd: Maximum budget in USD.
    """

    cli_path: str | None
    model: str | None
    cwd: str | None
    permission_mode: str | None
    max_turns: int | None
    max_budget_usd: float | None


class ClaudeAgentOptions(TypedDict, total=False):
    """Claude Agent-specific options."""

    system_prompt: str
    """System prompt for the agent."""

    cli_path: str | Path
    """Path to Claude CLI executable. Default: auto-detected."""

    cwd: str | Path
    """Working directory for Claude CLI. Default: current working directory."""

    env: dict[str, str]
    """Environment variables to pass to CLI."""

    settings: str
    """Path to Claude settings file."""

    model: str
    """Model to use ("sonnet", "opus", "haiku"). Default: "sonnet"."""

    fallback_model: str
    """Fallback model if primary fails."""

    allowed_tools: list[str]
    """Allowlist of tools. If set, Claude can ONLY use tools in this list."""

    disallowed_tools: list[str]
    """Blocklist of tools. Claude cannot use these tools."""

    mcp_servers: dict[str, McpServerConfig]
    """MCP server configurations for external tools."""

    permission_mode: PermissionMode
    """Permission handling mode ("default", "acceptEdits", "plan", "bypassPermissions")."""

    can_use_tool: CanUseTool
    """Permission callback for tool use."""

    max_turns: int
    """Maximum conversation turns."""

    max_budget_usd: float
    """Budget limit in USD."""

    hooks: dict[str, list[HookMatcher]]
    """Pre/post tool hooks."""

    add_dirs: list[str | Path]
    """Additional directories to add to context."""

    sandbox: SandboxSettings
    """Sandbox configuration for bash isolation."""

    agents: dict[str, AgentDefinition]
    """Custom agent definitions."""

    output_format: dict[str, Any]
    """Structured output format (JSON schema)."""

    enable_file_checkpointing: bool
    """Enable file checkpointing for rewind."""

    betas: list[SdkBeta]
    """Beta features to enable."""

    plugins: list[SdkPluginConfig]
    """Plugin configurations for custom commands and capabilities."""

    setting_sources: list[SettingSource]
    """Which Claude settings files to load ("user", "project", "local")."""

    thinking: ThinkingConfig
    """Extended thinking configuration (adaptive, enabled, or disabled)."""

    effort: Literal["low", "medium", "high", "xhigh", "max"]
    """Effort level for thinking depth."""

    skills: list[str] | Literal["all"]
    """Skills to enable for the main session. Use ``"all"`` for every discovered skill,
    a list of named skills, or ``[]`` to suppress all skills."""

    session_id: str
    """Use a specific session ID (must be a valid UUID) instead of auto-generated."""

    task_budget: dict[str, int]
    """API-side task budget in tokens for pacing tool use."""

    include_hook_events: bool
    """When True, hook lifecycle events are emitted in the message stream."""

    strict_mcp_config: bool
    """When True, only use MCP servers passed via ``mcp_servers``, ignoring all others."""

    continue_conversation: bool
    """Continue the most recent conversation instead of starting a new one."""

    fork_session: bool
    """When True, resumed sessions fork to a new session ID."""

    on_function_approval: FunctionApprovalCallback
    """Approval callback for ``FunctionTool`` instances declared with
    ``approval_mode="always_require"``. The callback is awaited (sync or async)
    inside the SDK tool-handler before the tool is executed; a falsy return
    value denies the call. If omitted, calls to such tools are denied with an
    explanatory message returned to the model."""


OptionsT = TypeVar(
    "OptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ClaudeAgentOptions",
    covariant=True,
)


class RawClaudeAgent(BaseAgent, Generic[OptionsT]):
    """Claude Agent using Claude Code CLI without telemetry layers.

    This is the core Claude agent implementation without OpenTelemetry instrumentation.
    For most use cases, prefer :class:`ClaudeAgent` which includes telemetry support.

    Wraps the Claude Agent SDK to provide agentic capabilities including
    tool use, session management, and streaming responses.

    This agent communicates with Claude through the Claude Code CLI,
    enabling access to Claude's full agentic capabilities like file
    editing, code execution, and tool use.

    The agent can be used as an async context manager to ensure proper cleanup:

    Examples:
        Basic usage with context manager:

        .. code-block:: python

            from agent_framework.anthropic import RawClaudeAgent

            async with RawClaudeAgent(
                instructions="You are a helpful assistant.",
            ) as agent:
                response = await agent.run("Hello!")
                print(response.text)
    """

    AGENT_PROVIDER_NAME: ClassVar[str] = "anthropic.claude"

    def __init__(
        self,
        instructions: str | None = None,
        *,
        client: ClaudeSDKClient | None = None,
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
        """Initialize a RawClaudeAgent instance.

        Args:
            instructions: System prompt for the agent.

        Keyword Args:
            client: Optional pre-configured ClaudeSDKClient instance. If not provided,
                a new client will be created using the other parameters.
            id: Unique identifier for the agent.
            name: Name of the agent.
            description: Description of the agent.
            context_providers: Context providers for the agent.
            middleware: List of middleware.
            tools: Tools for the agent. Can be:
                - Strings for built-in tools (e.g., "Read", "Write", "Bash", "Glob")
                - Functions for custom tools
            default_options: Default ClaudeAgentOptions including system_prompt, model, etc.
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

        cli_path = opts.pop("cli_path", None)
        model = opts.pop("model", None)
        cwd = opts.pop("cwd", None)
        permission_mode = opts.pop("permission_mode", None)
        max_turns = opts.pop("max_turns", None)
        max_budget_usd = opts.pop("max_budget_usd", None)
        self._mcp_servers: dict[str, Any] = opts.pop("mcp_servers", None) or {}
        self._function_approval_handler: FunctionApprovalCallback | None = opts.pop("on_function_approval", None)

        # Load settings from environment and options
        self._settings = load_settings(
            ClaudeAgentSettings,
            env_prefix="CLAUDE_AGENT_",
            cli_path=cli_path,
            model=model,
            cwd=cwd,
            permission_mode=permission_mode,
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        # Separate built-in tools (strings) from custom tools (callables/FunctionTool)
        self._builtin_tools: list[str] = []
        self._custom_tools: list[ToolTypes] = []
        self._normalize_tools(tools)

        self._default_options = opts
        self._started = False
        # An injected client is a single Claude conversation; bind it to the first
        # session that uses it and serialize access so distinct sessions cannot
        # share it and concurrent runs cannot race its connection or interleave.
        self._injected_session: AgentSession | None = None
        self._client_lock = asyncio.Lock()

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

        non_builtin_tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] = []
        if not isinstance(tools, list):
            tools = [tools]
        for tool in tools:  # type: ignore[reportUnknownVariableType]
            if isinstance(tool, str):
                self._builtin_tools.append(tool)
            else:
                non_builtin_tools.append(tool)  # type: ignore[union-attr, reportUnknownArgumentType]
        if not non_builtin_tools:
            return
        self._custom_tools.extend(normalize_tools(non_builtin_tools))

    async def __aenter__(self) -> RawClaudeAgent[OptionsT]:
        """Start the agent when entering async context."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the agent when exiting async context."""
        await self.stop()

    async def start(self) -> None:
        """Start the Claude SDK client.

        Owned clients are created per run so that distinct sessions stay isolated;
        this only needs to establish a connection for a pre-configured client that
        was injected at construction. It is called automatically when using the
        agent as an async context manager.

        Raises:
            AgentException: If the client fails to start.
        """
        if self._client is not None and not self._owns_client:
            async with self._client_lock:
                await self._connect_injected_client()

    async def stop(self) -> None:
        """Stop the Claude SDK client and clean up resources.

        Per-run owned clients are disconnected at the end of each run, so this
        only disconnects a long-lived client the agent still owns. A client that
        was injected at construction is owned by the caller and left untouched.
        Called automatically when using the agent as an async context manager.
        """
        if self._client is not None and self._owns_client:
            with contextlib.suppress(Exception):
                await self._client.disconnect()

        self._started = False

    async def _connect_injected_client(self) -> None:
        """Connect the injected client once. Caller must hold ``_client_lock``.

        Raises:
            AgentException: If the client fails to connect.
        """
        if self._client is None or self._started:
            return
        try:
            await self._client.connect()
            self._started = True
        except Exception as ex:
            raise AgentException(f"Failed to start Claude SDK client: {ex}") from ex

    async def _acquire_client(self, session: AgentSession) -> tuple[ClaudeSDKClient, bool]:
        """Acquire a Claude SDK client for a single run.

        A ``ClaudeSDKClient`` is stateful and represents exactly one provider
        conversation, so obtaining it is an isolation decision, not just a
        connection optimization. When a client was injected at construction, that
        single conversation is bound to the first session that uses it and reused
        only for that same conversation; a session that targets a different
        conversation is rejected because one injected conversation cannot be
        shared without leaking context. Otherwise a fresh client scoped to this
        run is created and connected, resuming the session's provider conversation
        when it already carries one. Binding the client to the run rather than to
        shared agent state keeps distinct sessions isolated even when they run
        concurrently against the same agent instance.

        Args:
            session: The active session for this run.

        Returns:
            A tuple of the client and whether the caller owns it and must
            disconnect it when the run completes. An injected client is never
            owned by the caller of this method.

        Raises:
            AgentException: If the client fails to connect.
            AgentInvalidRequestException: If an injected client is reused with a
                session that targets a different conversation than the one it is
                bound to.
        """
        if self._client is not None and not self._owns_client:
            # Injected client: a single caller-managed conversation. Bind it to
            # the first session and refuse to let a different conversation reuse it.
            if self._injected_session is None:
                self._injected_session = session
            elif not self._injected_session_matches(session):
                raise AgentInvalidRequestException(
                    "An injected ClaudeSDKClient represents a single Claude conversation and is "
                    "bound to one session; it cannot be reused with a session that targets a "
                    "different conversation. Omit `client=` so each run gets its own isolated "
                    "client, or use a separate ClaudeAgent per session."
                )
            await self._connect_injected_client()
            return self._client, False

        opts = self._prepare_client_options(resume_session_id=self._get_chat_conversation_id(session))
        client = ClaudeSDKClient(options=opts)
        try:
            await client.connect()
        except Exception as ex:
            raise AgentException(f"Failed to start Claude SDK client: {ex}") from ex
        return client, True

    def _injected_session_matches(self, session: AgentSession) -> bool:
        """Whether ``session`` targets the conversation the injected client is bound to.

        The isolation boundary for an injected client is the Claude conversation,
        identified by ``service_session_id`` -- not the framework-local
        ``session_id``. A reconstructed session (for example one from
        ``get_session(service_session_id=...)``) carries a fresh ``session_id`` but
        the same provider conversation id, so it legitimately continues the bound
        conversation. When the incoming session has no provider id yet, fall back
        to the local ``session_id`` so two distinct unbound sessions cannot share
        the client.

        Args:
            session: The session requesting the injected client.

        Returns:
            True if the session may reuse the injected client, False otherwise.
        """
        bound = self._injected_session
        if bound is None or bound is session:
            return True
        if session.service_session_id is not None:
            return bound.service_session_id == session.service_session_id
        return bound.session_id == session.session_id

    def _prepare_client_options(self, resume_session_id: str | None = None) -> SDKOptions:
        """Prepare SDK options for client initialization.

        Args:
            resume_session_id: Optional session ID to resume.

        Returns:
            SDKOptions instance configured for the client.
        """
        opts: dict[str, Any] = {}

        # Set resume option if provided
        if resume_session_id:
            opts["resume"] = resume_session_id

        # Apply settings from environment
        if cli_path := self._settings.get("cli_path"):
            opts["cli_path"] = cli_path
        if model := self._settings.get("model"):
            opts["model"] = model
        if cwd := self._settings.get("cwd"):
            opts["cwd"] = cwd
        if permission_mode := self._settings.get("permission_mode"):
            opts["permission_mode"] = permission_mode
        if max_turns := self._settings.get("max_turns"):
            opts["max_turns"] = max_turns
        if max_budget_usd := self._settings.get("max_budget_usd"):
            opts["max_budget_usd"] = max_budget_usd

        # Apply default options
        for key, value in self._default_options.items():
            if value is not None:
                opts[key] = value

        # Add built-in tools (strings like "Read", "Write", "Bash")
        if self._builtin_tools:
            opts["tools"] = self._builtin_tools

        # Prepare custom tools (FunctionTool instances)
        custom_tools_server, custom_tool_names = (
            self._prepare_tools(self._custom_tools) if self._custom_tools else (None, [])
        )

        # MCP servers - merge user-provided servers with custom tools server
        mcp_servers = dict(self._mcp_servers) if self._mcp_servers else {}
        if custom_tools_server:
            mcp_servers[TOOLS_MCP_SERVER_NAME] = custom_tools_server
        if mcp_servers:
            opts["mcp_servers"] = mcp_servers

        # Add custom tools to allowed_tools so they can be executed
        if custom_tool_names:
            existing_allowed = opts.get("allowed_tools", [])
            opts["allowed_tools"] = list(existing_allowed) + custom_tool_names

        # Always enable partial messages for streaming support
        opts["include_partial_messages"] = True

        return SDKOptions(**opts)

    def _prepare_tools(
        self,
        tools: Sequence[ToolTypes],
    ) -> tuple[Any, list[str]]:
        """Convert Agent Framework tools to SDK MCP server.

        Args:
            tools: List of Agent Framework tools.

        Returns:
            Tuple of (MCP server config, list of allowed tool names).
        """
        sdk_tools: list[SdkMcpTool[Any]] = []
        tool_names: list[str] = []

        for tool in tools:
            if isinstance(tool, FunctionTool):
                sdk_tools.append(self._function_tool_to_sdk_mcp_tool(tool))
                # Claude Agent SDK convention: MCP tools use format "mcp__{server}__{tool}"
                tool_names.append(f"mcp__{TOOLS_MCP_SERVER_NAME}__{tool.name}")
            else:
                # Non-FunctionTool items (e.g., dict-based hosted tools) cannot be converted to SDK MCP tools
                logger.debug(f"Unsupported tool type: {type(tool)}")

        if not sdk_tools:
            return None, []

        return create_sdk_mcp_server(name=TOOLS_MCP_SERVER_NAME, tools=sdk_tools), tool_names

    def _function_tool_to_sdk_mcp_tool(self, func_tool: FunctionTool) -> SdkMcpTool[Any]:
        """Convert a FunctionTool to an SDK MCP tool.

        Args:
            func_tool: The FunctionTool to convert.

        Returns:
            An SdkMcpTool instance.
        """
        approval_handler = self._function_approval_handler
        requires_approval = func_tool.approval_mode == "always_require"

        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            """Handler that invokes the FunctionTool."""
            try:
                if requires_approval and not await _resolve_function_approval(approval_handler, func_tool, args):
                    deny_text = (
                        f"Tool '{func_tool.name}' requires human approval "
                        "(approval_mode='always_require') and the request was denied."
                        if approval_handler is not None
                        else (
                            f"Tool '{func_tool.name}' requires human approval "
                            "(approval_mode='always_require') but no on_function_approval "
                            "callback is configured on the agent; the request was denied."
                        )
                    )
                    logger.warning(
                        "Denying execution of tool '%s' (approval_mode='always_require', %s)",
                        func_tool.name,
                        "callback denied" if approval_handler is not None else "no callback configured",
                    )
                    return {"content": [{"type": "text", "text": deny_text}]}
                if func_tool.input_model:
                    args_instance = func_tool.input_model(**args)
                    result = await func_tool.invoke(arguments=args_instance)
                else:
                    result = await func_tool.invoke(arguments=args)
                content_blocks: list[dict[str, str]] = []
                for c in result:
                    if c.type == "text" and c.text:
                        content_blocks.append({"type": "text", "text": c.text})
                    elif c.type in ("data", "uri"):
                        logger.warning(
                            "Claude Agent SDK does not support rich content (images, audio) "
                            "in tool results. Rich content items will be omitted."
                        )
                return {"content": content_blocks or [{"type": "text", "text": ""}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error: {e}"}]}

        # Get JSON schema from pydantic model
        schema: dict[str, Any] = func_tool.input_model.model_json_schema() if func_tool.input_model else {}
        input_schema: dict[str, Any] = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }
        # Preserve $defs for nested type references (Pydantic uses $defs for nested models)
        if "$defs" in schema:
            input_schema["$defs"] = schema["$defs"]

        return SdkMcpTool(
            name=func_tool.name,
            description=func_tool.description,
            input_schema=input_schema,
            handler=handler,
        )

    async def _apply_runtime_options(self, client: ClaudeSDKClient, options: dict[str, Any] | None) -> None:
        """Apply runtime options that can be changed dynamically.

        The Claude SDK supports changing model and permission_mode after connection.

        Args:
            client: The per-run client to apply the options to.
            options: Runtime options to apply.
        """
        if not options:
            return

        if "on_function_approval" in options:
            raise ValueError(
                "on_function_approval is a security-sensitive option and must be set "
                "via default_options at agent construction time. It cannot be overridden "
                "per run."
            )

        if "model" in options:
            await client.set_model(options["model"])

        if "permission_mode" in options:
            await client.set_permission_mode(options["permission_mode"])

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

    def _finalize_response(self, updates: Sequence[AgentResponseUpdate], structured_output: Any) -> AgentResponse[Any]:
        """Build AgentResponse and propagate structured_output as value.

        Args:
            updates: The collected stream updates.
            structured_output: The run-scoped structured output captured during the
                run, propagated as the response value if present.

        Returns:
            An AgentResponse with structured_output set as value if present.
        """
        return AgentResponse.from_updates(updates, value=structured_output)

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        options: OptionsT | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
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
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Run the agent with the given messages.

        Args:
            messages: The messages to process.

        Keyword Args:
            stream: If True, returns an async iterable of updates. If False (default),
                returns an awaitable AgentResponse.
            session: The conversation session. If session has service_session_id set,
                the agent will resume that session.
            options: Runtime options. Model and permission_mode can be changed per request.
            kwargs: Additional keyword arguments for compatibility with the shared agent
                interface (e.g. compaction_strategy, tokenizer). Not used by ClaudeAgent.

        Returns:
            When stream=True: An ResponseStream for streaming updates.
            When stream=False: An Awaitable[AgentResponse] with the complete response.
        """
        # Structured output is scoped to this run so concurrent runs on a shared
        # agent instance cannot overwrite each other's value before the finalizer
        # reads it.
        run_state: dict[str, Any] = {"structured_output": None}
        response = ResponseStream(
            self._get_stream(messages, session=session, options=options, run_state=run_state),
            finalizer=lambda updates: self._finalize_response(updates, run_state["structured_output"]),
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
        run_state: dict[str, Any] | None = None,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Internal streaming implementation."""
        if run_state is None:
            run_state = {"structured_output": None}

        # An injected client is a single caller-owned conversation: reuse the
        # session it is bound to when the caller passes none (so multi-turn runs
        # stay continuous), and serialize access so its connection is not raced
        # and concurrent runs do not interleave on the one shared client.
        if self._client is not None and not self._owns_client:
            if session is None and self._injected_session is not None:
                session = self._injected_session
            session = session or self.create_session()
            async with self._client_lock:
                client, _ = await self._acquire_client(session)
                async for update in self._stream_run(client, session, messages, options, run_state):
                    yield update
            return

        # A ClaudeSDKClient represents a single provider conversation, so each run
        # acquires its own client (resuming the framework session's provider
        # conversation when one exists) and releases it when the run completes.
        # Binding the client to the run keeps distinct sessions isolated even when
        # they run concurrently against the same agent instance.
        session = session or self.create_session()
        client, owns_client = await self._acquire_client(session)
        try:
            async for update in self._stream_run(client, session, messages, options, run_state):
                yield update
        finally:
            if owns_client:
                with contextlib.suppress(Exception):
                    await client.disconnect()

    async def _stream_run(
        self,
        client: ClaudeSDKClient,
        session: AgentSession,
        messages: AgentRunInputs | None,
        options: OptionsT | None,
        run_state: dict[str, Any],
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Run a single query against ``client`` and stream response updates.

        Args:
            client: The per-run Claude SDK client to query.
            session: The active session; its ``service_session_id`` is updated with
                the provider conversation id when the run completes.
            messages: The input messages for this run.
            options: Runtime options (model, permission_mode) for this run.
            run_state: Per-run state holder; the structured output is written here
                for the run's finalizer instead of on shared agent state.
        """
        prompt = self._format_prompt(normalize_messages(messages))

        # Apply runtime options (model, permission_mode)
        await self._apply_runtime_options(client, dict(options) if options else None)

        session_id: str | None = None
        structured_output: Any = None

        mark_feature_used(FeatureIndex.CLAUDE)
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, StreamEvent):
                # Handle streaming events - extract text/thinking deltas
                event = message.event
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield AgentResponseUpdate(
                                role="assistant",
                                contents=[Content.from_text(text=text, raw_representation=message)],
                                raw_representation=message,
                            )
                    elif delta_type == "thinking_delta":
                        thinking = delta.get("thinking", "")
                        if thinking:
                            yield AgentResponseUpdate(
                                role="assistant",
                                contents=[Content.from_text_reasoning(text=thinking, raw_representation=message)],
                                raw_representation=message,
                            )
            elif isinstance(message, AssistantMessage):
                # Handle AssistantMessage - check for API errors
                # Note: In streaming mode, the content was already yielded via StreamEvent,
                # so we only check for errors here, not re-emit content.
                if message.error:
                    # Map error types to descriptive messages
                    error_messages = {
                        "authentication_failed": "Authentication failed with Claude API",
                        "billing_error": "Billing error with Claude API",
                        "rate_limit": "Rate limit exceeded for Claude API",
                        "invalid_request": "Invalid request to Claude API",
                        "server_error": "Claude API server error",
                        "unknown": "Unknown error from Claude API",
                    }
                    error_msg = error_messages.get(message.error, f"Claude API error: {message.error}")
                    # Extract any error details from content blocks
                    if message.content:
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                error_msg = f"{error_msg}: {block.text}"
                                break
                    raise AgentException(error_msg)
            elif isinstance(message, ResultMessage):
                # Check for errors in result message
                if message.is_error:
                    error_msg = message.result or "Unknown error from Claude API"
                    raise AgentException(f"Claude API error: {error_msg}")
                session_id = message.session_id
                structured_output = message.structured_output
                usage = message.usage or {}
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
                total_token_count = (
                    input_tokens + output_tokens
                    if isinstance(input_tokens, int) and isinstance(output_tokens, int)
                    else None
                )
                usage_details = UsageDetails(**{
                    key: value
                    for key, value in {
                        "input_token_count": input_tokens,
                        "output_token_count": output_tokens,
                        "total_token_count": total_token_count,
                        "cache_creation_input_token_count": usage.get("cache_creation_input_tokens"),
                        "cache_read_input_token_count": usage.get("cache_read_input_tokens"),
                    }.items()
                    if isinstance(value, int)
                })
                finish_reason = (
                    FINISH_REASON_MAP.get(message.stop_reason, message.stop_reason) if message.stop_reason else None
                )
                if usage_details or finish_reason:
                    yield AgentResponseUpdate(
                        contents=[Content.from_usage(usage_details, raw_representation=message)]
                        if usage_details
                        else None,
                        finish_reason=cast(Any, finish_reason),
                        raw_representation=message,
                    )

        # Update session with session ID
        if session_id:
            session.service_session_id = session_id

        # Store structured output for the run's finalizer (run-scoped, not on self)
        run_state["structured_output"] = structured_output


class ClaudeAgent(AgentTelemetryLayer, RawClaudeAgent[OptionsT], Generic[OptionsT]):
    """Claude Agent with OpenTelemetry instrumentation.

    This is the recommended agent class for most use cases. It includes
    OpenTelemetry-based telemetry for observability. For a minimal
    implementation without telemetry, use :class:`RawClaudeAgent`.

    Examples:
        Basic usage with context manager:

        .. code-block:: python

            from agent_framework.anthropic import ClaudeAgent

            async with ClaudeAgent(
                instructions="You are a helpful assistant.",
            ) as agent:
                response = await agent.run("Hello!")
                print(response.text)
    """

    @overload
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

    @overload
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

    def run(  # pyright: ignore[reportIncompatibleMethodOverride]
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
        """Run the Claude agent with telemetry enabled."""
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

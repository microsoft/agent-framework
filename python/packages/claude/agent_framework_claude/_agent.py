# Copyright (c) Microsoft. All rights reserved.

import contextlib
import sys
from collections.abc import AsyncIterable, Callable, MutableMapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic

from agent_framework import (
    AgentMiddlewareTypes,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Content,
    ContextProvider,
    FunctionTool,
    Role,
    ToolProtocol,
    get_logger,
    normalize_messages,
)
from agent_framework._types import normalize_tools
from agent_framework.exceptions import ServiceException, ServiceInitializationError
from claude_agent_sdk import (
    ClaudeAgentOptions as SDKOptions,
)
from claude_agent_sdk import (
    ClaudeSDKClient,
    ResultMessage,
    SdkMcpTool,
    create_sdk_mcp_server,
)
from claude_agent_sdk.types import StreamEvent
from pydantic import ValidationError

from ._settings import ClaudeAgentSettings

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
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
    )

__all__ = ["ClaudeAgent", "ClaudeAgentOptions"]

logger = get_logger("agent_framework.claude")

# Name of the in-process MCP server that hosts Agent Framework tools.
# FunctionTool instances are converted to SDK MCP tools and served
# through this server, as Claude Code CLI only supports tools via MCP.
TOOLS_MCP_SERVER_NAME = "_agent_framework_tools"


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

    max_thinking_tokens: int
    """Maximum tokens for thinking blocks."""

    allowed_tools: list[str]
    """Allowlist of tools. If set, Claude can ONLY use tools in this list."""

    disallowed_tools: list[str]
    """Blocklist of tools. Claude cannot use these tools."""

    mcp_servers: dict[str, "McpServerConfig"]
    """MCP server configurations for external tools."""

    permission_mode: "PermissionMode"
    """Permission handling mode ("default", "acceptEdits", "plan", "bypassPermissions")."""

    can_use_tool: "CanUseTool"
    """Permission callback for tool use."""

    max_turns: int
    """Maximum conversation turns."""

    max_budget_usd: float
    """Budget limit in USD."""

    hooks: dict[str, list["HookMatcher"]]
    """Pre/post tool hooks."""

    add_dirs: list[str | Path]
    """Additional directories to add to context."""

    sandbox: "SandboxSettings"
    """Sandbox configuration for bash isolation."""

    agents: dict[str, "AgentDefinition"]
    """Custom agent definitions."""

    output_format: dict[str, Any]
    """Structured output format (JSON schema)."""

    enable_file_checkpointing: bool
    """Enable file checkpointing for rewind."""

    betas: list["SdkBeta"]
    """Beta features to enable."""


TOptions = TypeVar(
    "TOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ClaudeAgentOptions",
    covariant=True,
)


class ClaudeAgent(BaseAgent, Generic[TOptions]):
    """Claude Agent using Claude Code CLI.

    Wraps the Claude Agent SDK to provide agentic capabilities including
    tool use, session management, and streaming responses.

    This agent communicates with Claude through the Claude Code CLI,
    enabling access to Claude's full agentic capabilities like file
    editing, code execution, and tool use.

    The agent can be used as an async context manager to ensure proper cleanup:

    Examples:
        Basic usage with context manager:

        .. code-block:: python

            from agent_framework_claude import ClaudeAgent

            async with ClaudeAgent(
                instructions="You are a helpful assistant.",
            ) as agent:
                response = await agent.run("Hello!")
                print(response.text)

        With streaming:

        .. code-block:: python

            async with ClaudeAgent() as agent:
                async for update in agent.run_stream("Write a poem"):
                    print(update.text, end="", flush=True)

        With session management:

        .. code-block:: python

            async with ClaudeAgent() as agent:
                thread = agent.get_new_thread()
                await agent.run("Remember my name is Alice", thread=thread)
                response = await agent.run("What's my name?", thread=thread)
                # Claude will remember "Alice" from the same session

        With Agent Framework tools:

        .. code-block:: python

            from agent_framework import tool

            @tool
            def greet(name: str) -> str:
                \"\"\"Greet someone by name.\"\"\"
                return f"Hello, {name}!"

            async with ClaudeAgent(tools=[greet]) as agent:
                response = await agent.run("Greet Alice")
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
        context_provider: ContextProvider | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | str
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any] | str]
        | None = None,
        default_options: TOptions | MutableMapping[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a ClaudeAgent instance.

        Args:
            instructions: System prompt for the agent.

        Keyword Args:
            client: Optional pre-configured ClaudeSDKClient instance. If not provided,
                a new client will be created using the other parameters.
            id: Unique identifier for the agent.
            name: Name of the agent.
            description: Description of the agent.
            context_provider: Context provider for the agent.
            middleware: List of middleware.
            tools: Tools for the agent. Can be:
                - Strings for built-in tools (e.g., "Read", "Write", "Bash", "Glob")
                - Functions or ToolProtocol instances for custom tools
            default_options: Default ClaudeAgentOptions including system_prompt, model, etc.
            env_file_path: Path to .env file.
            env_file_encoding: Encoding of .env file.
        """
        super().__init__(
            id=id,
            name=name,
            description=description,
            context_provider=context_provider,
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

        # Load settings from environment and options
        try:
            self._settings = ClaudeAgentSettings(
                cli_path=cli_path,
                model=model,
                cwd=cwd,
                permission_mode=permission_mode,
                max_turns=max_turns,
                max_budget_usd=max_budget_usd,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Claude Agent settings.", ex) from ex

        # Separate built-in tools (strings) from custom tools (callables/ToolProtocol)
        self._builtin_tools: list[str] = []
        self._custom_tools: list[ToolProtocol | MutableMapping[str, Any]] = []
        self._normalize_tools(tools)

        self._default_options = opts
        self._started = False
        self._current_session_id: str | None = None

    def _normalize_tools(
        self,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | str
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any] | str]
        | None,
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
        elif isinstance(tools, (ToolProtocol, MutableMapping)) or callable(tools):
            tools_list = [tools]
        else:
            tools_list = list(tools)

        for tool in tools_list:
            if isinstance(tool, str):
                self._builtin_tools.append(tool)
            else:
                # Use normalize_tools for custom tools
                normalized = normalize_tools(tool)
                self._custom_tools.extend(normalized)

    async def __aenter__(self) -> "ClaudeAgent[TOptions]":
        """Start the agent when entering async context."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the agent when exiting async context."""
        await self.stop()

    async def start(self) -> None:
        """Start the Claude SDK client.

        This method initializes the Claude SDK client and establishes a connection
        to the Claude Code CLI. It is called automatically when using the agent
        as an async context manager.

        Raises:
            ServiceException: If the client fails to start.
        """
        await self._ensure_session()

    async def stop(self) -> None:
        """Stop the Claude SDK client and clean up resources.

        Stops the client if owned by this agent. Called automatically when
        using the agent as an async context manager.
        """
        if self._client and self._owns_client:
            with contextlib.suppress(Exception):
                await self._client.disconnect()

        self._started = False
        self._current_session_id = None

    async def _ensure_session(self, session_id: str | None = None) -> None:
        """Ensure the client is connected for the specified session.

        If the requested session differs from the current one, recreates the client.

        Args:
            session_id: The session ID to use, or None for a new session.
        """
        needs_new_client = (
            not self._started or self._client is None or (session_id and session_id != self._current_session_id)
        )

        if needs_new_client:
            # Stop existing client if any
            if self._client and self._owns_client:
                with contextlib.suppress(Exception):
                    await self._client.disconnect()
                self._started = False

            # Create new client with resume option if needed
            opts = self._prepare_client_options(resume_session_id=session_id)
            self._client = ClaudeSDKClient(options=opts)
            self._owns_client = True

            try:
                await self._client.connect()
                self._started = True
                self._current_session_id = session_id
            except Exception as ex:
                self._client = None
                raise ServiceException(f"Failed to start Claude SDK client: {ex}") from ex

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
        if self._settings.cli_path:
            opts["cli_path"] = self._settings.cli_path
        if self._settings.model:
            opts["model"] = self._settings.model
        if self._settings.cwd:
            opts["cwd"] = self._settings.cwd
        if self._settings.permission_mode:
            opts["permission_mode"] = self._settings.permission_mode
        if self._settings.max_turns:
            opts["max_turns"] = self._settings.max_turns
        if self._settings.max_budget_usd:
            opts["max_budget_usd"] = self._settings.max_budget_usd

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
        tools: list[ToolProtocol | MutableMapping[str, Any]],
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
            elif isinstance(tool, ToolProtocol):
                logger.debug(f"Unsupported tool type: {type(tool)}")

        if not sdk_tools:
            return None, []

        return create_sdk_mcp_server(name=TOOLS_MCP_SERVER_NAME, tools=sdk_tools), tool_names

    def _function_tool_to_sdk_mcp_tool(self, func_tool: FunctionTool[Any, Any]) -> SdkMcpTool[Any]:
        """Convert a FunctionTool to an SDK MCP tool.

        Args:
            func_tool: The FunctionTool to convert.

        Returns:
            An SdkMcpTool instance.
        """

        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            """Handler that invokes the FunctionTool."""
            try:
                if func_tool.input_model:
                    args_instance = func_tool.input_model(**args)
                    result = await func_tool.invoke(arguments=args_instance)
                else:
                    result = await func_tool.invoke(arguments=args)
                return {"content": [{"type": "text", "text": str(result)}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error: {e}"}]}

        # Get JSON schema from pydantic model
        schema: dict[str, Any] = func_tool.input_model.model_json_schema() if func_tool.input_model else {}
        input_schema: dict[str, Any] = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }

        return SdkMcpTool(
            name=func_tool.name,
            description=func_tool.description,
            input_schema=input_schema,
            handler=handler,
        )

    async def _apply_runtime_options(self, options: dict[str, Any] | None) -> None:
        """Apply runtime options that can be changed dynamically.

        The Claude SDK supports changing model and permission_mode after connection.

        Args:
            options: Runtime options to apply.
        """
        if not options or not self._client:
            return

        if "model" in options:
            await self._client.set_model(options["model"])

        if "permission_mode" in options:
            await self._client.set_permission_mode(options["permission_mode"])

    def _format_prompt(self, messages: list[ChatMessage] | None) -> str:
        """Format messages into a prompt string.

        Args:
            messages: List of chat messages.

        Returns:
            Formatted prompt string.
        """
        if not messages:
            return ""
        return "\n".join([msg.text or "" for msg in messages])

    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        options: TOptions | MutableMapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse[Any]:
        """Run the agent with the given messages.

        Args:
            messages: The messages to process.

        Keyword Args:
            thread: The conversation thread. If thread has service_thread_id set,
                the agent will resume that session.
            options: Runtime options (model, permission_mode can be changed per-request).
            kwargs: Additional keyword arguments.

        Returns:
            AgentResponse with the agent's response.
        """
        thread = thread or self.get_new_thread()
        return await AgentResponse.from_agent_response_generator(
            self.run_stream(messages, thread=thread, options=options, **kwargs)
        )

    async def run_stream(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        options: TOptions | MutableMapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Stream the agent's response.

        Args:
            messages: The messages to process.

        Keyword Args:
            thread: The conversation thread. If thread has service_thread_id set,
                the agent will resume that session.
            options: Runtime options (model, permission_mode can be changed per-request).
            kwargs: Additional keyword arguments.

        Yields:
            AgentResponseUpdate objects containing chunks of the response.
        """
        thread = thread or self.get_new_thread()

        # Ensure we're connected to the right session
        await self._ensure_session(thread.service_thread_id)

        if not self._client:
            raise ServiceException("Claude SDK client not initialized.")

        prompt = self._format_prompt(normalize_messages(messages))

        # Apply runtime options (model, permission_mode)
        await self._apply_runtime_options(dict(options) if options else None)

        session_id: str | None = None

        await self._client.query(prompt)
        async for message in self._client.receive_response():
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
                                role=Role.ASSISTANT,
                                contents=[Content.from_text(text=text, raw_representation=message)],
                                raw_representation=message,
                            )
                    elif delta_type == "thinking_delta":
                        thinking = delta.get("thinking", "")
                        if thinking:
                            yield AgentResponseUpdate(
                                role=Role.ASSISTANT,
                                contents=[Content.from_text_reasoning(text=thinking, raw_representation=message)],
                                raw_representation=message,
                            )
            elif isinstance(message, ResultMessage):
                session_id = message.session_id

        # Update thread with session ID
        if session_id:
            thread.service_thread_id = session_id

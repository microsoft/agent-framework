# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncIterable, Callable, MutableMapping, Sequence
from typing import Any, ClassVar, Generic, TypedDict

from agent_framework import (
    AgentMiddlewareTypes,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Content,
    ContextProvider,
    Role,
    normalize_messages,
)
from agent_framework._tools import FunctionTool, ToolProtocol
from agent_framework._types import normalize_tools
from agent_framework.exceptions import ServiceException, ServiceInitializationError
from copilot import CopilotClient, CopilotSession
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.types import (
    CopilotClientOptions,
    MCPServerConfig,
    PermissionRequest,
    PermissionRequestResult,
    ResumeSessionConfig,
    SessionConfig,
    ToolInvocation,
    ToolResult,
)
from copilot.types import Tool as CopilotTool
from pydantic import ValidationError

from ._settings import GitHubCopilotSettings

if sys.version_info >= (3, 13):
    from typing import TypeVar
else:
    from typing_extensions import TypeVar


DEFAULT_TIMEOUT_SECONDS: float = 60.0
"""Default timeout in seconds for Copilot requests."""

PermissionHandlerType = Callable[[PermissionRequest, dict[str, str]], PermissionRequestResult]
"""Type for permission request handlers."""

logger = logging.getLogger("agent_framework.github_copilot")


class GitHubCopilotOptions(TypedDict, total=False):
    """GitHub Copilot-specific options."""

    instructions: str
    """System message to append to the session."""

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


TOptions = TypeVar(
    "TOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="GitHubCopilotOptions",
    covariant=True,
)


class GitHubCopilotAgent(BaseAgent, Generic[TOptions]):
    """A GitHub Copilot Agent.

    This agent wraps the GitHub Copilot SDK to provide Copilot agentic capabilities
    within the Agent Framework. It supports both streaming and non-streaming responses,
    custom tools, and session management.

    The agent can be used as an async context manager to ensure proper cleanup:

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
                default_options={"model": "claude-sonnet-4", "timeout": 120}
            )

        With tools:

        .. code-block:: python

            def get_weather(city: str) -> str:
                return f"Weather in {city} is sunny"


            async with GitHubCopilotAgent(tools=[get_weather]) as agent:
                response = await agent.run("What's the weather in Seattle?")
    """

    AGENT_PROVIDER_NAME: ClassVar[str] = "github.copilot"

    def __init__(
        self,
        *,
        client: CopilotClient | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_provider: ContextProvider | None = None,
        middleware: Sequence[AgentMiddlewareTypes] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        default_options: TOptions | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the GitHub Copilot Agent.

        Keyword Args:
            client: Optional pre-configured CopilotClient instance. If not provided,
                a new client will be created using the other parameters.
            id: ID of the GitHubCopilotAgent.
            name: Name of the GitHubCopilotAgent.
            description: Description of the GitHubCopilotAgent.
            context_provider: Context Provider, to be used by the agent.
            middleware: Agent middleware used by the agent.
            tools: Tools to use for the agent. Can be functions, ToolProtocol instances,
                or tool definition dicts. These are converted to Copilot SDK tools internally.
            default_options: Default options for the agent. Can include cli_path, model,
                timeout, log_level, etc.
            env_file_path: Optional path to .env file for loading configuration.
            env_file_encoding: Encoding of the .env file, defaults to 'utf-8'.

        Raises:
            ServiceInitializationError: If required configuration is missing or invalid.
        """
        super().__init__(
            id=id,
            name=name,
            description=description,
            context_provider=context_provider,
            middleware=list(middleware) if middleware else None,
        )

        self._client = client
        self._owns_client = client is None

        # Parse options
        opts: dict[str, Any] = dict(default_options) if default_options else {}
        instructions = opts.pop("instructions", None)
        cli_path = opts.pop("cli_path", None)
        model = opts.pop("model", None)
        timeout = opts.pop("timeout", None)
        log_level = opts.pop("log_level", None)
        on_permission_request: PermissionHandlerType | None = opts.pop("on_permission_request", None)
        mcp_servers: dict[str, MCPServerConfig] | None = opts.pop("mcp_servers", None)

        try:
            self._settings = GitHubCopilotSettings(
                cli_path=cli_path,
                model=model,
                timeout=timeout,
                log_level=log_level,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create GitHub Copilot settings.", ex) from ex

        self._instructions = instructions
        self._tools = normalize_tools(tools)
        self._permission_handler = on_permission_request
        self._mcp_servers = mcp_servers
        self._default_options = opts
        self._started = False

    async def __aenter__(self) -> "GitHubCopilotAgent[TOptions]":
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
            ServiceException: If the client fails to start.
        """
        if self._started:
            return

        if self._client is None:
            client_options: CopilotClientOptions = {}
            if self._settings.cli_path:
                client_options["cli_path"] = self._settings.cli_path
            if self._settings.log_level:
                client_options["log_level"] = self._settings.log_level  # type: ignore[typeddict-item]

            self._client = CopilotClient(client_options if client_options else None)

        try:
            await self._client.start()
            self._started = True
        except Exception as ex:
            raise ServiceException(f"Failed to start GitHub Copilot client: {ex}") from ex

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

    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        options: TOptions | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single AgentResponse object. The caller is blocked until
        the final result is available.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            thread: The conversation thread associated with the message(s).
            options: Runtime options (model, timeout, etc.).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.

        Raises:
            ServiceException: If the request fails.
        """
        if not self._started:
            await self.start()

        if not thread:
            thread = self.get_new_thread()

        opts: dict[str, Any] = dict(options) if options else {}
        timeout = opts.pop("timeout", None) or self._settings.timeout or DEFAULT_TIMEOUT_SECONDS

        session = await self._get_or_create_session(thread, streaming=False)
        input_messages = normalize_messages(messages)
        prompt = "\n".join([message.text for message in input_messages])

        try:
            response_event = await session.send_and_wait({"prompt": prompt}, timeout=timeout)
        except Exception as ex:
            raise ServiceException(f"GitHub Copilot request failed: {ex}") from ex

        response_messages: list[ChatMessage] = []
        response_id: str | None = None

        # send_and_wait returns only the final ASSISTANT_MESSAGE event;
        # other events (deltas, tool calls) are handled internally by the SDK.
        if response_event and response_event.type == SessionEventType.ASSISTANT_MESSAGE:
            message_id = response_event.data.message_id

            if response_event.data.content:
                response_messages.append(
                    ChatMessage(
                        role=Role.ASSISTANT,
                        contents=[Content.from_text(response_event.data.content)],
                        message_id=message_id,
                        raw_representation=response_event,
                    )
                )
            response_id = message_id

        return AgentResponse(messages=response_messages, response_id=response_id)

    async def run_stream(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        options: TOptions | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Run the agent as a stream.

        This method will return the intermediate steps and final results of the
        agent's execution as a stream of AgentResponseUpdate objects to the caller.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            thread: The conversation thread associated with the message(s).
            options: Runtime options (model, timeout, etc.).
            kwargs: Additional keyword arguments.

        Yields:
            An agent response update for each delta.

        Raises:
            ServiceException: If the request fails.
        """
        if not self._started:
            await self.start()

        if not thread:
            thread = self.get_new_thread()

        session = await self._get_or_create_session(thread, streaming=True)
        input_messages = normalize_messages(messages)
        prompt = "\n".join([message.text for message in input_messages])

        queue: asyncio.Queue[AgentResponseUpdate | Exception | None] = asyncio.Queue()

        def event_handler(event: SessionEvent) -> None:
            if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                if event.data.delta_content:
                    update = AgentResponseUpdate(
                        role=Role.ASSISTANT,
                        contents=[Content.from_text(event.data.delta_content)],
                        response_id=event.data.message_id,
                        message_id=event.data.message_id,
                        raw_representation=event,
                    )
                    queue.put_nowait(update)
            elif event.type == SessionEventType.SESSION_IDLE:
                queue.put_nowait(None)
            elif event.type == SessionEventType.SESSION_ERROR:
                error_msg = event.data.message or "Unknown error"
                queue.put_nowait(ServiceException(f"GitHub Copilot session error: {error_msg}"))

        unsubscribe = session.on(event_handler)

        try:
            await session.send({"prompt": prompt})

            while (item := await queue.get()) is not None:
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            unsubscribe()

    def _prepare_tools(
        self,
        tools: list[ToolProtocol | MutableMapping[str, Any]],
    ) -> list[CopilotTool]:
        """Convert Agent Framework tools to Copilot SDK tools.

        Args:
            tools: List of Agent Framework tools.

        Returns:
            List of Copilot SDK tools.
        """
        copilot_tools: list[CopilotTool] = []

        for tool in tools:
            if isinstance(tool, ToolProtocol):
                match tool:
                    case FunctionTool():
                        copilot_tools.append(self._tool_to_copilot_tool(tool))  # type: ignore
                    case _:
                        logger.debug(f"Unsupported tool type: {type(tool)}")
            elif isinstance(tool, CopilotTool):
                copilot_tools.append(tool)

        return copilot_tools

    def _tool_to_copilot_tool(self, ai_func: FunctionTool[Any, Any]) -> CopilotTool:
        """Convert an FunctionTool to a Copilot SDK tool."""

        async def handler(invocation: ToolInvocation) -> ToolResult:
            args = invocation.get("arguments", {})
            try:
                if ai_func.input_model:
                    args_instance = ai_func.input_model(**args)
                    result = await ai_func.invoke(arguments=args_instance)
                else:
                    result = await ai_func.invoke(arguments=args)
                return ToolResult(
                    textResultForLlm=str(result),
                    resultType="success",
                )
            except Exception as e:
                return ToolResult(
                    textResultForLlm=f"Error: {e}",
                    resultType="failure",
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
        thread: AgentThread,
        streaming: bool = False,
    ) -> CopilotSession:
        """Get an existing session or create a new one for the thread.

        Args:
            thread: The conversation thread.
            streaming: Whether to enable streaming for the session.

        Returns:
            A CopilotSession instance.

        Raises:
            ServiceException: If the session cannot be created.
        """
        if not self._client:
            raise ServiceException("GitHub Copilot client not initialized. Call start() first.")

        try:
            if thread.service_thread_id:
                return await self._resume_session(thread.service_thread_id, streaming)

            session = await self._create_session(streaming)
            thread.service_thread_id = session.session_id
            return session
        except Exception as ex:
            raise ServiceException(f"Failed to create GitHub Copilot session: {ex}") from ex

    async def _create_session(self, streaming: bool) -> CopilotSession:
        """Create a new Copilot session."""
        if not self._client:
            raise ServiceException("GitHub Copilot client not initialized. Call start() first.")

        config: SessionConfig = {"streaming": streaming}

        if self._settings.model:
            config["model"] = self._settings.model  # type: ignore[typeddict-item]

        if self._instructions:
            config["system_message"] = {"mode": "append", "content": self._instructions}

        if self._tools:
            config["tools"] = self._prepare_tools(self._tools)

        if self._permission_handler:
            config["on_permission_request"] = self._permission_handler

        if self._mcp_servers:
            config["mcp_servers"] = self._mcp_servers

        return await self._client.create_session(config)

    async def _resume_session(self, session_id: str, streaming: bool) -> CopilotSession:
        """Resume an existing Copilot session by ID."""
        if not self._client:
            raise ServiceException("GitHub Copilot client not initialized. Call start() first.")

        config: ResumeSessionConfig = {"streaming": streaming}

        if self._tools:
            config["tools"] = self._prepare_tools(self._tools)

        if self._permission_handler:
            config["on_permission_request"] = self._permission_handler

        if self._mcp_servers:
            config["mcp_servers"] = self._mcp_servers

        return await self._client.resume_session(session_id, config)

# Copyright (c) Microsoft. All rights reserved.

import unittest.mock
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    ChatMessage,
    Content,
    Role,
)
from agent_framework.exceptions import ServiceException
from copilot.generated.session_events import Data, SessionEvent, SessionEventType

from agent_framework_github_copilot import GitHubCopilotAgent, GitHubCopilotOptions


def create_session_event(
    event_type: SessionEventType,
    content: str | None = None,
    delta_content: str | None = None,
    message_id: str | None = None,
    error_message: str | None = None,
) -> SessionEvent:
    """Create a mock session event for testing."""
    data = Data(
        content=content,
        delta_content=delta_content,
        message_id=message_id or str(uuid4()),
        message=error_message,
    )
    return SessionEvent(
        data=data,
        id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        type=event_type,
    )


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock CopilotSession."""
    session = MagicMock()
    session.session_id = "test-session-id"
    session.send = AsyncMock(return_value="test-message-id")
    session.send_and_wait = AsyncMock()
    session.destroy = AsyncMock()
    session.on = MagicMock(return_value=lambda: None)
    return session


@pytest.fixture
def mock_client(mock_session: MagicMock) -> MagicMock:
    """Create a mock CopilotClient."""
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock(return_value=[])
    client.create_session = AsyncMock(return_value=mock_session)
    client.resume_session = AsyncMock(return_value=mock_session)
    return client


@pytest.fixture
def assistant_message_event() -> SessionEvent:
    """Create a mock assistant message event."""
    return create_session_event(
        SessionEventType.ASSISTANT_MESSAGE,
        content="Test response",
        message_id="test-msg-id",
    )


@pytest.fixture
def assistant_delta_event() -> SessionEvent:
    """Create a mock assistant message delta event."""
    return create_session_event(
        SessionEventType.ASSISTANT_MESSAGE_DELTA,
        delta_content="Hello",
        message_id="test-msg-id",
    )


@pytest.fixture
def session_idle_event() -> SessionEvent:
    """Create a mock session idle event."""
    return create_session_event(SessionEventType.SESSION_IDLE)


@pytest.fixture
def session_error_event() -> SessionEvent:
    """Create a mock session error event."""
    return create_session_event(
        SessionEventType.SESSION_ERROR,
        error_message="Test error",
    )


class TestGitHubCopilotAgentInit:
    """Test cases for GitHubCopilotAgent initialization."""

    def test_init_with_client(self, mock_client: MagicMock) -> None:
        """Test initialization with pre-configured client."""
        agent = GitHubCopilotAgent(client=mock_client)
        assert agent._client == mock_client  # type: ignore
        assert agent._owns_client is False  # type: ignore
        assert agent.id is not None

    def test_init_without_client(self) -> None:
        """Test initialization without client creates settings."""
        agent = GitHubCopilotAgent()
        assert agent._client is None  # type: ignore
        assert agent._owns_client is True  # type: ignore
        assert agent._settings is not None  # type: ignore

    def test_init_with_default_options(self) -> None:
        """Test initialization with default_options parameter."""
        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            default_options={"model": "claude-sonnet-4", "timeout": 120}
        )
        assert agent._settings.model == "claude-sonnet-4"  # type: ignore
        assert agent._settings.timeout == 120  # type: ignore

    def test_init_with_tools(self) -> None:
        """Test initialization with function tools."""

        def my_tool(arg: str) -> str:
            return f"Result: {arg}"

        agent = GitHubCopilotAgent(tools=[my_tool])
        assert len(agent._tools) == 1  # type: ignore

    def test_init_with_instructions(self) -> None:
        """Test initialization with custom instructions."""
        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            default_options={"instructions": "You are a helpful assistant."}
        )
        assert agent._instructions == "You are a helpful assistant."  # type: ignore


class TestGitHubCopilotAgentLifecycle:
    """Test cases for agent lifecycle management."""

    async def test_start_creates_client(self) -> None:
        """Test that start creates a client if none provided."""
        with patch("agent_framework_github_copilot._agent.CopilotClient") as MockClient:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            MockClient.return_value = mock_client

            agent = GitHubCopilotAgent()
            await agent.start()

            MockClient.assert_called_once()
            mock_client.start.assert_called_once()
            assert agent._started is True  # type: ignore

    async def test_start_uses_existing_client(self, mock_client: MagicMock) -> None:
        """Test that start uses provided client."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        mock_client.start.assert_called_once()
        assert agent._started is True  # type: ignore

    async def test_start_idempotent(self, mock_client: MagicMock) -> None:
        """Test that calling start multiple times is safe."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()
        await agent.start()

        mock_client.start.assert_called_once()

    async def test_stop_cleans_up(self, mock_client: MagicMock, mock_session: MagicMock) -> None:
        """Test that stop resets started state."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent.stop()

        assert agent._started is False  # type: ignore

    async def test_context_manager(self, mock_client: MagicMock) -> None:
        """Test async context manager usage."""
        async with GitHubCopilotAgent(client=mock_client) as agent:
            assert agent._started is True  # type: ignore

        # When client is provided externally, agent doesn't own it and won't stop it
        mock_client.stop.assert_not_called()
        assert agent._started is False  # type: ignore

    async def test_stop_calls_client_stop_when_agent_owns_client(self) -> None:
        """Test that stop calls client.stop() when agent created the client."""
        with patch("agent_framework_github_copilot._agent.CopilotClient") as MockClient:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            MockClient.return_value = mock_client

            agent = GitHubCopilotAgent()
            await agent.start()
            await agent.stop()

            mock_client.stop.assert_called_once()

    async def test_start_creates_client_with_options(self) -> None:
        """Test that start creates client with cli_path and log_level from settings."""
        with patch("agent_framework_github_copilot._agent.CopilotClient") as MockClient:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            MockClient.return_value = mock_client

            agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
                default_options={"cli_path": "/custom/path", "log_level": "debug"}
            )
            await agent.start()

            call_args = MockClient.call_args[0][0]
            assert call_args["cli_path"] == "/custom/path"
            assert call_args["log_level"] == "debug"


class TestGitHubCopilotAgentRun:
    """Test cases for run method."""

    async def test_run_string_message(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with string message."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        response = await agent.run("Hello")

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        assert response.messages[0].role == Role.ASSISTANT
        assert response.messages[0].contents[0].text == "Test response"

    async def test_run_chat_message(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with ChatMessage."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        chat_message = ChatMessage(role=Role.USER, contents=[Content.from_text("Hello")])
        response = await agent.run(chat_message)

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1

    async def test_run_with_thread(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with existing thread."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        thread = AgentThread()
        response = await agent.run("Hello", thread=thread)

        assert isinstance(response, AgentResponse)
        assert thread.service_thread_id == mock_session.session_id

    async def test_run_with_runtime_options(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with runtime options."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        response = await agent.run("Hello", options={"timeout": 30})

        assert isinstance(response, AgentResponse)

    async def test_run_empty_response(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test run method with no response event."""
        mock_session.send_and_wait.return_value = None

        agent = GitHubCopilotAgent(client=mock_client)
        response = await agent.run("Hello")

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 0

    async def test_run_auto_starts(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that run auto-starts the agent if not started."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        assert agent._started is False  # type: ignore

        await agent.run("Hello")

        assert agent._started is True  # type: ignore
        mock_client.start.assert_called_once()


class TestGitHubCopilotAgentRunStream:
    """Test cases for run_stream method."""

    async def test_run_stream_basic(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test basic streaming response."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run_stream("Hello"):
            responses.append(update)

        assert len(responses) == 1
        assert isinstance(responses[0], AgentResponseUpdate)
        assert responses[0].role == Role.ASSISTANT
        assert responses[0].contents[0].text == "Hello"

    async def test_run_stream_with_thread(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test streaming with existing thread."""

        def mock_on(handler: Any) -> Any:
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        thread = AgentThread()

        async for _ in agent.run_stream("Hello", thread=thread):
            pass

        assert thread.service_thread_id == mock_session.session_id

    async def test_run_stream_error(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_error_event: SessionEvent,
    ) -> None:
        """Test streaming error handling."""

        def mock_on(handler: Any) -> Any:
            handler(session_error_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)

        with pytest.raises(ServiceException, match="session error"):
            async for _ in agent.run_stream("Hello"):
                pass

    async def test_run_stream_auto_starts(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that run_stream auto-starts the agent if not started."""

        def mock_on(handler: Any) -> Any:
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        assert agent._started is False  # type: ignore

        async for _ in agent.run_stream("Hello"):
            pass

        assert agent._started is True  # type: ignore
        mock_client.start.assert_called_once()


class TestGitHubCopilotAgentSessionManagement:
    """Test cases for session management."""

    async def test_session_resumed_for_same_thread(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that subsequent calls on the same thread resume the session."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        thread = AgentThread()

        await agent.run("Hello", thread=thread)
        await agent.run("World", thread=thread)

        mock_client.create_session.assert_called_once()
        mock_client.resume_session.assert_called_once_with(mock_session.session_id, unittest.mock.ANY)

    async def test_session_config_includes_model(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes model setting."""
        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client, default_options={"model": "claude-sonnet-4"}
        )
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert config["model"] == "claude-sonnet-4"

    async def test_session_config_includes_instructions(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes instructions."""
        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"instructions": "You are a helpful assistant."},
        )
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert config["system_message"]["mode"] == "append"
        assert config["system_message"]["content"] == "You are a helpful assistant."

    async def test_session_config_includes_streaming_flag(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes the streaming flag."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent._get_or_create_session(AgentThread(), streaming=True)  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert config["streaming"] is True

    async def test_resume_session_with_existing_service_thread_id(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session is resumed when thread has a service_thread_id."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        thread = AgentThread()
        thread.service_thread_id = "existing-session-id"

        await agent._get_or_create_session(thread)  # type: ignore

        mock_client.create_session.assert_not_called()
        mock_client.resume_session.assert_called_once()
        call_args = mock_client.resume_session.call_args
        assert call_args[0][0] == "existing-session-id"

    async def test_resume_session_includes_tools_and_permissions(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that resumed session config includes tools and permission handler."""
        from copilot.types import PermissionRequest, PermissionRequestResult

        def my_handler(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            return PermissionRequestResult(kind="approved")

        def my_tool(arg: str) -> str:
            """A test tool."""
            return arg

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            tools=[my_tool],
            default_options={"on_permission_request": my_handler},
        )
        await agent.start()

        thread = AgentThread()
        thread.service_thread_id = "existing-session-id"

        await agent._get_or_create_session(thread)  # type: ignore

        mock_client.resume_session.assert_called_once()
        call_args = mock_client.resume_session.call_args
        config = call_args[0][1]
        assert "tools" in config
        assert "on_permission_request" in config


class TestGitHubCopilotAgentMCPServers:
    """Test cases for MCP server configuration."""

    async def test_mcp_servers_passed_to_create_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that mcp_servers are passed through to create_session config."""
        from copilot.types import MCPServerConfig

        mcp_servers: dict[str, MCPServerConfig] = {
            "filesystem": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                "tools": ["*"],
            },
            "remote": {
                "type": "http",
                "url": "https://example.com/mcp",
                "tools": ["*"],
            },
        }

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"mcp_servers": mcp_servers},
        )
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert "mcp_servers" in config
        assert "filesystem" in config["mcp_servers"]
        assert "remote" in config["mcp_servers"]
        assert config["mcp_servers"]["filesystem"]["command"] == "npx"
        assert config["mcp_servers"]["remote"]["url"] == "https://example.com/mcp"

    async def test_mcp_servers_passed_to_resume_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that mcp_servers are passed through to resume_session config."""
        from copilot.types import MCPServerConfig

        mcp_servers: dict[str, MCPServerConfig] = {
            "test-server": {
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
                "tools": ["*"],
            },
        }

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"mcp_servers": mcp_servers},
        )
        await agent.start()

        thread = AgentThread()
        thread.service_thread_id = "existing-session-id"

        await agent._get_or_create_session(thread)  # type: ignore

        mock_client.resume_session.assert_called_once()
        call_args = mock_client.resume_session.call_args
        config = call_args[0][1]
        assert "mcp_servers" in config
        assert "test-server" in config["mcp_servers"]

    async def test_session_config_excludes_mcp_servers_when_not_set(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config does not include mcp_servers when not set."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert "mcp_servers" not in config


class TestGitHubCopilotAgentToolConversion:
    """Test cases for tool conversion."""

    async def test_function_tool_conversion(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that function tools are converted to Copilot tools."""

        def my_tool(arg: str) -> str:
            """A test tool."""
            return f"Result: {arg}"

        agent = GitHubCopilotAgent(client=mock_client, tools=[my_tool])
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert "tools" in config
        assert len(config["tools"]) == 1
        assert config["tools"][0].name == "my_tool"
        assert config["tools"][0].description == "A test tool."

    async def test_tool_handler_returns_success_result(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that tool handler returns success result on successful invocation."""

        def my_tool(arg: str) -> str:
            """A test tool."""
            return f"Result: {arg}"

        agent = GitHubCopilotAgent(client=mock_client, tools=[my_tool])
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        copilot_tool = config["tools"][0]

        result = await copilot_tool.handler({"arguments": {"arg": "test"}})

        assert result["resultType"] == "success"
        assert result["textResultForLlm"] == "Result: test"

    async def test_tool_handler_returns_failure_result_on_error(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that tool handler returns failure result when invocation raises exception."""

        def failing_tool(arg: str) -> str:
            """A tool that fails."""
            raise ValueError("Something went wrong")

        agent = GitHubCopilotAgent(client=mock_client, tools=[failing_tool])
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        copilot_tool = config["tools"][0]

        result = await copilot_tool.handler({"arguments": {"arg": "test"}})

        assert result["resultType"] == "failure"
        assert "Something went wrong" in result["textResultForLlm"]
        assert "Something went wrong" in result["error"]

    def test_copilot_tool_passthrough(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that CopilotTool instances are passed through as-is."""
        from copilot.types import Tool as CopilotTool

        async def tool_handler(invocation: Any) -> Any:
            return {"textResultForLlm": "result", "resultType": "success"}

        copilot_tool = CopilotTool(
            name="direct_tool",
            description="A direct CopilotTool",
            handler=tool_handler,
            parameters={"type": "object", "properties": {}},
        )

        agent = GitHubCopilotAgent(client=mock_client)
        result = agent._prepare_tools([copilot_tool])  # type: ignore

        assert len(result) == 1
        assert result[0] == copilot_tool

    def test_mixed_tools_conversion(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that mixed tool types are handled correctly."""
        from agent_framework import tool
        from copilot.types import Tool as CopilotTool

        @tool(approval_mode="never_require")
        def my_function(arg: str) -> str:
            """A function tool."""
            return arg

        async def tool_handler(invocation: Any) -> Any:
            return {"textResultForLlm": "result", "resultType": "success"}

        copilot_tool = CopilotTool(
            name="direct_tool",
            description="A direct CopilotTool",
            handler=tool_handler,
        )

        agent = GitHubCopilotAgent(client=mock_client)
        result = agent._prepare_tools([my_function, copilot_tool])  # type: ignore

        assert len(result) == 2
        # First tool is converted FunctionTool
        assert result[0].name == "my_function"
        # Second tool is CopilotTool passthrough
        assert result[1] == copilot_tool


class TestGitHubCopilotAgentErrorHandling:
    """Test cases for error handling."""

    async def test_start_raises_on_client_error(self, mock_client: MagicMock) -> None:
        """Test that start raises ServiceException when client fails to start."""
        mock_client.start.side_effect = Exception("Connection failed")

        agent = GitHubCopilotAgent(client=mock_client)

        with pytest.raises(ServiceException, match="Failed to start GitHub Copilot client"):
            await agent.start()

    async def test_run_raises_on_send_error(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that run raises ServiceException when send_and_wait fails."""
        mock_session.send_and_wait.side_effect = Exception("Request timeout")

        agent = GitHubCopilotAgent(client=mock_client)

        with pytest.raises(ServiceException, match="GitHub Copilot request failed"):
            await agent.run("Hello")

    async def test_get_or_create_session_raises_on_create_error(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that _get_or_create_session raises ServiceException when create_session fails."""
        mock_client.create_session.side_effect = Exception("Session creation failed")

        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        with pytest.raises(ServiceException, match="Failed to create GitHub Copilot session"):
            await agent._get_or_create_session(AgentThread())  # type: ignore

    async def test_get_or_create_session_raises_when_client_not_initialized(self) -> None:
        """Test that _get_or_create_session raises ServiceException when client is not initialized."""
        agent = GitHubCopilotAgent()
        # Don't call start() - client remains None

        with pytest.raises(ServiceException, match="GitHub Copilot client not initialized"):
            await agent._get_or_create_session(AgentThread())  # type: ignore


class TestGitHubCopilotAgentPermissions:
    """Test cases for permission handling."""

    def test_no_permission_handler_when_not_provided(self) -> None:
        """Test that no handler is set when on_permission_request is not provided."""
        agent = GitHubCopilotAgent()
        assert agent._permission_handler is None  # type: ignore

    def test_permission_handler_set_when_provided(self) -> None:
        """Test that a handler is set when on_permission_request is provided."""
        from copilot.types import PermissionRequest, PermissionRequestResult

        def approve_shell(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            if request.get("kind") == "shell":
                return PermissionRequestResult(kind="approved")
            return PermissionRequestResult(kind="denied-interactively-by-user")

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            default_options={"on_permission_request": approve_shell}
        )
        assert agent._permission_handler is not None  # type: ignore

    async def test_session_config_includes_permission_handler(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes permission handler when provided."""
        from copilot.types import PermissionRequest, PermissionRequestResult

        def approve_shell_read(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            if request.get("kind") in ("shell", "read"):
                return PermissionRequestResult(kind="approved")
            return PermissionRequestResult(kind="denied-interactively-by-user")

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"on_permission_request": approve_shell_read},
        )
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert "on_permission_request" in config
        assert config["on_permission_request"] is not None

    async def test_session_config_excludes_permission_handler_when_not_set(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config does not include permission handler when not set."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent._get_or_create_session(AgentThread())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert "on_permission_request" not in config

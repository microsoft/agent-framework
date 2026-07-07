# Copyright (c) Microsoft. All rights reserved.

# ruff: noqa: E402

import os
import unittest.mock
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

copilot = pytest.importorskip("copilot")

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    Content,
    ContextProvider,
    HistoryProvider,
    Message,
    tool,
)
from agent_framework.exceptions import AgentException
from copilot.session import PermissionHandler, PreToolUseHookInput
from copilot.session_events import (
    Data,
    SessionEvent,
    SessionEventType,
    ToolExecutionCompleteError,
    ToolExecutionCompleteResult,
)
from copilot.tools import ToolInvocation, ToolResult

from agent_framework_github_copilot import GitHubCopilotAgent, GitHubCopilotOptions


def copilot_options(options: GitHubCopilotOptions) -> GitHubCopilotOptions:
    """Return GitHub Copilot options with concrete TypedDict typing for tests."""
    return options


def pre_tool_use_input(tool_name: str) -> PreToolUseHookInput:
    """Build a complete PreToolUseHookInput for exercising on_pre_tool_use hooks in tests."""
    return {
        "sessionId": "test-session",
        "timestamp": datetime.now(timezone.utc),
        "workingDirectory": ".",
        "toolName": tool_name,
        "toolArgs": {},
    }


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
        agent = GitHubCopilotAgent(default_options=copilot_options({"model": "claude-sonnet-4", "timeout": 120}))
        assert agent._settings["model"] == "claude-sonnet-4"  # type: ignore
        assert agent._settings["timeout"] == 120  # type: ignore

    def test_init_with_tools(self) -> None:
        """Test initialization with function tools."""

        def my_tool(arg: str) -> str:
            return f"Result: {arg}"

        agent = GitHubCopilotAgent(tools=[my_tool])
        assert len(agent._tools) == 1  # type: ignore

    def test_init_with_instructions_parameter(self) -> None:
        """Test initialization with instructions parameter."""
        agent = GitHubCopilotAgent(instructions="You are a helpful assistant.")
        assert agent._default_options.get("system_message") == {  # type: ignore
            "mode": "append",
            "content": "You are a helpful assistant.",
        }

    def test_init_with_system_message_in_default_options(self) -> None:
        """Test initialization with system_message object in default_options."""
        agent = GitHubCopilotAgent(
            default_options=copilot_options({
                "system_message": {"mode": "append", "content": "You are a helpful assistant."}
            })
        )
        assert agent._default_options.get("system_message") == {  # type: ignore
            "mode": "append",
            "content": "You are a helpful assistant.",
        }

    def test_init_with_system_message_replace_mode(self) -> None:
        """Test initialization with system_message in replace mode."""
        agent = GitHubCopilotAgent(
            default_options=copilot_options({"system_message": {"mode": "replace", "content": "Custom system prompt."}})
        )
        assert agent._default_options.get("system_message") == {  # type: ignore
            "mode": "replace",
            "content": "Custom system prompt.",
        }

    def test_instructions_parameter_takes_precedence_for_content(self) -> None:
        """Test that direct instructions parameter takes precedence for content but preserves mode."""
        agent = GitHubCopilotAgent(
            instructions="Direct instructions",
            default_options=copilot_options({
                "system_message": {"mode": "replace", "content": "Options system_message"}
            }),
        )
        assert agent._default_options.get("system_message") == {  # type: ignore
            "mode": "replace",
            "content": "Direct instructions",
        }

    def test_instructions_parameter_defaults_to_append_mode(self) -> None:
        """Test that instructions parameter defaults to append mode when no system_message provided."""
        agent = GitHubCopilotAgent(instructions="Direct instructions")
        assert agent._default_options.get("system_message") == {  # type: ignore
            "mode": "append",
            "content": "Direct instructions",
        }

    def test_default_options_includes_model_for_telemetry(self) -> None:
        """Test that default_options merges model from settings for AgentTelemetryLayer span attributes."""
        agent = GitHubCopilotAgent(default_options=copilot_options({"model": "claude-sonnet-4-5", "timeout": 120}))
        opts = agent.default_options
        assert opts["model"] == "claude-sonnet-4-5"
        assert "timeout" not in opts  # timeout is extracted into _settings, not returned in default_options

    def test_default_options_without_model_configured(self) -> None:
        """Test that default_options works correctly when no model is configured."""
        agent = GitHubCopilotAgent(instructions="Helper")
        opts = agent.default_options
        assert "model" not in opts
        assert opts.get("system_message") == {"mode": "append", "content": "Helper"}

    def test_default_options_returns_independent_copy(self) -> None:
        """Test that mutating the returned dict does not affect internal state."""
        agent = GitHubCopilotAgent(default_options=copilot_options({"model": "gpt-5.1-mini"}))
        opts = agent.default_options
        opts["model"] = "mutated"
        assert agent._settings.get("model") == "gpt-5.1-mini"

    def test_init_stores_instruction_directories(self) -> None:
        """Test that instruction_directories are stored on the agent instance."""
        agent = GitHubCopilotAgent(default_options=copilot_options({"instruction_directories": ["/my/instructions"]}))
        assert agent._instruction_directories == ["/my/instructions"]  # type: ignore

    def test_init_without_instruction_directories(self) -> None:
        """Test that instruction_directories default to None when not provided."""
        agent = GitHubCopilotAgent()
        assert agent._instruction_directories is None  # type: ignore


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

            agent = GitHubCopilotAgent(
                default_options=copilot_options({"cli_path": "/custom/path", "log_level": "debug"})
            )
            await agent.start()

            kwargs = MockClient.call_args.kwargs
            assert kwargs["connection"].path == "/custom/path"
            assert kwargs["log_level"] == "debug"

    async def test_start_passes_base_directory_to_client(self) -> None:
        """Test that base_directory is passed through to CopilotClient."""
        with patch("agent_framework_github_copilot._agent.CopilotClient") as MockClient:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            MockClient.return_value = mock_client

            agent = GitHubCopilotAgent(default_options=copilot_options({"base_directory": "/custom/copilot/home"}))
            await agent.start()

            kwargs = MockClient.call_args.kwargs
            assert kwargs["base_directory"] == "/custom/copilot/home"

    async def test_start_base_directory_not_set_when_unspecified(self) -> None:
        """Test that base_directory is not included in client kwargs when not specified."""
        with patch("agent_framework_github_copilot._agent.CopilotClient") as MockClient:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            MockClient.return_value = mock_client

            agent = GitHubCopilotAgent()
            await agent.start()

            kwargs = MockClient.call_args.kwargs
            assert "base_directory" not in kwargs

    async def test_start_base_directory_from_env_variable(self) -> None:
        """Test that base_directory can be set via GITHUB_COPILOT_BASE_DIRECTORY env variable."""
        with (
            patch("agent_framework_github_copilot._agent.CopilotClient") as MockClient,
            patch.dict("os.environ", {"GITHUB_COPILOT_BASE_DIRECTORY": "/env/copilot/home"}),
        ):
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            MockClient.return_value = mock_client

            agent = GitHubCopilotAgent()
            await agent.start()

            kwargs = MockClient.call_args.kwargs
            assert kwargs["base_directory"] == "/env/copilot/home"


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
        assert response.messages[0].role == "assistant"
        assert response.messages[0].contents[0].text == "Test response"

    async def test_run_chat_message(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with Message."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        chat_message = Message(role="user", contents=[Content.from_text("Hello")])
        response = await agent.run(chat_message)

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1

    async def test_run_with_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with existing session."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        session = AgentSession()
        response = await agent.run("Hello", session=session)

        assert isinstance(response, AgentResponse)
        assert session.service_session_id == mock_session.session_id

    async def test_run_with_runtime_options(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with runtime options."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        response = await agent.run("Hello", options=cast(Any, {"timeout": 30}))

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


class TestGitHubCopilotAgentRunStreaming:
    """Test cases for run(stream=True) method."""

    async def test_run_streaming_basic(
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
        async for update in agent.run("Hello", stream=True):
            responses.append(update)

        assert len(responses) == 1
        assert isinstance(responses[0], AgentResponseUpdate)
        assert responses[0].role == "assistant"
        assert responses[0].contents[0].text == "Hello"

    async def test_run_streaming_with_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test streaming with existing session."""

        def mock_on(handler: Any) -> Any:
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        session = AgentSession()

        async for _ in agent.run("Hello", session=session, stream=True):
            pass

        assert session.service_session_id == mock_session.session_id

    async def test_run_streaming_error(
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

        with pytest.raises(AgentException, match="session error"):
            async for _ in agent.run("Hello", stream=True):
                pass

    async def test_run_streaming_auto_starts(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that run(stream=True) auto-starts the agent if not started."""

        def mock_on(handler: Any) -> Any:
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        assert agent._started is False  # type: ignore

        async for _ in agent.run("Hello", stream=True):
            pass

        assert agent._started is True  # type: ignore
        mock_client.start.assert_called_once()

    async def test_run_streaming_tool_execution_start(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that TOOL_EXECUTION_START events produce function_call content."""
        tool_event_data = MagicMock()
        tool_event_data.tool_call_id = "call_abc123"
        tool_event_data.tool_name = "get_weather"
        tool_event_data.arguments = {"city": "Seattle"}

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_START,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("What's the weather?", stream=True):
            responses.append(update)

        assert len(responses) == 1
        assert responses[0].role == "assistant"
        content = responses[0].contents[0]
        assert content.type == "function_call"
        assert content.call_id == "call_abc123"
        assert content.name == "get_weather"
        assert content.arguments == {"city": "Seattle"}
        assert content.raw_representation is tool_event_data

    async def test_run_streaming_tool_execution_complete(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that TOOL_EXECUTION_COMPLETE events produce function_result content."""
        tool_event_data = MagicMock()
        tool_event_data.tool_call_id = "call_abc123"
        tool_event_data.result = ToolExecutionCompleteResult(content="Sunny, 72°F")
        tool_event_data.success = True
        tool_event_data.error = None

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("What's the weather?", stream=True):
            responses.append(update)

        assert len(responses) == 1
        assert responses[0].role == "tool"
        content = responses[0].contents[0]
        assert content.type == "function_result"
        assert content.call_id == "call_abc123"
        assert content.result == "Sunny, 72°F"
        assert content.exception is None
        assert content.raw_representation is tool_event_data

    async def test_run_streaming_tool_execution_missing_fields(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that missing tool fields fall back to empty strings."""
        tool_event_data = MagicMock(spec=[])  # No attributes

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_START,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            responses.append(update)

        assert len(responses) == 1
        content = responses[0].contents[0]
        assert content.type == "function_call"
        assert content.call_id == ""
        assert content.name == ""
        assert content.arguments is None

    async def test_run_streaming_tool_result_none(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that a tool result with None result object produces empty string."""
        tool_event_data = MagicMock()
        tool_event_data.tool_call_id = "call_xyz"
        tool_event_data.result = None
        tool_event_data.success = True
        tool_event_data.error = None

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            responses.append(update)

        assert len(responses) == 1
        content = responses[0].contents[0]
        assert content.type == "function_result"
        assert content.call_id == "call_xyz"
        assert content.result == ""
        assert content.exception is None

    async def test_run_streaming_tool_execution_failure(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that a failed tool result surfaces the error as exception."""
        tool_event_data = MagicMock()
        tool_event_data.tool_call_id = "call_fail"
        tool_event_data.result = ToolExecutionCompleteResult(content="Error: connection timeout")
        tool_event_data.success = False
        tool_event_data.error = ToolExecutionCompleteError(message="connection timeout")

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            responses.append(update)

        assert len(responses) == 1
        content = responses[0].contents[0]
        assert content.type == "function_result"
        assert content.call_id == "call_fail"
        assert content.result == "Error: connection timeout"
        assert content.exception == "connection timeout"

    async def test_run_streaming_tool_execution_failure_string_error(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that a failed tool result with a string error is surfaced."""
        tool_event_data = MagicMock()
        tool_event_data.tool_call_id = "call_fail2"
        tool_event_data.result = ToolExecutionCompleteResult(content="")
        tool_event_data.success = False
        tool_event_data.error = "something went wrong"

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            responses.append(update)

        assert len(responses) == 1
        content = responses[0].contents[0]
        assert content.type == "function_result"
        assert content.call_id == "call_fail2"
        assert content.exception == "something went wrong"

    async def test_run_streaming_tool_execution_success_with_error_field(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that a successful tool result with error field does not propagate exception."""
        tool_event_data = MagicMock()
        tool_event_data.tool_call_id = "call_ok"
        tool_event_data.result = ToolExecutionCompleteResult(content="partial result")
        tool_event_data.success = True
        tool_event_data.error = "some warning"

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            responses.append(update)

        assert len(responses) == 1
        content = responses[0].contents[0]
        assert content.type == "function_result"
        assert content.call_id == "call_ok"
        assert content.result == "partial result"
        assert content.exception is None

    async def test_run_streaming_tool_complete_missing_fields(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that missing fields on TOOL_EXECUTION_COMPLETE fall back to defaults."""
        tool_event_data = MagicMock(spec=[])  # No attributes

        tool_event = SessionEvent(
            data=tool_event_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        )

        def mock_on(handler: Any) -> Any:
            handler(tool_event)
            handler(session_idle_event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            responses.append(update)

        assert len(responses) == 1
        content = responses[0].contents[0]
        assert content.type == "function_result"
        assert content.call_id == ""
        assert content.result == ""
        assert content.exception is None

    async def test_run_streaming_tool_call_and_result_sequence(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test a full streaming sequence: text delta, tool call, tool result, text delta."""
        # Tool call event
        call_data = MagicMock()
        call_data.tool_call_id = "call_001"
        call_data.tool_name = "search"
        call_data.arguments = {"query": "weather"}
        tool_call_event = SessionEvent(
            data=call_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_START,
        )

        # Tool result event
        result_data = MagicMock()
        result_data.tool_call_id = "call_001"
        result_data.result = ToolExecutionCompleteResult(content="72°F and sunny")
        result_data.success = True
        result_data.error = None
        tool_result_event = SessionEvent(
            data=result_data,
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        )

        # Final text delta
        final_delta = create_session_event(
            SessionEventType.ASSISTANT_MESSAGE_DELTA,
            delta_content="The weather is sunny.",
            message_id="msg-2",
        )

        events = [assistant_delta_event, tool_call_event, tool_result_event, final_delta, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on

        agent = GitHubCopilotAgent(client=mock_client)
        responses: list[AgentResponseUpdate] = []
        async for update in agent.run("What's the weather?", stream=True):
            responses.append(update)

        assert len(responses) == 4
        assert responses[0].role == "assistant"
        assert responses[0].contents[0].type == "text"
        assert responses[1].role == "assistant"
        assert responses[1].contents[0].type == "function_call"
        assert responses[2].role == "tool"
        assert responses[2].contents[0].type == "function_result"
        assert responses[3].role == "assistant"
        assert responses[3].contents[0].type == "text"


class TestGitHubCopilotAgentSessionManagement:
    """Test cases for session management."""

    async def test_session_resumed_for_same_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that subsequent calls on the same session resume the session."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GitHubCopilotAgent(client=mock_client)
        session = AgentSession()

        await agent.run("Hello", session=session)
        await agent.run("World", session=session)

        mock_client.create_session.assert_called_once()
        mock_client.resume_session.assert_called_once_with(
            mock_session.session_id,
            on_permission_request=unittest.mock.ANY,
            streaming=unittest.mock.ANY,
            model=unittest.mock.ANY,
            system_message=unittest.mock.ANY,
            tools=unittest.mock.ANY,
            mcp_servers=unittest.mock.ANY,
            provider=unittest.mock.ANY,
            instruction_directories=unittest.mock.ANY,
            hooks=unittest.mock.ANY,
        )

    async def test_session_config_includes_model(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes model setting."""
        agent = GitHubCopilotAgent(client=mock_client, default_options=copilot_options({"model": "claude-sonnet-4"}))
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["model"] == "claude-sonnet-4"

    async def test_session_config_includes_instructions(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes instructions from direct parameter."""
        agent = GitHubCopilotAgent(
            instructions="You are a helpful assistant.",
            client=mock_client,
        )
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["system_message"]["mode"] == "append"
        assert config["system_message"]["content"] == "You are a helpful assistant."

    async def test_runtime_options_take_precedence_over_default(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that runtime options from run() take precedence over default_options."""
        agent = GitHubCopilotAgent(
            instructions="Default instructions",
            client=mock_client,
        )
        await agent.start()

        runtime_options: dict[str, Any] = {"system_message": {"mode": "replace", "content": "Runtime instructions"}}
        await agent._get_or_create_session(  # type: ignore
            AgentSession(),
            runtime_options=runtime_options,
        )

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["system_message"]["mode"] == "replace"
        assert config["system_message"]["content"] == "Runtime instructions"

    async def test_session_config_includes_streaming_flag(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes the streaming flag."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent._get_or_create_session(AgentSession(), streaming=True)  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["streaming"] is True

    async def test_resume_session_with_existing_service_session_id(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session is resumed when session has a service_session_id."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        session = AgentSession()
        session.service_session_id = "existing-session-id"

        await agent._get_or_create_session(session)  # type: ignore

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
        from copilot.session import PermissionDecisionApproveOnce, PermissionRequestResult
        from copilot.session_events import PermissionRequest

        def my_handler(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            return PermissionDecisionApproveOnce()

        def my_tool(arg: str) -> str:
            """A test tool."""
            return arg

        agent = GitHubCopilotAgent(
            client=mock_client,
            tools=[my_tool],
            default_options=copilot_options({"on_permission_request": my_handler}),
        )
        await agent.start()

        session = AgentSession()
        session.service_session_id = "existing-session-id"

        await agent._get_or_create_session(session)  # type: ignore

        mock_client.resume_session.assert_called_once()
        call_args = mock_client.resume_session.call_args
        config = call_args.kwargs
        assert "tools" in config
        assert "on_permission_request" in config

    async def test_instruction_directories_passed_to_create_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that instruction_directories are passed through to create_session."""
        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"instruction_directories": ["/path/to/instructions", "/other/path"]}),
        )
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["instruction_directories"] == ["/path/to/instructions", "/other/path"]

    async def test_instruction_directories_runtime_override(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that runtime instruction_directories take precedence over defaults."""
        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"instruction_directories": ["/default/path"]}),
        )
        await agent.start()

        runtime_options: GitHubCopilotOptions = {"instruction_directories": ["/runtime/path"]}
        await agent._get_or_create_session(AgentSession(), runtime_options=runtime_options)  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["instruction_directories"] == ["/runtime/path"]

    async def test_instruction_directories_none_when_not_specified(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that instruction_directories is None when not specified."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["instruction_directories"] is None

    async def test_instruction_directories_empty_list_clears_defaults(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that an explicit empty list at runtime clears the agent-level defaults."""
        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"instruction_directories": ["/default/path"]}),
        )
        await agent.start()

        runtime_options: GitHubCopilotOptions = {"instruction_directories": []}
        await agent._get_or_create_session(AgentSession(), runtime_options=runtime_options)  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["instruction_directories"] == []

    async def test_instruction_directories_override_on_resumed_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that instruction_directories override works on resumed sessions."""
        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"instruction_directories": ["/default/path"]}),
        )
        await agent.start()

        # Simulate a session that already has a service_session_id (resume path)
        session = AgentSession()
        session.service_session_id = "existing-session-id"

        runtime_options: GitHubCopilotOptions = {"instruction_directories": ["/override/path"]}
        await agent._get_or_create_session(session, runtime_options=runtime_options)  # type: ignore

        call_args = mock_client.resume_session.call_args
        config = call_args.kwargs
        assert config["instruction_directories"] == ["/override/path"]


class TestGitHubCopilotAgentMCPServers:
    """Test cases for MCP server configuration."""

    async def test_mcp_servers_passed_to_create_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that mcp_servers are passed through to create_session config."""
        from copilot.session import MCPServerConfig

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

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"mcp_servers": mcp_servers}),
        )
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
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
        from copilot.session import MCPServerConfig

        mcp_servers: dict[str, MCPServerConfig] = {
            "test-server": {
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
                "tools": ["*"],
            },
        }

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"mcp_servers": mcp_servers}),
        )
        await agent.start()

        session = AgentSession()
        session.service_session_id = "existing-session-id"

        await agent._get_or_create_session(session)  # type: ignore

        mock_client.resume_session.assert_called_once()
        call_args = mock_client.resume_session.call_args
        config = call_args.kwargs
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

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["mcp_servers"] is None


class TestGitHubCopilotAgentProvider:
    """Test cases for provider configuration (BYOK / Managed Identity)."""

    async def test_provider_passed_to_create_session(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that provider config is passed through to create_session."""
        from copilot.session import ProviderConfig

        provider: ProviderConfig = {
            "type": "azure",
            "base_url": "https://my-resource.openai.azure.com",
            "bearer_token": "test-token",
        }

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"provider": provider}),
        )
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["provider"]["type"] == "azure"
        assert config["provider"]["base_url"] == "https://my-resource.openai.azure.com"
        assert config["provider"]["bearer_token"] == "test-token"

    async def test_provider_passed_to_resume_session(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that provider config is passed through to resume_session."""
        from copilot.session import ProviderConfig

        provider: ProviderConfig = {
            "type": "azure",
            "base_url": "https://my-resource.openai.azure.com",
            "bearer_token": "test-token",
        }

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"provider": provider}),
        )
        await agent.start()

        session = AgentSession()
        session.service_session_id = "existing-session-id"

        await agent._get_or_create_session(session)  # type: ignore

        mock_client.resume_session.assert_called_once()
        call_args = mock_client.resume_session.call_args
        config = call_args.kwargs
        assert config["provider"]["type"] == "azure"

    async def test_session_config_excludes_provider_when_not_set(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that provider is None in session config when not set."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["provider"] is None

    async def test_resume_session_excludes_provider_when_not_set(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that provider is None in resume session config when not set."""
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        session = AgentSession()
        session.service_session_id = "existing-session-id"

        await agent._get_or_create_session(session)  # type: ignore

        call_args = mock_client.resume_session.call_args
        config = call_args.kwargs
        assert config["provider"] is None

    async def test_runtime_provider_takes_precedence(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that runtime provider options override default_options provider."""
        from copilot.session import ProviderConfig

        default_provider: ProviderConfig = {
            "type": "azure",
            "base_url": "https://default.openai.azure.com",
            "bearer_token": "default-token",
        }
        runtime_provider: ProviderConfig = {
            "type": "openai",
            "base_url": "https://runtime.openai.com",
            "api_key": "runtime-key",
        }

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"provider": default_provider}),
        )
        await agent.start()

        await agent._get_or_create_session(  # type: ignore
            AgentSession(),
            runtime_options={"provider": runtime_provider},
        )

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["provider"]["type"] == "openai"
        assert config["provider"]["base_url"] == "https://runtime.openai.com"

    async def test_provider_not_leaked_into_default_options(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that provider is popped from opts and not left in _default_options."""
        from copilot.session import ProviderConfig

        provider: ProviderConfig = {
            "type": "azure",
            "base_url": "https://my-resource.openai.azure.com",
            "bearer_token": "test-token",
        }

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"provider": provider, "model": "gpt-5"}),
        )

        assert "provider" not in agent._default_options
        assert agent._provider is not None
        assert agent._provider["type"] == "azure"

    async def test_provider_coexists_with_other_options(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that provider works alongside model, tools, and mcp_servers."""
        from copilot.session import MCPServerConfig, ProviderConfig

        provider: ProviderConfig = {
            "type": "azure",
            "base_url": "https://my-resource.openai.azure.com",
            "bearer_token": "test-token",
        }
        mcp_servers: dict[str, MCPServerConfig] = {
            "test-server": {
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
                "tools": ["*"],
            },
        }

        def my_tool(arg: str) -> str:
            """A test tool."""
            return arg

        agent = GitHubCopilotAgent(
            client=mock_client,
            tools=[my_tool],
            default_options=copilot_options({
                "model": "gpt-5",
                "provider": provider,
                "mcp_servers": mcp_servers,
            }),
        )
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert config["provider"]["type"] == "azure"
        assert config["model"] == "gpt-5"
        assert config["mcp_servers"] is not None
        assert config["tools"] is not None


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

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
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

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        copilot_tool = config["tools"][0]

        result = await copilot_tool.handler(ToolInvocation(arguments={"arg": "test"}))

        assert isinstance(result, ToolResult)
        assert result.result_type == "success"
        assert result.text_result_for_llm == "Result: test"

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

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        copilot_tool = config["tools"][0]

        result = await copilot_tool.handler(ToolInvocation(arguments={"arg": "test"}))

        assert isinstance(result, ToolResult)
        assert result.result_type == "failure"
        assert "Something went wrong" in result.text_result_for_llm
        assert result.error is not None
        assert "Something went wrong" in result.error

    async def test_tool_handler_rejects_raw_dict_invocation(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that tool handler raises TypeError when called with a raw dict instead of ToolInvocation."""

        def my_tool(arg: str) -> str:
            """A test tool."""
            return f"Result: {arg}"

        agent = GitHubCopilotAgent(client=mock_client, tools=[my_tool])
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        copilot_tool = config["tools"][0]

        with pytest.raises((TypeError, AttributeError)):
            await copilot_tool.handler({"arguments": {"arg": "test"}})

    async def test_tool_handler_with_empty_arguments(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that tool handler handles ToolInvocation with empty arguments."""

        def no_args_tool() -> str:
            """A tool with no arguments."""
            return "no args result"

        agent = GitHubCopilotAgent(client=mock_client, tools=[no_args_tool])
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        copilot_tool = config["tools"][0]

        result = await copilot_tool.handler(ToolInvocation(arguments={}))

        assert isinstance(result, ToolResult)
        assert result.result_type == "success"
        assert result.text_result_for_llm == "no args result"

    def test_copilot_tool_passthrough(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that CopilotTool instances are passed through as-is."""
        from copilot.tools import Tool as CopilotTool

        async def tool_handler(invocation: Any) -> Any:
            return {"text_result_for_llm": "result", "result_type": "success"}

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
        from copilot.tools import Tool as CopilotTool

        @tool(approval_mode="never_require")
        def my_function(arg: str) -> str:
            """A function tool."""
            return arg

        async def tool_handler(invocation: Any) -> Any:
            return {"text_result_for_llm": "result", "result_type": "success"}

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


class TestGitHubCopilotAgentFunctionApproval:
    """Tests that ``approval_mode='always_require'`` is gated via the SDK ``on_pre_tool_use`` hook."""

    def test_default_hook_asks_for_approval_required_tool(
        self,
        mock_client: MagicMock,
    ) -> None:
        """The default hook returns 'ask' for always_require tools and defers others."""

        @tool(approval_mode="always_require")
        def dangerous(path: str) -> str:
            """A tool that requires human approval."""
            return f"deleted {path}"

        @tool
        def safe(x: int) -> str:
            """A tool that does not require approval."""
            return f"safe={x}"

        agent = GitHubCopilotAgent(client=mock_client)
        hooks = agent._build_session_hooks([dangerous, safe], {})  # type: ignore[reportPrivateUsage]

        assert hooks is not None
        hook = hooks["on_pre_tool_use"]

        approval_decision = hook(pre_tool_use_input("dangerous"), {"session_id": "s"})
        assert approval_decision == {
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "Tool 'dangerous' is marked as requiring approval (approval_mode='always_require')."
            ),
        }

        assert hook(pre_tool_use_input("safe"), {"session_id": "s"}) is None

    def test_no_hook_when_no_approval_required_tools(
        self,
        mock_client: MagicMock,
    ) -> None:
        """No approval-required tools and no user hook means no hooks are installed."""

        @tool
        def safe(x: int) -> str:
            """A tool that does not require approval."""
            return f"safe={x}"

        agent = GitHubCopilotAgent(client=mock_client)
        assert agent._build_session_hooks([safe], {}) is None  # type: ignore[reportPrivateUsage]

    def test_user_hook_takes_precedence_and_warns(
        self,
        mock_client: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A caller-supplied on_pre_tool_use takes precedence and triggers a warning."""

        def user_hook(_input: Any, _context: Any) -> Any:
            return {"permissionDecision": "allow"}

        @tool(approval_mode="always_require")
        def dangerous(path: str) -> str:
            """A tool that requires human approval."""
            return f"deleted {path}"

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"on_pre_tool_use": user_hook}),
        )

        with caplog.at_level("WARNING", logger="agent_framework.github_copilot"):
            hooks = agent._build_session_hooks([dangerous], {})  # type: ignore[reportPrivateUsage]

        assert hooks == {"on_pre_tool_use": user_hook}
        assert any("dangerous" in record.message and record.levelname == "WARNING" for record in caplog.records)

    def test_user_hook_no_warning_without_approval_tools(
        self,
        mock_client: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A caller hook with no approval-required tools is preserved without a warning."""

        def user_hook(_input: Any, _context: Any) -> Any:
            return None

        @tool
        def safe(x: int) -> str:
            """A tool that does not require approval."""
            return f"safe={x}"

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"on_pre_tool_use": user_hook}),
        )

        with caplog.at_level("WARNING", logger="agent_framework.github_copilot"):
            hooks = agent._build_session_hooks([safe], {})  # type: ignore[reportPrivateUsage]

        assert hooks == {"on_pre_tool_use": user_hook}
        assert not any(record.levelname == "WARNING" for record in caplog.records)

    def test_runtime_on_pre_tool_use_overrides_default_options(
        self,
        mock_client: MagicMock,
    ) -> None:
        """A per-run on_pre_tool_use option takes precedence over default_options."""

        def default_hook(_input: Any, _context: Any) -> Any:
            return None

        def runtime_hook(_input: Any, _context: Any) -> Any:
            return {"permissionDecision": "deny"}

        @tool(approval_mode="always_require")
        def dangerous(path: str) -> str:
            """A tool that requires human approval."""
            return f"deleted {path}"

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"on_pre_tool_use": default_hook}),
        )

        hooks = agent._build_session_hooks([dangerous], {"on_pre_tool_use": runtime_hook})  # type: ignore[reportPrivateUsage]
        assert hooks == {"on_pre_tool_use": runtime_hook}

    async def test_default_hook_forwarded_to_create_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """An always_require tool causes the default hook to be forwarded to the SDK session."""
        mock_session.send_and_wait.return_value = assistant_message_event

        @tool(approval_mode="always_require")
        def dangerous(path: str) -> str:
            """A tool that requires human approval."""
            return f"deleted {path}"

        agent = GitHubCopilotAgent(client=mock_client, tools=[dangerous])
        await agent.run("hello")

        hooks = mock_client.create_session.call_args.kwargs["hooks"]
        assert hooks is not None
        assert "on_pre_tool_use" in hooks


class TestGitHubCopilotAgentDeprecatedFunctionApproval:
    """Tests for the deprecated ``on_function_approval`` callback (still enforced)."""

    def test_setting_callback_emits_deprecation_warning(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Configuring on_function_approval emits a DeprecationWarning."""

        def approve(_call: Content) -> bool:
            return True

        with pytest.warns(DeprecationWarning, match="on_function_approval is deprecated"):
            GitHubCopilotAgent(
                client=mock_client,
                default_options=copilot_options({"on_function_approval": approve}),
            )

    async def test_handler_denies_when_callback_returns_false(
        self,
        mock_client: MagicMock,
    ) -> None:
        """A falsy callback return value denies the call and skips execution."""
        invocations: list[str] = []

        def deny(_call: Content) -> bool:
            return False

        @tool(approval_mode="always_require")
        def dangerous(path: str) -> str:
            """A tool that requires human approval."""
            invocations.append(path)
            return f"deleted {path}"

        with pytest.warns(DeprecationWarning):
            agent = GitHubCopilotAgent(
                client=mock_client,
                default_options=copilot_options({"on_function_approval": deny}),
            )
        copilot_tool = agent._tool_to_copilot_tool(dangerous)  # type: ignore[reportPrivateUsage]

        handler = cast("Any", copilot_tool.handler)
        result = await handler(ToolInvocation(arguments={"path": "/critical"}))

        assert invocations == []
        assert result.result_type == "failure"
        assert result.error == "approval_denied"

    async def test_handler_executes_when_callback_returns_true(
        self,
        mock_client: MagicMock,
    ) -> None:
        """A truthy callback return value allows the tool to execute."""

        def approve(_call: Content) -> bool:
            return True

        @tool(approval_mode="always_require")
        def guarded(x: int) -> str:
            """A tool that requires human approval."""
            return f"result={x}"

        with pytest.warns(DeprecationWarning):
            agent = GitHubCopilotAgent(
                client=mock_client,
                default_options=copilot_options({"on_function_approval": approve}),
            )
        copilot_tool = agent._tool_to_copilot_tool(guarded)  # type: ignore[reportPrivateUsage]

        handler = cast("Any", copilot_tool.handler)
        result = await handler(ToolInvocation(arguments={"x": 42}))

        assert result.result_type == "success"
        assert result.text_result_for_llm == "result=42"

    def test_default_hook_not_installed_when_callback_set(
        self,
        mock_client: MagicMock,
    ) -> None:
        """When on_function_approval is set, the default ask-hook is not installed."""

        def approve(_call: Content) -> bool:
            return True

        @tool(approval_mode="always_require")
        def dangerous(path: str) -> str:
            """A tool that requires human approval."""
            return f"deleted {path}"

        with pytest.warns(DeprecationWarning):
            agent = GitHubCopilotAgent(
                client=mock_client,
                default_options=copilot_options({"on_function_approval": approve}),
            )

        assert agent._build_session_hooks([dangerous], {}) is None  # type: ignore[reportPrivateUsage]

    def test_both_options_in_default_options_raises(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Setting both on_function_approval and on_pre_tool_use at construction raises."""

        def deny(_call: Content) -> bool:
            return False

        def hook(_input: Any, _context: Any) -> Any:
            return None

        with pytest.raises(ValueError, match="cannot both be set"):
            GitHubCopilotAgent(
                client=mock_client,
                default_options=copilot_options({"on_function_approval": deny, "on_pre_tool_use": hook}),
            )

    async def test_runtime_on_pre_tool_use_with_deprecated_callback_raises(
        self,
        mock_client: MagicMock,
    ) -> None:
        """A per-run on_pre_tool_use combined with a construction-time on_function_approval raises."""

        def deny(_call: Content) -> bool:
            return False

        def allow_hook(_input: Any, _context: Any) -> Any:
            return {"permissionDecision": "allow"}

        with pytest.warns(DeprecationWarning):
            agent = GitHubCopilotAgent(
                client=mock_client,
                default_options=copilot_options({"on_function_approval": deny}),
            )

        with pytest.raises(ValueError, match="cannot be combined with the deprecated on_function_approval"):
            await agent.run("hello", options=cast(Any, {"on_pre_tool_use": allow_hook}))

    async def test_runtime_on_pre_tool_use_with_deprecated_callback_raises_streaming(
        self,
        mock_client: MagicMock,
    ) -> None:
        """The mutual-exclusivity check also applies on the streaming path."""

        def deny(_call: Content) -> bool:
            return False

        def allow_hook(_input: Any, _context: Any) -> Any:
            return {"permissionDecision": "allow"}

        with pytest.warns(DeprecationWarning):
            agent = GitHubCopilotAgent(
                client=mock_client,
                default_options=copilot_options({"on_function_approval": deny}),
            )

        with pytest.raises(ValueError, match="cannot be combined with the deprecated on_function_approval"):
            async for _ in agent.run("hello", stream=True, options=cast(Any, {"on_pre_tool_use": allow_hook})):
                pass

    async def test_runtime_on_function_approval_rejected(self, mock_client: MagicMock) -> None:
        """Passing on_function_approval at runtime raises rather than being silently ignored."""
        agent = GitHubCopilotAgent(client=mock_client)
        with pytest.raises(ValueError, match="on_function_approval"):
            await agent.run("hello", options=cast(Any, {"on_function_approval": lambda _c: True}))

    async def test_runtime_on_function_approval_rejected_streaming(self, mock_client: MagicMock) -> None:
        """Passing on_function_approval at runtime raises on the streaming path too."""
        agent = GitHubCopilotAgent(client=mock_client)
        with pytest.raises(ValueError, match="on_function_approval"):
            async for _ in agent.run(
                "hello",
                stream=True,
                options=cast(Any, {"on_function_approval": lambda _c: True}),
            ):
                pass


class TestGitHubCopilotAgentErrorHandling:
    """Test cases for error handling."""

    async def test_start_raises_on_client_error(self, mock_client: MagicMock) -> None:
        """Test that start raises AgentException when client fails to start."""
        mock_client.start.side_effect = Exception("Connection failed")

        agent = GitHubCopilotAgent(client=mock_client)

        with pytest.raises(AgentException, match="Failed to start GitHub Copilot client"):
            await agent.start()

    async def test_run_raises_on_send_error(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that run raises AgentException when send_and_wait fails."""
        mock_session.send_and_wait.side_effect = Exception("Request timeout")

        agent = GitHubCopilotAgent(client=mock_client)

        with pytest.raises(AgentException, match="GitHub Copilot request failed"):
            await agent.run("Hello")

    async def test_get_or_create_session_raises_on_create_error(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that _get_or_create_session raises AgentException when create_session fails."""
        mock_client.create_session.side_effect = Exception("Session creation failed")

        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        with pytest.raises(AgentException, match="Failed to create GitHub Copilot session"):
            await agent._get_or_create_session(AgentSession())  # type: ignore

    async def test_get_or_create_session_raises_when_client_not_initialized(self) -> None:
        """Test that _get_or_create_session raises RuntimeError when client is not initialized."""
        agent = GitHubCopilotAgent()
        # Don't call start() - client remains None

        with pytest.raises(RuntimeError, match="GitHub Copilot client not initialized"):
            await agent._get_or_create_session(AgentSession())  # type: ignore


class TestGitHubCopilotAgentPermissions:
    """Test cases for permission handling."""

    def test_deny_all_permissions_returns_user_not_available(self) -> None:
        """Test that the default deny handler returns PermissionDecisionUserNotAvailable."""
        from copilot.generated.rpc import PermissionDecisionUserNotAvailable

        from agent_framework_github_copilot._agent import _deny_all_permissions

        result = _deny_all_permissions(MagicMock(), {})
        assert isinstance(result, PermissionDecisionUserNotAvailable)

    def test_no_permission_handler_when_not_provided(self) -> None:
        """Test that no handler is set when on_permission_request is not provided."""
        agent = GitHubCopilotAgent()
        assert agent._permission_handler is None  # type: ignore

    def test_permission_handler_set_when_provided(self) -> None:
        """Test that a handler is set when on_permission_request is provided."""
        from copilot.generated.rpc import PermissionDecisionDeniedInteractivelyByUser
        from copilot.session import PermissionDecisionApproveOnce, PermissionRequestResult
        from copilot.session_events import PermissionRequest

        def approve_shell(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            if request.kind == "shell":
                return PermissionDecisionApproveOnce()
            return PermissionDecisionDeniedInteractivelyByUser()

        agent = GitHubCopilotAgent(default_options=copilot_options({"on_permission_request": approve_shell}))
        assert agent._permission_handler is not None  # type: ignore

    async def test_session_config_includes_permission_handler(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes permission handler when provided."""
        from copilot.generated.rpc import PermissionDecisionDeniedInteractivelyByUser
        from copilot.session import PermissionDecisionApproveOnce, PermissionRequestResult
        from copilot.session_events import PermissionRequest

        def approve_shell_read(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            if request.kind in ("shell", "read"):
                return PermissionDecisionApproveOnce()
            return PermissionDecisionDeniedInteractivelyByUser()

        agent = GitHubCopilotAgent(
            client=mock_client,
            default_options=copilot_options({"on_permission_request": approve_shell_read}),
        )
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert "on_permission_request" in config
        assert config["on_permission_request"] is not None

    async def test_session_config_uses_deny_all_when_no_permission_handler_set(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config uses deny-all handler when no permission handler is set.

        In SDK 0.2.x, on_permission_request is required by create_session, so the agent
        always falls back to _deny_all_permissions when no handler is provided.
        """
        agent = GitHubCopilotAgent(client=mock_client)
        await agent.start()

        await agent._get_or_create_session(AgentSession())  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args.kwargs
        assert "on_permission_request" in config
        assert config["on_permission_request"] is not None


class SpyContextProvider(ContextProvider):
    """A context provider that records whether its hooks are called."""

    def __init__(self) -> None:
        super().__init__(source_id="spy-provider")
        self.before_run_called = False
        self.after_run_called = False
        self.before_run_context: Any = None
        self.after_run_context: Any = None

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        self.before_run_called = True
        self.before_run_context = context
        context.instructions.append("Injected by spy provider")

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        self.after_run_called = True
        self.after_run_context = context


class TestGitHubCopilotAgentContextProviders:
    """Test cases for context provider integration."""

    async def test_before_run_called_on_run(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that before_run is called on context providers during run()."""
        mock_session.send_and_wait.return_value = assistant_message_event
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        await agent.run("Hello", session=session)

        assert spy.before_run_called

    async def test_after_run_called_on_run(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that after_run is called on context providers after run()."""
        mock_session.send_and_wait.return_value = assistant_message_event
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        await agent.run("Hello", session=session)

        assert spy.after_run_called

    async def test_provider_instructions_included_in_prompt(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that instructions added by context providers are included in the prompt."""
        mock_session.send_and_wait.return_value = assistant_message_event
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        await agent.run("Hello", session=session)

        sent_prompt = mock_session.send_and_wait.call_args[0][0]
        assert "Injected by spy provider" in sent_prompt

    async def test_after_run_receives_response(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that after_run context contains the agent response."""
        mock_session.send_and_wait.return_value = assistant_message_event
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        await agent.run("Hello", session=session)

        assert spy.after_run_context is not None
        assert spy.after_run_context.response is not None

    async def test_before_run_called_on_streaming(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that before_run is called on context providers during streaming."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        assert spy.before_run_called

    async def test_after_run_called_on_streaming(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that after_run is called on context providers after streaming."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        assert spy.after_run_called

    async def test_provider_instructions_included_in_streaming_prompt(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that instructions from context providers are included in the streaming prompt."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        sent_prompt = mock_session.send.call_args[0][0]
        assert "Injected by spy provider" in sent_prompt

    async def test_context_preserved_across_runs(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that provider state is preserved across multiple runs with the same session."""
        mock_session.send_and_wait.return_value = assistant_message_event
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()

        await agent.run("Hello", session=session)
        assert spy.before_run_called

        spy.before_run_called = False
        await agent.run("Hello again", session=session)
        assert spy.before_run_called

    async def test_context_messages_included_in_prompt(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that context messages added by providers via extend_messages are included in the prompt."""
        mock_session.send_and_wait.return_value = assistant_message_event

        class MessageInjectingProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="msg-injector")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                context.extend_messages(self, [Message(role="user", contents=[Content.from_text("History message")])])

            async def after_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                pass

        provider = MessageInjectingProvider()
        agent = GitHubCopilotAgent(client=mock_client, context_providers=[provider])
        session = agent.create_session()
        await agent.run("Hello", session=session)

        sent_prompt = mock_session.send_and_wait.call_args[0][0]
        assert "History message" in sent_prompt
        assert "Hello" in sent_prompt

    async def test_context_messages_included_in_streaming_prompt(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that context messages added by providers are included in the streaming prompt."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on

        class MessageInjectingProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="msg-injector")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                context.extend_messages(self, [Message(role="user", contents=[Content.from_text("History message")])])

            async def after_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                pass

        provider = MessageInjectingProvider()
        agent = GitHubCopilotAgent(client=mock_client, context_providers=[provider])
        session = agent.create_session()
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        sent_prompt = mock_session.send.call_args[0][0]
        assert "History message" in sent_prompt
        assert "Hello" in sent_prompt

    async def test_after_run_not_called_on_error(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that after_run is NOT called when send_and_wait raises."""
        mock_session.send_and_wait.side_effect = Exception("Request failed")
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        with pytest.raises(AgentException):
            await agent.run("Hello", session=session)

        assert spy.before_run_called
        assert not spy.after_run_called

    async def test_after_run_not_called_on_streaming_error(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_error_event: SessionEvent,
    ) -> None:
        """Test that after_run is NOT called when streaming encounters an error."""
        events = [session_error_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        with pytest.raises(AgentException):
            async for _ in agent.run("Hello", stream=True, session=session):
                pass

        assert spy.before_run_called
        assert not spy.after_run_called

    async def test_multiple_providers_ordering(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that before_run is called in forward order and after_run in reverse order."""
        mock_session.send_and_wait.return_value = assistant_message_event
        call_order: list[str] = []

        class OrderedProvider(ContextProvider):
            def __init__(self, name: str) -> None:
                super().__init__(source_id=name)
                self.name = name

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                call_order.append(f"before:{self.name}")

            async def after_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                call_order.append(f"after:{self.name}")

        providers = [OrderedProvider("A"), OrderedProvider("B"), OrderedProvider("C")]
        agent = GitHubCopilotAgent(client=mock_client, context_providers=providers)
        session = agent.create_session()
        await agent.run("Hello", session=session)

        assert call_order == ["before:A", "before:B", "before:C", "after:C", "after:B", "after:A"]

    async def test_history_provider_skip_when_load_messages_false(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that HistoryProvider with load_messages=False is skipped in before_run."""
        mock_session.send_and_wait.return_value = assistant_message_event

        class StubHistoryProvider(HistoryProvider):
            def __init__(self, *, load_messages: bool = True) -> None:
                super().__init__(source_id="stub-history", load_messages=load_messages)
                self.before_run_called = False

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                self.before_run_called = True

            async def after_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                self.after_run_called = True

            async def get_messages(
                self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
            ) -> list[Message]:
                return []

            async def save_messages(
                self,
                session_id: str | None,
                messages: Sequence[Message],
                *,
                state: dict[str, Any] | None = None,
                **kwargs: Any,
            ) -> None:
                pass

        skipped_provider = StubHistoryProvider(load_messages=False)
        active_provider = StubHistoryProvider(load_messages=True)
        # Use unique source_ids
        object.__setattr__(skipped_provider, "_source_id", "skipped-history")
        object.__setattr__(active_provider, "_source_id", "active-history")

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[skipped_provider, active_provider])
        session = agent.create_session()
        await agent.run("Hello", session=session)

        assert not skipped_provider.before_run_called
        assert active_provider.before_run_called
        # after_run should still be called even when load_messages=False
        assert skipped_provider.after_run_called
        assert active_provider.after_run_called

    async def test_streaming_after_run_response_has_updates(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that streaming after_run context.response contains the aggregated updates."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        assert spy.after_run_context is not None
        assert spy.after_run_context.response is not None
        assert len(spy.after_run_context.response.messages) > 0
        assert spy.after_run_context.response.messages[0].text == "Hello"

    async def test_streaming_after_run_sets_empty_response_on_no_updates(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that streaming after_run sets an empty response when no updates are yielded."""
        events = [session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on
        spy = SpyContextProvider()

        agent = GitHubCopilotAgent(client=mock_client, context_providers=[spy])
        session = agent.create_session()
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        assert spy.after_run_called
        assert spy.after_run_context.response is not None
        assert len(spy.after_run_context.response.messages) == 0

    async def test_timeout_preserved_in_session_context_options(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that timeout is preserved in session context options for providers."""
        mock_session.send_and_wait.return_value = assistant_message_event
        observed_options: dict[str, Any] = {}

        class OptionsObserverProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="options-observer")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                observed_options.update(context.options)

            async def after_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                pass

        provider = OptionsObserverProvider()
        agent = GitHubCopilotAgent(client=mock_client, context_providers=[provider])
        session = agent.create_session()
        await agent.run("Hello", session=session, options=cast(Any, {"timeout": 120}))

        assert observed_options.get("timeout") == 120

    async def test_runtime_on_pre_tool_use_forwarded(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Passing on_pre_tool_use at runtime is accepted and forwarded to the session."""
        mock_session.send_and_wait.return_value = assistant_message_event

        def runtime_hook(_input: Any, _context: Any) -> Any:
            return {"permissionDecision": "deny"}

        agent = GitHubCopilotAgent(client=mock_client)
        await agent.run("hello", options=cast(Any, {"on_pre_tool_use": runtime_hook}))

        hooks = mock_client.create_session.call_args.kwargs["hooks"]
        assert hooks == {"on_pre_tool_use": runtime_hook}

    async def test_runtime_on_pre_tool_use_forwarded_streaming(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Passing on_pre_tool_use at runtime is accepted on the streaming path too."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on

        def runtime_hook(_input: Any, _context: Any) -> Any:
            return {"permissionDecision": "deny"}

        agent = GitHubCopilotAgent(client=mock_client)
        async for _ in agent.run(
            "hello",
            stream=True,
            options=cast(Any, {"on_pre_tool_use": runtime_hook}),
        ):
            pass

        hooks = mock_client.create_session.call_args.kwargs["hooks"]
        assert hooks == {"on_pre_tool_use": runtime_hook}

    async def test_provider_tools_forwarded_to_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that tools added by context providers are forwarded to session creation."""
        mock_session.send_and_wait.return_value = assistant_message_event

        class ToolInjectingProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="tool-injector")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                from agent_framework._tools import normalize_tools

                def load_skill(skill_name: str) -> str:
                    """Load a skill by name."""
                    return f"Loaded: {skill_name}"

                context.extend_tools(self.source_id, normalize_tools([load_skill]))

        provider = ToolInjectingProvider()
        agent = GitHubCopilotAgent(client=mock_client, context_providers=[provider])
        session = agent.create_session()
        await agent.run("Hello", session=session)

        call_kwargs = mock_client.create_session.call_args.kwargs
        assert call_kwargs.get("tools") is not None
        tool_names = [t.name for t in call_kwargs["tools"]]
        assert "load_skill" in tool_names

    async def test_provider_tools_merged_with_constructor_tools(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that provider tools are merged with constructor tools, not replacing them."""
        mock_session.send_and_wait.return_value = assistant_message_event

        def my_tool(x: str) -> str:
            """A constructor tool."""
            return x

        class ToolInjectingProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="tool-injector")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                from agent_framework._tools import normalize_tools

                def load_skill(skill_name: str) -> str:
                    """Load a skill by name."""
                    return f"Loaded: {skill_name}"

                context.extend_tools(self.source_id, normalize_tools([load_skill]))

        provider = ToolInjectingProvider()
        agent = GitHubCopilotAgent(
            client=mock_client,
            tools=[my_tool],
            context_providers=[provider],
        )
        session = agent.create_session()
        await agent.run("Hello", session=session)

        call_kwargs = mock_client.create_session.call_args.kwargs
        assert call_kwargs.get("tools") is not None
        tool_names = [t.name for t in call_kwargs["tools"]]
        assert "my_tool" in tool_names
        assert "load_skill" in tool_names

    async def test_provider_tools_forwarded_in_streaming(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that provider tools are forwarded in the streaming path."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on

        class ToolInjectingProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="tool-injector")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                from agent_framework._tools import normalize_tools

                def load_skill(skill_name: str) -> str:
                    """Load a skill by name."""
                    return f"Loaded: {skill_name}"

                context.extend_tools(self.source_id, normalize_tools([load_skill]))

        provider = ToolInjectingProvider()
        agent = GitHubCopilotAgent(client=mock_client, context_providers=[provider])
        session = agent.create_session()
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        call_kwargs = mock_client.create_session.call_args.kwargs
        assert call_kwargs.get("tools") is not None
        tool_names = [t.name for t in call_kwargs["tools"]]
        assert "load_skill" in tool_names

    async def test_provider_tools_forwarded_to_resume_session(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that provider tools are forwarded when resuming an existing session."""
        mock_session.send_and_wait.return_value = assistant_message_event

        class ToolInjectingProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="tool-injector")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                from agent_framework._tools import normalize_tools

                def load_skill(skill_name: str) -> str:
                    """Load a skill by name."""
                    return f"Loaded: {skill_name}"

                context.extend_tools(self.source_id, normalize_tools([load_skill]))

        provider = ToolInjectingProvider()
        agent = GitHubCopilotAgent(client=mock_client, context_providers=[provider])
        session = agent.create_session()
        session.service_session_id = "existing-id"
        await agent.run("Hello", session=session)

        mock_client.create_session.assert_not_called()
        mock_client.resume_session.assert_called_once()
        call_kwargs = mock_client.resume_session.call_args.kwargs
        assert call_kwargs.get("tools") is not None
        tool_names = [t.name for t in call_kwargs["tools"]]
        assert "load_skill" in tool_names

    async def test_provider_tools_forwarded_to_resume_session_streaming(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_delta_event: SessionEvent,
        session_idle_event: SessionEvent,
    ) -> None:
        """Test that provider tools are forwarded when resuming an existing session in streaming mode."""
        events = [assistant_delta_event, session_idle_event]

        def mock_on(handler: Any) -> Any:
            for event in events:
                handler(event)
            return lambda: None

        mock_session.on = mock_on

        class ToolInjectingProvider(ContextProvider):
            def __init__(self) -> None:
                super().__init__(source_id="tool-injector")

            async def before_run(
                self,
                *,
                agent: Any,
                session: AgentSession,
                context: Any,
                state: dict[str, Any],
            ) -> None:
                from agent_framework._tools import normalize_tools

                def load_skill(skill_name: str) -> str:
                    """Load a skill by name."""
                    return f"Loaded: {skill_name}"

                context.extend_tools(self.source_id, normalize_tools([load_skill]))

        provider = ToolInjectingProvider()
        agent = GitHubCopilotAgent(client=mock_client, context_providers=[provider])
        session = agent.create_session()
        session.service_session_id = "existing-id"
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        mock_client.create_session.assert_not_called()
        mock_client.resume_session.assert_called_once()
        call_kwargs = mock_client.resume_session.call_args.kwargs
        assert call_kwargs.get("tools") is not None
        tool_names = [t.name for t in call_kwargs["tools"]]
        assert "load_skill" in tool_names


# ---------------------------------------------------------------------------
# Integration tests — require COPILOT_GITHUB_TOKEN env var
# ---------------------------------------------------------------------------

skip_if_copilot_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("COPILOT_GITHUB_TOKEN", "") == "",
    reason="No COPILOT_GITHUB_TOKEN provided; skipping integration tests.",
)


@tool(approval_mode="never_require")
def get_weather(location: str) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25C."


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_copilot_integration_tests_disabled
async def test_integration_run_with_simple_prompt_returns_response() -> None:
    """Integration test: basic non-streaming response."""
    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant. Keep your answers short.",
        default_options=copilot_options({"on_permission_request": PermissionHandler.approve_all}),
    )

    async with agent:
        session = agent.create_session()
        response = await agent.run("What is 2 + 2? Answer with just the number.", session=session)

        assert response is not None
        assert len(response.messages) > 0
        assert "4" in response.text

        if isinstance(session.service_session_id, str) and agent._client:
            await agent._client.delete_session(session.service_session_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_copilot_integration_tests_disabled
async def test_integration_run_streaming_returns_updates() -> None:
    """Integration test: streaming response yields updates."""
    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant. Keep your answers short.",
        default_options=copilot_options({"on_permission_request": PermissionHandler.approve_all}),
    )

    async with agent:
        session = agent.create_session()
        updates = []
        async for chunk in agent.run("Count from 1 to 5.", stream=True, session=session):
            updates.append(chunk)

        assert len(updates) > 0
        full_text = "".join(u.text for u in updates if u.text)
        assert len(full_text) > 0

        if isinstance(session.service_session_id, str) and agent._client:
            await agent._client.delete_session(session.service_session_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_copilot_integration_tests_disabled
async def test_integration_run_with_function_tool_invokes_tool() -> None:
    """Integration test: function tool is invoked by the agent."""
    agent = GitHubCopilotAgent(
        instructions="You are a helpful weather agent. Use the get_weather tool to answer weather questions.",
        tools=[get_weather],
        default_options=copilot_options({"on_permission_request": PermissionHandler.approve_all}),
    )

    async with agent:
        session = agent.create_session()
        response = await agent.run("What's the weather like in Seattle?", session=session)

        assert response is not None
        assert len(response.messages) > 0
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather", "seattle"])

        if isinstance(session.service_session_id, str) and agent._client:
            await agent._client.delete_session(session.service_session_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_copilot_integration_tests_disabled
async def test_integration_run_with_session_maintains_context() -> None:
    """Integration test: session maintains conversation context across turns."""
    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant. Keep your answers short.",
        default_options=copilot_options({"on_permission_request": PermissionHandler.approve_all}),
    )

    async with agent:
        session = agent.create_session()

        response1 = await agent.run("My name is Alice.", session=session)
        assert response1 is not None

        response2 = await agent.run("What is my name?", session=session)

        assert response2 is not None
        assert "alice" in response2.text.lower()

        if isinstance(session.service_session_id, str) and agent._client:
            await agent._client.delete_session(session.service_session_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_copilot_integration_tests_disabled
async def test_integration_run_with_session_resume_continues_conversation() -> None:
    """Integration test: session can be resumed by ID."""
    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant. Keep your answers short.",
        default_options=copilot_options({"on_permission_request": PermissionHandler.approve_all}),
    )

    async with agent:
        session1 = agent.create_session()
        await agent.run("Remember this number: 42.", session=session1)

        session_id = session1.service_session_id
        assert isinstance(session_id, str)

        session2 = AgentSession()
        session2.service_session_id = session_id

        response = await agent.run("What number did I ask you to remember?", session=session2)

        assert response is not None
        assert "42" in response.text

        if agent._client:
            await agent._client.delete_session(session_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_copilot_integration_tests_disabled
async def test_integration_run_with_shell_permissions_executes_command() -> None:
    """Integration test: shell commands can be executed with permission handler."""
    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant that can execute shell commands.",
        default_options=copilot_options({"on_permission_request": PermissionHandler.approve_all}),
    )

    async with agent:
        session = agent.create_session()
        response = await agent.run("Run a shell command to print 'hello world'", session=session)

        assert response is not None
        assert "hello" in response.text.lower()

        if isinstance(session.service_session_id, str) and agent._client:
            await agent._client.delete_session(session.service_session_id)

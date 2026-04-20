# Copyright (c) Microsoft. All rights reserved.

# ruff: noqa: E402

import unittest.mock
from datetime import datetime, timezone
from typing import Any
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
)
from agent_framework.exceptions import AgentException
from copilot.generated.session_events import Data, ErrorClass, Result, SessionEvent, SessionEventType
from copilot.tools import ToolInvocation, ToolResult

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
        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            default_options={"system_message": {"mode": "append", "content": "You are a helpful assistant."}}
        )
        assert agent._default_options.get("system_message") == {  # type: ignore
            "mode": "append",
            "content": "You are a helpful assistant.",
        }

    def test_init_with_system_message_replace_mode(self) -> None:
        """Test initialization with system_message in replace mode."""
        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            default_options={"system_message": {"mode": "replace", "content": "Custom system prompt."}}
        )
        assert agent._default_options.get("system_message") == {  # type: ignore
            "mode": "replace",
            "content": "Custom system prompt.",
        }

    def test_instructions_parameter_takes_precedence_for_content(self) -> None:
        """Test that direct instructions parameter takes precedence for content but preserves mode."""
        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            instructions="Direct instructions",
            default_options={"system_message": {"mode": "replace", "content": "Options system_message"}},
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
            assert call_args.cli_path == "/custom/path"
            assert call_args.log_level == "debug"


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
        tool_event_data.result = Result(content="Sunny, 72°F")
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
        tool_event_data.result = Result(content="Error: connection timeout")
        tool_event_data.success = False
        tool_event_data.error = ErrorClass(message="connection timeout")

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
        tool_event_data.result = Result(content="")
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
        tool_event_data.result = Result(content="partial result")
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
        result_data.result = Result(content="72°F and sunny")
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
            tools=unittest.mock.ANY,
            mcp_servers=unittest.mock.ANY,
            provider=unittest.mock.ANY,
        )

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

        runtime_options: GitHubCopilotOptions = {
            "system_message": {"mode": "replace", "content": "Runtime instructions"}
        }
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
        from copilot.generated.session_events import PermissionRequest
        from copilot.session import PermissionRequestResult

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

        session = AgentSession()
        session.service_session_id = "existing-session-id"

        await agent._get_or_create_session(session)  # type: ignore

        mock_client.resume_session.assert_called_once()
        call_args = mock_client.resume_session.call_args
        config = call_args.kwargs
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

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"mcp_servers": mcp_servers},
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

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"mcp_servers": mcp_servers},
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

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"provider": provider},
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

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"provider": provider},
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

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"provider": default_provider},
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

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"provider": provider, "model": "gpt-5"},
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

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            tools=[my_tool],
            default_options={
                "model": "gpt-5",
                "provider": provider,
                "mcp_servers": mcp_servers,
            },
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

    def test_no_permission_handler_when_not_provided(self) -> None:
        """Test that no handler is set when on_permission_request is not provided."""
        agent = GitHubCopilotAgent()
        assert agent._permission_handler is None  # type: ignore

    def test_permission_handler_set_when_provided(self) -> None:
        """Test that a handler is set when on_permission_request is provided."""
        from copilot.generated.session_events import PermissionRequest
        from copilot.session import PermissionRequestResult

        def approve_shell(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            if request.kind == "shell":
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
        from copilot.generated.session_events import PermissionRequest
        from copilot.session import PermissionRequestResult

        def approve_shell_read(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
            if request.kind in ("shell", "read"):
                return PermissionRequestResult(kind="approved")
            return PermissionRequestResult(kind="denied-interactively-by-user")

        agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
            client=mock_client,
            default_options={"on_permission_request": approve_shell_read},
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

            async def get_messages(self, *, session_id: str, **kwargs: Any) -> list[Message]:
                return []

            async def save_messages(self, *, session_id: str, messages: list[Message], **kwargs: Any) -> None:
                pass

        skipped_provider = StubHistoryProvider(load_messages=False)
        active_provider = StubHistoryProvider(load_messages=True)
        # Use unique source_ids
        skipped_provider._source_id = "skipped-history"
        active_provider._source_id = "active-history"

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
        await agent.run("Hello", session=session, options={"timeout": 120})

        assert observed_options.get("timeout") == 120

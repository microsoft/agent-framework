# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, AgentThread, ChatMessage, Content, Role
from agent_framework.exceptions import ServiceException
from copilot.generated.session_events import Data, SessionEvent, SessionEventType

from agent_framework_github_copilot import GithubCopilotAgent, GithubCopilotOptions


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


class TestGithubCopilotAgentInit:
    """Test cases for GithubCopilotAgent initialization."""

    def test_init_with_client(self, mock_client: MagicMock) -> None:
        """Test initialization with pre-configured client."""
        agent = GithubCopilotAgent(client=mock_client)
        assert agent._client == mock_client  # type: ignore
        assert agent._owns_client is False  # type: ignore
        assert agent.id is not None

    def test_init_without_client(self) -> None:
        """Test initialization without client creates settings."""
        agent = GithubCopilotAgent()
        assert agent._client is None  # type: ignore
        assert agent._owns_client is True  # type: ignore
        assert agent._settings is not None  # type: ignore

    def test_init_with_default_options(self) -> None:
        """Test initialization with default_options parameter."""
        agent: GithubCopilotAgent[GithubCopilotOptions] = GithubCopilotAgent(
            default_options={"model": "claude-sonnet-4", "timeout": 120}
        )
        assert agent._settings.model == "claude-sonnet-4"  # type: ignore
        assert agent._settings.timeout == 120  # type: ignore

    def test_init_with_tools(self) -> None:
        """Test initialization with function tools."""

        def my_tool(arg: str) -> str:
            return f"Result: {arg}"

        agent = GithubCopilotAgent(tools=[my_tool])
        assert len(agent._tools) == 1  # type: ignore

    def test_init_with_instructions(self) -> None:
        """Test initialization with custom instructions."""
        agent = GithubCopilotAgent(instructions="You are a helpful assistant.")
        assert agent._instructions == "You are a helpful assistant."  # type: ignore


class TestGithubCopilotAgentLifecycle:
    """Test cases for agent lifecycle management."""

    async def test_start_creates_client(self) -> None:
        """Test that start creates a client if none provided."""
        with patch("agent_framework_github_copilot._agent.CopilotClient") as MockClient:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            MockClient.return_value = mock_client

            agent = GithubCopilotAgent()
            await agent.start()

            MockClient.assert_called_once()
            mock_client.start.assert_called_once()
            assert agent._started is True  # type: ignore

    async def test_start_uses_existing_client(self, mock_client: MagicMock) -> None:
        """Test that start uses provided client."""
        agent = GithubCopilotAgent(client=mock_client)
        await agent.start()

        mock_client.start.assert_called_once()
        assert agent._started is True  # type: ignore

    async def test_start_idempotent(self, mock_client: MagicMock) -> None:
        """Test that calling start multiple times is safe."""
        agent = GithubCopilotAgent(client=mock_client)
        await agent.start()
        await agent.start()

        mock_client.start.assert_called_once()

    async def test_stop_cleans_up(self, mock_client: MagicMock, mock_session: MagicMock) -> None:
        """Test that stop cleans up sessions and client."""
        agent = GithubCopilotAgent(client=mock_client)
        await agent.start()

        mock_client.create_session.return_value = mock_session
        await agent._get_or_create_session(AgentThread(), [])  # type: ignore

        await agent.stop()

        mock_session.destroy.assert_called_once()
        assert agent._started is False  # type: ignore

    async def test_context_manager(self, mock_client: MagicMock) -> None:
        """Test async context manager usage."""
        async with GithubCopilotAgent(client=mock_client) as agent:
            assert agent._started is True  # type: ignore

        # When client is provided externally, agent doesn't own it and won't stop it
        mock_client.stop.assert_not_called()
        assert agent._started is False  # type: ignore


class TestGithubCopilotAgentRun:
    """Test cases for run method."""

    async def test_run_string_message(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test run method with string message."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GithubCopilotAgent(client=mock_client)
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

        agent = GithubCopilotAgent(client=mock_client)
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

        agent = GithubCopilotAgent(client=mock_client)
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

        agent = GithubCopilotAgent(client=mock_client)
        response = await agent.run("Hello", options={"timeout": 30})

        assert isinstance(response, AgentResponse)

    async def test_run_empty_response(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test run method with no response event."""
        mock_session.send_and_wait.return_value = None

        agent = GithubCopilotAgent(client=mock_client)
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

        agent = GithubCopilotAgent(client=mock_client)
        assert agent._started is False  # type: ignore

        await agent.run("Hello")

        assert agent._started is True  # type: ignore
        mock_client.start.assert_called_once()


class TestGithubCopilotAgentRunStream:
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

        agent = GithubCopilotAgent(client=mock_client)
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

        agent = GithubCopilotAgent(client=mock_client)
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

        agent = GithubCopilotAgent(client=mock_client)

        with pytest.raises(ServiceException, match="session error"):
            async for _ in agent.run_stream("Hello"):
                pass


class TestGithubCopilotAgentSessionManagement:
    """Test cases for session management."""

    async def test_session_reuse(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that sessions are reused for the same thread."""
        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GithubCopilotAgent(client=mock_client)
        thread = AgentThread()

        await agent.run("Hello", thread=thread)
        await agent.run("World", thread=thread)

        mock_client.create_session.assert_called_once()

    async def test_session_config_includes_model(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes model setting."""
        agent: GithubCopilotAgent[GithubCopilotOptions] = GithubCopilotAgent(
            client=mock_client, default_options={"model": "claude-sonnet-4"}
        )
        await agent.start()

        await agent._get_or_create_session(AgentThread(), [])  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert config["model"] == "claude-sonnet-4"

    async def test_session_config_includes_instructions(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Test that session config includes instructions."""
        agent = GithubCopilotAgent(client=mock_client, instructions="You are a helpful assistant.")
        await agent.start()

        await agent._get_or_create_session(AgentThread(), [])  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert config["system_message"]["mode"] == "append"
        assert config["system_message"]["content"] == "You are a helpful assistant."


class TestGithubCopilotAgentToolConversion:
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

        agent = GithubCopilotAgent(client=mock_client, tools=[my_tool])
        await agent.start()

        await agent._get_or_create_session(AgentThread(), agent._tools)  # type: ignore

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert "tools" in config
        assert len(config["tools"]) == 1
        assert config["tools"][0].name == "my_tool"
        assert config["tools"][0].description == "A test tool."

    async def test_runtime_tools_merged(
        self,
        mock_client: MagicMock,
        mock_session: MagicMock,
        assistant_message_event: SessionEvent,
    ) -> None:
        """Test that runtime tools are merged with agent tools."""

        def agent_tool(x: str) -> str:
            """Agent tool."""
            return x

        def runtime_tool(y: str) -> str:
            """Runtime tool."""
            return y

        mock_session.send_and_wait.return_value = assistant_message_event

        agent = GithubCopilotAgent(client=mock_client, tools=[agent_tool])
        await agent.run("Hello", tools=[runtime_tool])

        call_args = mock_client.create_session.call_args
        config = call_args[0][0]
        assert "tools" in config
        assert len(config["tools"]) == 2

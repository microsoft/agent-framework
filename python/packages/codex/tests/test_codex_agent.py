# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import AgentResponseUpdate, AgentSession, Content, Message, tool
from agent_framework._settings import load_settings

from agent_framework_codex import CodexAgent, CodexAgentOptions, CodexAgentSettings

# region Test CodexAgentSettings


class TestCodexAgentSettings:
    """Tests for CodexAgentSettings."""

    def test_default_values(self) -> None:
        """Test default values are None."""
        settings = load_settings(CodexAgentSettings, env_prefix="CODEX_AGENT_")
        assert settings["codex_path"] is None
        assert settings["model"] is None
        assert settings["cwd"] is None
        assert settings["approval_policy"] is None

    def test_explicit_values(self) -> None:
        """Test explicit values override defaults."""
        settings = load_settings(
            CodexAgentSettings,
            env_prefix="CODEX_AGENT_",
            codex_path="/usr/local/bin/codex",
            model="codex-mini-latest",
            cwd="/home/user/project",
            approval_policy="full-auto",
        )
        assert settings["codex_path"] == "/usr/local/bin/codex"
        assert settings["model"] == "codex-mini-latest"
        assert settings["cwd"] == "/home/user/project"
        assert settings["approval_policy"] == "full-auto"

    def test_env_variable_loading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading from environment variables."""
        monkeypatch.setenv("CODEX_AGENT_MODEL", "gpt-5.1-codex")
        settings = load_settings(CodexAgentSettings, env_prefix="CODEX_AGENT_")
        assert settings["model"] == "gpt-5.1-codex"


# region Test CodexAgent Initialization


class TestCodexAgentInit:
    """Tests for CodexAgent initialization."""

    def test_default_initialization(self) -> None:
        """Test agent initializes with defaults."""
        agent = CodexAgent()
        assert agent.id is not None
        assert agent.name is None
        assert agent.description is None

    def test_with_name_and_description(self) -> None:
        """Test agent with name and description."""
        agent = CodexAgent(name="test-agent", description="A test agent")
        assert agent.name == "test-agent"
        assert agent.description == "A test agent"

    def test_with_instructions_parameter(self) -> None:
        """Test agent with instructions parameter."""
        agent = CodexAgent(instructions="You are a helpful assistant.")
        assert agent._default_options.get("system_prompt") == "You are a helpful assistant."  # type: ignore[reportPrivateUsage]

    def test_with_system_prompt_in_options(self) -> None:
        """Test agent with system_prompt in options."""
        options: CodexAgentOptions = {
            "system_prompt": "You are a helpful assistant.",
        }
        agent = CodexAgent(default_options=options)
        assert agent._default_options.get("system_prompt") == "You are a helpful assistant."  # type: ignore[reportPrivateUsage]

    def test_with_default_options(self) -> None:
        """Test agent with default options."""
        options: CodexAgentOptions = {
            "model": "codex-mini-latest",
        }
        agent = CodexAgent(default_options=options)
        assert agent._settings["model"] == "codex-mini-latest"  # type: ignore[reportPrivateUsage]

    def test_with_function_tool(self) -> None:
        """Test agent with function tool."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = CodexAgent(tools=[greet])
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]

    def test_with_single_tool(self) -> None:
        """Test agent with single tool (not in list)."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = CodexAgent(tools=greet)
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]

    def test_with_builtin_tools(self) -> None:
        """Test agent with built-in tool names."""
        agent = CodexAgent(tools=["Read", "Write", "Bash"])
        assert agent._builtin_tools == ["Read", "Write", "Bash"]  # type: ignore[reportPrivateUsage]
        assert agent._custom_tools == []  # type: ignore[reportPrivateUsage]

    def test_with_mixed_tools(self) -> None:
        """Test agent with both built-in and custom tools."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = CodexAgent(tools=["Read", greet, "Bash"])
        assert agent._builtin_tools == ["Read", "Bash"]  # type: ignore[reportPrivateUsage]
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]


# region Test CodexAgent Lifecycle


class TestCodexAgentLifecycle:
    """Tests for CodexAgent lifecycle management."""

    def test_custom_tools_stored_from_constructor(self) -> None:
        """Test that custom tools from constructor are stored."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = CodexAgent(tools=[greet])
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]

    def test_multiple_custom_tools(self) -> None:
        """Test agent with multiple custom tools."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        @tool
        def farewell(name: str) -> str:
            """Say goodbye."""
            return f"Goodbye, {name}!"

        agent = CodexAgent(tools=[greet, farewell])
        assert len(agent._custom_tools) == 2  # type: ignore[reportPrivateUsage]

    def test_no_tools(self) -> None:
        """Test agent without tools."""
        agent = CodexAgent()
        assert agent._custom_tools == []  # type: ignore[reportPrivateUsage]
        assert agent._builtin_tools == []  # type: ignore[reportPrivateUsage]


# region Test CodexAgent Run


def _make_mock_thread(events: list[Any]) -> MagicMock:
    """Create a mock Thread that yields given events via run_streamed_events."""

    async def _stream_events(*args: Any, **kwargs: Any) -> Any:
        for event in events:
            yield event

    mock_thread = MagicMock()
    mock_thread.run_streamed_events = _stream_events
    mock_thread.id = "thread-123"
    return mock_thread


def _make_mock_codex(mock_thread: MagicMock) -> MagicMock:
    """Create a mock Codex client that returns the given thread."""
    mock_codex = MagicMock()
    mock_codex.start_thread.return_value = mock_thread
    mock_codex.resume_thread.return_value = mock_thread
    return mock_codex


class TestCodexAgentRun:
    """Tests for CodexAgent run method."""

    async def test_run_with_string_message(self) -> None:
        """Test run with string message yields text from ItemUpdatedEvent."""
        from codex_sdk.events import ItemUpdatedEvent, TurnCompletedEvent, Usage
        from codex_sdk.items import AgentMessageItem

        events = [
            ItemUpdatedEvent(
                type="item.updated",
                item=AgentMessageItem(id="msg-1", type="agent_message", text="Hello!"),
            ),
            TurnCompletedEvent(
                type="turn.completed",
                usage=Usage(input_tokens=10, cached_input_tokens=0, output_tokens=5),
            ),
        ]
        mock_thread = _make_mock_thread(events)
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            response = await agent.run("Hello")
            assert response.text == "Hello!"

    async def test_run_captures_thread_id(self) -> None:
        """Test that thread ID is captured from completed turn."""
        from codex_sdk.events import ItemUpdatedEvent, TurnCompletedEvent, Usage
        from codex_sdk.items import AgentMessageItem

        events = [
            ItemUpdatedEvent(
                type="item.updated",
                item=AgentMessageItem(id="msg-1", type="agent_message", text="Response"),
            ),
            TurnCompletedEvent(
                type="turn.completed",
                usage=Usage(input_tokens=10, cached_input_tokens=0, output_tokens=5),
            ),
        ]
        mock_thread = _make_mock_thread(events)
        mock_thread.id = "test-thread-id"
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            session = agent.create_session()
            await agent.run("Hello", session=session)
            assert session.service_session_id == "test-thread-id"

    async def test_run_with_existing_session(self) -> None:
        """Test run with existing session resumes thread."""
        from codex_sdk.events import ItemUpdatedEvent, TurnCompletedEvent, Usage
        from codex_sdk.items import AgentMessageItem

        events = [
            ItemUpdatedEvent(
                type="item.updated",
                item=AgentMessageItem(id="msg-1", type="agent_message", text="Response"),
            ),
            TurnCompletedEvent(
                type="turn.completed",
                usage=Usage(input_tokens=10, cached_input_tokens=0, output_tokens=5),
            ),
        ]
        mock_thread = _make_mock_thread(events)
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            session = agent.create_session()
            session.service_session_id = "existing-thread"
            await agent.run("Hello", session=session)
            mock_codex.resume_thread.assert_called_once()


# region Test CodexAgent Run Stream


class TestCodexAgentRunStream:
    """Tests for CodexAgent streaming run method."""

    async def test_run_stream_yields_updates(self) -> None:
        """Test run(stream=True) yields AgentResponseUpdate objects."""
        from codex_sdk.events import ItemUpdatedEvent, TurnCompletedEvent, Usage
        from codex_sdk.items import AgentMessageItem

        events = [
            ItemUpdatedEvent(
                type="item.updated",
                item=AgentMessageItem(id="msg-1", type="agent_message", text="Streaming "),
            ),
            ItemUpdatedEvent(
                type="item.updated",
                item=AgentMessageItem(id="msg-2", type="agent_message", text="response"),
            ),
            TurnCompletedEvent(
                type="turn.completed",
                usage=Usage(input_tokens=10, cached_input_tokens=0, output_tokens=5),
            ),
        ]
        mock_thread = _make_mock_thread(events)
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            updates: list[AgentResponseUpdate] = []
            async for update in agent.run("Hello", stream=True):
                updates.append(update)
            assert len(updates) == 2
            assert updates[0].role == "assistant"
            assert updates[0].text == "Streaming "
            assert updates[1].text == "response"

    async def test_run_stream_yields_reasoning(self) -> None:
        """Test run(stream=True) yields reasoning updates."""
        from codex_sdk.events import ItemUpdatedEvent, TurnCompletedEvent, Usage
        from codex_sdk.items import AgentMessageItem, ReasoningItem

        events = [
            ItemUpdatedEvent(
                type="item.updated",
                item=ReasoningItem(id="reason-1", type="reasoning", text="Let me think..."),
            ),
            ItemUpdatedEvent(
                type="item.updated",
                item=AgentMessageItem(id="msg-1", type="agent_message", text="Hello!"),
            ),
            TurnCompletedEvent(
                type="turn.completed",
                usage=Usage(input_tokens=10, cached_input_tokens=0, output_tokens=5),
            ),
        ]
        mock_thread = _make_mock_thread(events)
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            updates: list[AgentResponseUpdate] = []
            async for update in agent.run("Hello", stream=True):
                updates.append(update)
            assert len(updates) == 2

    async def test_run_stream_raises_on_error_item(self) -> None:
        """Test run raises AgentException when ErrorItem is received."""
        from agent_framework.exceptions import AgentException
        from codex_sdk.events import ItemUpdatedEvent
        from codex_sdk.items import ErrorItem

        events = [
            ItemUpdatedEvent(
                type="item.updated",
                item=ErrorItem(id="err-1", type="error", message="API rate limit exceeded"),
            ),
        ]
        mock_thread = _make_mock_thread(events)
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            with pytest.raises(AgentException) as exc_info:
                async for _ in agent.run("Hello", stream=True):
                    pass
            assert "API rate limit exceeded" in str(exc_info.value)

    async def test_run_stream_raises_on_turn_failed(self) -> None:
        """Test run raises AgentException when TurnFailedEvent is received."""
        from agent_framework.exceptions import AgentException
        from codex_sdk.events import ThreadError, TurnFailedEvent

        events = [
            TurnFailedEvent(
                type="turn.failed",
                error=ThreadError(message="Model not found"),
            ),
        ]
        mock_thread = _make_mock_thread(events)
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            with pytest.raises(AgentException) as exc_info:
                async for _ in agent.run("Hello", stream=True):
                    pass
            assert "turn failed" in str(exc_info.value).lower()


# region Test CodexAgent Session Management


class TestCodexAgentSessionManagement:
    """Tests for CodexAgent session management."""

    def test_create_session(self) -> None:
        """Test create_session creates a new session."""
        agent = CodexAgent()
        session = agent.create_session()
        assert isinstance(session, AgentSession)
        assert session.service_session_id is None

    def test_create_session_with_service_session_id(self) -> None:
        """Test create_session with existing service_session_id."""
        agent = CodexAgent()
        session = agent.create_session(session_id="existing-session-123")
        assert isinstance(session, AgentSession)

    def test_get_or_create_thread_starts_new_thread(self) -> None:
        """Test _get_or_create_thread starts new thread when no session."""
        mock_codex = MagicMock()
        mock_thread = MagicMock()
        mock_codex.start_thread.return_value = mock_thread

        agent = CodexAgent()
        agent._client = mock_codex  # type: ignore[reportPrivateUsage]

        thread = agent._get_or_create_thread(None)  # type: ignore[reportPrivateUsage]
        mock_codex.start_thread.assert_called_once()
        assert thread is mock_thread

    def test_get_or_create_thread_resumes_existing(self) -> None:
        """Test _get_or_create_thread resumes thread when session ID provided."""
        mock_codex = MagicMock()
        mock_thread = MagicMock()
        mock_codex.resume_thread.return_value = mock_thread

        agent = CodexAgent()
        agent._client = mock_codex  # type: ignore[reportPrivateUsage]

        thread = agent._get_or_create_thread("existing-thread-123")  # type: ignore[reportPrivateUsage]
        # Verify resume_thread was called with the correct thread ID
        args = mock_codex.resume_thread.call_args
        assert args[0][0] == "existing-thread-123"
        assert thread is mock_thread

    def test_get_or_create_thread_reuses_for_same_session(self) -> None:
        """Test _get_or_create_thread reuses thread for same session."""
        mock_codex = MagicMock()
        mock_thread = MagicMock()
        mock_codex.start_thread.return_value = mock_thread

        agent = CodexAgent()
        agent._client = mock_codex  # type: ignore[reportPrivateUsage]

        # First call
        thread1 = agent._get_or_create_thread(None)  # type: ignore[reportPrivateUsage]

        # Same session should reuse
        thread2 = agent._get_or_create_thread(None)  # type: ignore[reportPrivateUsage]

        assert thread1 is thread2
        assert mock_codex.start_thread.call_count == 1


# region Test CodexAgent Error Handling


class TestCodexAgentErrorHandling:
    """Tests for CodexAgent error handling."""

    async def test_handles_empty_response(self) -> None:
        """Test handling of empty response (no events)."""
        mock_thread = _make_mock_thread([])
        mock_codex = _make_mock_codex(mock_thread)

        with patch("agent_framework_codex._agent.Codex", return_value=mock_codex):
            agent = CodexAgent()
            response = await agent.run("Hello")
            assert response.messages == []


# region Test Format Prompt


class TestFormatPrompt:
    """Tests for _format_prompt method."""

    def test_format_empty_messages(self) -> None:
        """Test formatting empty messages."""
        agent = CodexAgent()
        result = agent._format_prompt([])  # type: ignore[reportPrivateUsage]
        assert result == ""

    def test_format_none_messages(self) -> None:
        """Test formatting None messages."""
        agent = CodexAgent()
        result = agent._format_prompt(None)  # type: ignore[reportPrivateUsage]
        assert result == ""

    def test_format_user_message(self) -> None:
        """Test formatting user message."""
        agent = CodexAgent()
        msg = Message(
            role="user",
            contents=[Content.from_text(text="Hello")],
        )
        result = agent._format_prompt([msg])  # type: ignore[reportPrivateUsage]
        assert "Hello" in result

    def test_format_multiple_messages(self) -> None:
        """Test formatting multiple messages."""
        agent = CodexAgent()
        messages = [
            Message(role="user", contents=[Content.from_text(text="Hi")]),
            Message(role="assistant", contents=[Content.from_text(text="Hello!")]),
            Message(role="user", contents=[Content.from_text(text="How are you?")]),
        ]
        result = agent._format_prompt(messages)  # type: ignore[reportPrivateUsage]
        assert "Hi" in result
        assert "Hello!" in result
        assert "How are you?" in result


# region Test Default Options Property


class TestDefaultOptionsProperty:
    """Tests for the default_options property."""

    def test_default_options_maps_system_prompt_to_instructions(self) -> None:
        """Test that default_options maps system_prompt to instructions."""
        agent = CodexAgent(instructions="Be helpful")
        opts = agent.default_options
        assert "instructions" in opts
        assert opts["instructions"] == "Be helpful"
        assert "system_prompt" not in opts

    def test_default_options_without_system_prompt(self) -> None:
        """Test default_options without system_prompt."""
        agent = CodexAgent()
        opts = agent.default_options
        assert "instructions" not in opts
        assert "system_prompt" not in opts


# region Test Approval Policy


class TestCodexAgentApprovalPolicy:
    """Tests for CodexAgent approval policy handling."""

    def test_default_approval_policy(self) -> None:
        """Test default approval policy is None."""
        agent = CodexAgent()
        assert agent._settings["approval_policy"] is None  # type: ignore[reportPrivateUsage]

    def test_approval_policy_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test approval policy from environment settings."""
        monkeypatch.setenv("CODEX_AGENT_APPROVAL_POLICY", "full-auto")
        settings = load_settings(CodexAgentSettings, env_prefix="CODEX_AGENT_")
        assert settings["approval_policy"] == "full-auto"

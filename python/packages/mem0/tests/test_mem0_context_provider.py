# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

import importlib
import os
import sys
from typing import Any
from unittest.mock import AsyncMock

import pytest
from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.mem0 import Mem0ContextProvider


def test_mem0_context_provider_import() -> None:
    """Test that Mem0ContextProvider can be imported."""
    assert Mem0ContextProvider is not None


@pytest.fixture
def mock_mem0_client() -> AsyncMock:
    """Create a mock Mem0 AsyncMemoryClient."""
    from mem0 import AsyncMemoryClient

    mock_client = AsyncMock(spec=AsyncMemoryClient)
    mock_client.add = AsyncMock()
    mock_client.search = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    mock_client.async_client = AsyncMock()
    mock_client.async_client.aclose = AsyncMock()
    return mock_client


@pytest.fixture
def mock_agent() -> AsyncMock:
    """Create a mock agent."""
    return AsyncMock()


@pytest.fixture
def session() -> AgentSession:
    """Create a test AgentSession."""
    return AgentSession(session_id="test-session")


@pytest.fixture
def sample_messages() -> list[Message]:
    """Create sample chat messages for testing."""
    return [
        Message(role="user", text="Hello, how are you?"),
        Message(role="assistant", text="I'm doing well, thank you!"),
        Message(role="system", text="You are a helpful assistant"),
    ]


def _make_context(input_messages: list[Message], session_id: str = "test-session") -> SessionContext:
    """Helper to create a SessionContext with the given input messages."""
    return SessionContext(session_id=session_id, input_messages=input_messages)


def _empty_state() -> dict[str, Any]:
    """Helper to create an empty state dict."""
    return {}


def test_init_with_all_ids(mock_mem0_client: AsyncMock) -> None:
    """Test initialization with all IDs provided."""
    provider = Mem0ContextProvider(
        source_id="mem0",
        user_id="user123",
        agent_id="agent123",
        application_id="app123",
        mem0_client=mock_mem0_client,
    )
    assert provider.user_id == "user123"
    assert provider.agent_id == "agent123"
    assert provider.application_id == "app123"


def test_init_without_filters_succeeds(mock_mem0_client: AsyncMock) -> None:
    """Test that initialization succeeds even without filters (validation happens during invocation)."""
    provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)
    assert provider.user_id is None
    assert provider.agent_id is None
    assert provider.application_id is None


def test_init_with_custom_context_prompt(mock_mem0_client: AsyncMock) -> None:
    """Test initialization with custom context prompt."""
    custom_prompt = "## Custom Memories\nConsider these memories:"
    provider = Mem0ContextProvider(
        source_id="mem0", user_id="user123", context_prompt=custom_prompt, mem0_client=mock_mem0_client
    )
    assert provider.context_prompt == custom_prompt


def test_init_with_provided_client_should_not_close(mock_mem0_client: AsyncMock) -> None:
    """Test that provided client should not be closed by provider."""
    provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
    assert provider._should_close_client is False


async def test_async_context_manager_entry(mock_mem0_client: AsyncMock) -> None:
    """Test async context manager entry returns self."""
    provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
    async with provider as ctx:
        assert ctx is provider


async def test_async_context_manager_exit_does_not_close_provided_client(mock_mem0_client: AsyncMock) -> None:
    """Test that async context manager does not close provided client."""
    provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
    assert provider._should_close_client is False

    async with provider:
        pass

    mock_mem0_client.__aexit__.assert_not_called()


class TestMem0ContextProviderAfterRun:
    """Test after_run method (storing messages to Mem0)."""

    async def test_after_run_fails_without_filters(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that after_run fails when no filters are provided."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="Hello!")])

        with pytest.raises(ServiceInitializationError) as exc_info:
            await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        assert "At least one of the filters" in str(exc_info.value)

    async def test_after_run_single_input_message(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test storing a single input message."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="Hello!")])

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        mock_mem0_client.add.assert_called_once()
        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["messages"] == [{"role": "user", "content": "Hello!"}]
        assert call_args.kwargs["user_id"] == "user123"

    async def test_after_run_multiple_messages(
        self,
        mock_mem0_client: AsyncMock,
        mock_agent: AsyncMock,
        session: AgentSession,
        sample_messages: list[Message],
    ) -> None:
        """Test storing multiple input messages."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context(sample_messages)

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        mock_mem0_client.add.assert_called_once()
        call_args = mock_mem0_client.add.call_args
        expected_messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"},
            {"role": "system", "content": "You are a helpful assistant"},
        ]
        assert call_args.kwargs["messages"] == expected_messages

    async def test_after_run_includes_response_messages(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that after_run includes response messages."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="Hello!")])
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="Hi there!")])

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        mock_mem0_client.add.assert_called_once()
        call_args = mock_mem0_client.add.call_args
        expected_messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        assert call_args.kwargs["messages"] == expected_messages

    async def test_after_run_with_agent_id(
        self,
        mock_mem0_client: AsyncMock,
        mock_agent: AsyncMock,
        session: AgentSession,
        sample_messages: list[Message],
    ) -> None:
        """Test storing messages with agent_id."""
        provider = Mem0ContextProvider(source_id="mem0", agent_id="agent123", mem0_client=mock_mem0_client)
        ctx = _make_context(sample_messages)

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["agent_id"] == "agent123"
        assert call_args.kwargs["user_id"] is None

    async def test_after_run_with_application_id(
        self,
        mock_mem0_client: AsyncMock,
        mock_agent: AsyncMock,
        session: AgentSession,
        sample_messages: list[Message],
    ) -> None:
        """Test storing messages with application_id in metadata."""
        provider = Mem0ContextProvider(
            source_id="mem0", user_id="user123", application_id="app123", mem0_client=mock_mem0_client
        )
        ctx = _make_context(sample_messages)

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["metadata"] == {"application_id": "app123"}

    async def test_after_run_uses_session_id_as_run_id(
        self,
        mock_mem0_client: AsyncMock,
        mock_agent: AsyncMock,
        session: AgentSession,
        sample_messages: list[Message],
    ) -> None:
        """Test that after_run uses the context session_id as run_id."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context(sample_messages, session_id="my-session")

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["run_id"] == "my-session"

    async def test_after_run_filters_empty_messages(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that empty or invalid messages are filtered out."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        messages = [
            Message(role="user", text=""),
            Message(role="user", text="   "),
            Message(role="user", text="Valid message"),
        ]
        ctx = _make_context(messages)

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["messages"] == [{"role": "user", "content": "Valid message"}]

    async def test_after_run_skips_when_no_valid_messages(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that mem0 client is not called when no valid messages exist."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        messages = [
            Message(role="user", text=""),
            Message(role="user", text="   "),
        ]
        ctx = _make_context(messages)

        await provider.after_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        mock_mem0_client.add.assert_not_called()


class TestMem0ContextProviderBeforeRun:
    """Test before_run method (searching memories and adding to context)."""

    async def test_before_run_fails_without_filters(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that before_run fails when no filters are provided."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="What's the weather?")])

        with pytest.raises(ServiceInitializationError) as exc_info:
            await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        assert "At least one of the filters" in str(exc_info.value)

    async def test_before_run_single_message(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test before_run with a single input message."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="What's the weather?")])

        mock_mem0_client.search.return_value = [
            {"memory": "User likes outdoor activities"},
            {"memory": "User lives in Seattle"},
        ]

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        mock_mem0_client.search.assert_called_once()
        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["query"] == "What's the weather?"
        assert call_args.kwargs["filters"] == {"user_id": "user123", "run_id": "test-session"}

        context_messages = ctx.get_messages()
        assert len(context_messages) > 0
        expected_text = (
            "## Memories\nConsider the following memories when answering user questions:\n"
            "User likes outdoor activities\nUser lives in Seattle"
        )
        assert context_messages[0].text == expected_text

    async def test_before_run_multiple_messages(
        self,
        mock_mem0_client: AsyncMock,
        mock_agent: AsyncMock,
        session: AgentSession,
        sample_messages: list[Message],
    ) -> None:
        """Test before_run with multiple input messages."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context(sample_messages)

        mock_mem0_client.search.return_value = [{"memory": "Previous conversation context"}]

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.search.call_args
        expected_query = "Hello, how are you?\nI'm doing well, thank you!\nYou are a helpful assistant"
        assert call_args.kwargs["query"] == expected_query

    async def test_before_run_with_agent_id(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test before_run with agent_id."""
        provider = Mem0ContextProvider(source_id="mem0", agent_id="agent123", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="Hello")])

        mock_mem0_client.search.return_value = []

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["filters"] == {"agent_id": "agent123", "run_id": "test-session"}

    async def test_before_run_with_session_id_in_filters(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test before_run includes session_id as run_id in search filters."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="Hello")], session_id="my-session")

        mock_mem0_client.search.return_value = []

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["filters"] == {"user_id": "user123", "run_id": "my-session"}

    async def test_before_run_no_memories_does_not_add_messages(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that no memories does not add context messages."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text="Hello")])

        mock_mem0_client.search.return_value = []

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        context_messages = ctx.get_messages()
        assert len(context_messages) == 0

    async def test_before_run_empty_input_text_skips_search(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that empty input text skips the search entirely."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        ctx = _make_context([Message(role="user", text=""), Message(role="user", text="   ")])

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        mock_mem0_client.search.assert_not_called()

    async def test_before_run_filters_empty_message_text(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test that empty message text is filtered out from query."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        messages = [
            Message(role="user", text=""),
            Message(role="user", text="Valid message"),
            Message(role="user", text="   "),
        ]
        ctx = _make_context(messages)

        mock_mem0_client.search.return_value = []

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["query"] == "Valid message"

    async def test_before_run_custom_context_prompt(
        self, mock_mem0_client: AsyncMock, mock_agent: AsyncMock, session: AgentSession
    ) -> None:
        """Test before_run with custom context prompt."""
        custom_prompt = "## Custom Context\nRemember these details:"
        provider = Mem0ContextProvider(
            source_id="mem0",
            user_id="user123",
            context_prompt=custom_prompt,
            mem0_client=mock_mem0_client,
        )
        ctx = _make_context([Message(role="user", text="Hello")])

        mock_mem0_client.search.return_value = [{"memory": "Test memory"}]

        await provider.before_run(agent=mock_agent, session=session, context=ctx, state=_empty_state())

        context_messages = ctx.get_messages()
        expected_text = "## Custom Context\nRemember these details:\nTest memory"
        assert len(context_messages) > 0
        assert context_messages[0].text == expected_text


class TestMem0ContextProviderValidation:
    """Test validation methods."""

    def test_validate_filters_fails_without_any_filter(self, mock_mem0_client: AsyncMock) -> None:
        """Test validation failure when no filters are set."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)

        with pytest.raises(ServiceInitializationError) as exc_info:
            provider._validate_filters()

        assert "At least one of the filters" in str(exc_info.value)

    def test_validate_filters_succeeds_with_user_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test validation succeeds with user_id set."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)
        provider._validate_filters()  # Should not raise

    def test_validate_filters_succeeds_with_agent_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test validation succeeds with agent_id set."""
        provider = Mem0ContextProvider(source_id="mem0", agent_id="agent123", mem0_client=mock_mem0_client)
        provider._validate_filters()  # Should not raise

    def test_validate_filters_succeeds_with_application_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test validation succeeds with application_id set."""
        provider = Mem0ContextProvider(source_id="mem0", application_id="app123", mem0_client=mock_mem0_client)
        provider._validate_filters()  # Should not raise


class TestMem0ContextProviderBuildFilters:
    """Test the _build_filters method."""

    def test_build_filters_with_user_id_only(self, mock_mem0_client: AsyncMock) -> None:
        """Test building filters with only user_id."""
        provider = Mem0ContextProvider(source_id="mem0", user_id="user123", mem0_client=mock_mem0_client)

        filters = provider._build_filters()
        assert filters == {"user_id": "user123"}

    def test_build_filters_with_all_parameters(self, mock_mem0_client: AsyncMock) -> None:
        """Test building filters with all initialization parameters."""
        provider = Mem0ContextProvider(
            source_id="mem0",
            user_id="user123",
            agent_id="agent456",
            application_id="app999",
            mem0_client=mock_mem0_client,
        )

        filters = provider._build_filters()
        assert filters == {
            "user_id": "user123",
            "agent_id": "agent456",
            "app_id": "app999",
        }

    def test_build_filters_excludes_none_values(self, mock_mem0_client: AsyncMock) -> None:
        """Test that None values are excluded from filters."""
        provider = Mem0ContextProvider(
            source_id="mem0",
            user_id="user123",
            agent_id=None,
            application_id=None,
            mem0_client=mock_mem0_client,
        )

        filters = provider._build_filters()
        assert filters == {"user_id": "user123"}
        assert "agent_id" not in filters
        assert "app_id" not in filters

    def test_build_filters_with_session_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test that session_id is included as run_id in filters."""
        provider = Mem0ContextProvider(
            source_id="mem0",
            user_id="user123",
            mem0_client=mock_mem0_client,
        )

        filters = provider._build_filters(session_id="session-123")
        assert filters == {
            "user_id": "user123",
            "run_id": "session-123",
        }

    def test_build_filters_returns_empty_dict_when_no_parameters(self, mock_mem0_client: AsyncMock) -> None:
        """Test that _build_filters returns an empty dict when no parameters are set."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)

        filters = provider._build_filters()
        assert filters == {}


class TestMem0Telemetry:
    """Test telemetry configuration for Mem0."""

    def test_mem0_telemetry_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that MEM0_TELEMETRY is set to 'false' by default when importing the package."""
        # Ensure MEM0_TELEMETRY is not set before importing the module under test
        monkeypatch.delenv("MEM0_TELEMETRY", raising=False)

        # Remove cached modules to force re-import and trigger module-level initialization
        modules_to_remove = [key for key in sys.modules if key.startswith("agent_framework_mem0")]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Import (and reload) the module so that it can set MEM0_TELEMETRY when unset
        import agent_framework_mem0

        importlib.reload(agent_framework_mem0)

        # The environment variable should be set to "false" after importing
        assert os.environ.get("MEM0_TELEMETRY") == "false"

    def test_mem0_telemetry_respects_user_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that user-set MEM0_TELEMETRY value is not overwritten."""
        # Remove cached modules to force re-import
        modules_to_remove = [key for key in sys.modules if key.startswith("agent_framework_mem0")]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Set user preference before import
        monkeypatch.setenv("MEM0_TELEMETRY", "true")

        # Re-import the module
        import agent_framework_mem0

        importlib.reload(agent_framework_mem0)

        # User setting should be preserved
        assert os.environ.get("MEM0_TELEMETRY") == "true"

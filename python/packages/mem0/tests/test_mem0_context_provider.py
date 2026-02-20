# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext

from agent_framework_mem0._context_provider import Mem0ContextProvider


@pytest.fixture
def mock_mem0_client() -> AsyncMock:
    """Create a mock Mem0 AsyncMemoryClient."""
    from mem0 import AsyncMemoryClient

    mock_client = AsyncMock(spec=AsyncMemoryClient)
    mock_client.add = AsyncMock()
    mock_client.search = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


@pytest.fixture
def mock_oss_mem0_client() -> AsyncMock:
    """Create a mock Mem0 OSS AsyncMemory client."""
    from mem0 import AsyncMemory

    mock_client = AsyncMock(spec=AsyncMemory)
    mock_client.add = AsyncMock()
    mock_client.search = AsyncMock()
    return mock_client


# -- Initialization tests ------------------------------------------------------


class TestInit:
    """Test Mem0ContextProvider initialization."""

    def test_init_with_all_params(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(
            source_id="mem0",
            mem0_client=mock_mem0_client,
            api_key="key-123",
            application_id="app1",
            agent_id="agent1",
            user_id="user1",
            context_prompt="Custom prompt",
        )
        assert provider.source_id == "mem0"
        assert provider.api_key == "key-123"
        assert provider.application_id == "app1"
        assert provider.agent_id == "agent1"
        assert provider.user_id == "user1"
        assert provider.context_prompt == "Custom prompt"
        assert provider.mem0_client is mock_mem0_client
        assert provider._should_close_client is False

    def test_init_default_context_prompt(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        assert provider.context_prompt == Mem0ContextProvider.DEFAULT_CONTEXT_PROMPT

    def test_init_auto_creates_client_when_none(self) -> None:
        """When no client is provided, a default AsyncMemoryClient is created and flagged for closing."""
        with (
            patch("mem0.client.main.AsyncMemoryClient.__init__", return_value=None) as mock_init,
            patch("mem0.client.main.AsyncMemoryClient._validate_api_key", return_value=None),
        ):
            provider = Mem0ContextProvider(source_id="mem0", api_key="test-key", user_id="u1")
            mock_init.assert_called_once_with(api_key="test-key")
            assert provider._should_close_client is True

    def test_provided_client_not_flagged_for_close(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        assert provider._should_close_client is False


# -- before_run tests ----------------------------------------------------------


class TestBeforeRun:
    """Test before_run hook."""

    async def test_memories_added_to_context(self, mock_mem0_client: AsyncMock) -> None:
        """Mocked mem0 search returns memories → messages added to context with prompt."""
        mock_mem0_client.search.return_value = [
            {"memory": "User likes Python"},
            {"memory": "User prefers dark mode"},
        ]
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_mem0_client.search.assert_awaited_once()
        assert "mem0" in ctx.context_messages
        added = ctx.context_messages["mem0"]
        assert len(added) == 1
        assert "User likes Python" in added[0].text  # type: ignore[operator]
        assert "User prefers dark mode" in added[0].text  # type: ignore[operator]
        assert provider.context_prompt in added[0].text  # type: ignore[operator]

    async def test_empty_input_skips_search(self, mock_mem0_client: AsyncMock) -> None:
        """Empty input messages → no search performed."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="")], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_mem0_client.search.assert_not_awaited()
        assert "mem0" not in ctx.context_messages

    async def test_empty_search_results_no_messages(self, mock_mem0_client: AsyncMock) -> None:
        """Empty search results → no messages added."""
        mock_mem0_client.search.return_value = []
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="test")], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert "mem0" not in ctx.context_messages

    async def test_validates_filters_before_search(self, mock_mem0_client: AsyncMock) -> None:
        """Raises ValueError when no filters."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="test")], session_id="s1")

        with pytest.raises(ValueError, match="At least one of the filters"):
            await provider.before_run(agent=None, session=session, context=ctx, state=session.state)  # type: ignore[arg-type]

    async def test_v1_1_response_format(self, mock_mem0_client: AsyncMock) -> None:
        """Search response in v1.1 dict format with 'results' key."""
        mock_mem0_client.search.return_value = {"results": [{"memory": "remembered fact"}]}
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="test")], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        added = ctx.context_messages["mem0"]
        assert "remembered fact" in added[0].text  # type: ignore[operator]

    async def test_search_query_combines_input_messages(self, mock_mem0_client: AsyncMock) -> None:
        """Multiple input messages are joined for the search query."""
        mock_mem0_client.search.return_value = []
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", text="Hello"),
                Message(role="user", text="World"),
            ],
            session_id="s1",
        )

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        call_kwargs = mock_mem0_client.search.call_args.kwargs
        assert call_kwargs["query"] == "Hello\nWorld"

    async def test_oss_client_passes_direct_kwargs(self, mock_oss_mem0_client: AsyncMock) -> None:
        """OSS AsyncMemory client should receive user_id as direct kwarg, not in filters."""
        mock_oss_mem0_client.search.return_value = [{"memory": "User likes Python"}]
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_oss_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        call_kwargs = mock_oss_mem0_client.search.call_args.kwargs
        assert call_kwargs["query"] == "Hello"
        assert call_kwargs["user_id"] == "u1"
        assert "filters" not in call_kwargs

    async def test_oss_client_all_scoping_params(self, mock_oss_mem0_client: AsyncMock) -> None:
        """OSS client with all scoping parameters passes them as direct kwargs."""
        mock_oss_mem0_client.search.return_value = []
        provider = Mem0ContextProvider(
            source_id="mem0", mem0_client=mock_oss_mem0_client, user_id="u1", agent_id="a1", application_id="app1"
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        call_kwargs = mock_oss_mem0_client.search.call_args.kwargs
        assert call_kwargs["user_id"] == "u1"
        assert call_kwargs["agent_id"] == "a1"
        assert "filters" not in call_kwargs

    async def test_platform_client_passes_filters_dict(self, mock_mem0_client: AsyncMock) -> None:
        """Platform AsyncMemoryClient should receive scoping params in a filters dict."""
        mock_mem0_client.search.return_value = []
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        call_kwargs = mock_mem0_client.search.call_args.kwargs
        assert call_kwargs["query"] == "Hello"
        assert "filters" in call_kwargs
        assert call_kwargs["filters"]["user_id"] == "u1"


# -- after_run tests -----------------------------------------------------------


class TestAfterRun:
    """Test after_run hook."""

    async def test_stores_input_and_response(self, mock_mem0_client: AsyncMock) -> None:
        """Stores input+response messages to mem0 via client.add."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="question")], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="answer")])

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_mem0_client.add.assert_awaited_once()
        call_kwargs = mock_mem0_client.add.call_args.kwargs
        assert call_kwargs["messages"] == [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        assert call_kwargs["user_id"] == "u1"
        assert "run_id" not in call_kwargs

    async def test_only_stores_user_assistant_system(self, mock_mem0_client: AsyncMock) -> None:
        """Only stores user/assistant/system messages with text."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", text="hello"),
                Message(role="tool", text="tool output"),
            ],
            session_id="s1",
        )
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="reply")])

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        call_kwargs = mock_mem0_client.add.call_args.kwargs
        roles = [m["role"] for m in call_kwargs["messages"]]
        assert "tool" not in roles
        assert roles == ["user", "assistant"]

    async def test_skips_empty_messages(self, mock_mem0_client: AsyncMock) -> None:
        """Skips messages with empty text."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", text=""),
                Message(role="user", text="   "),
            ],
            session_id="s1",
        )
        ctx._response = AgentResponse(messages=[])

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_mem0_client.add.assert_not_awaited()

    async def test_no_run_id_in_storage(self, mock_mem0_client: AsyncMock) -> None:
        """run_id is not passed to mem0 add, so memories are not scoped to sessions."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="hi")], session_id="my-session")
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="hey")])

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert "run_id" not in mock_mem0_client.add.call_args.kwargs

    async def test_validates_filters(self, mock_mem0_client: AsyncMock) -> None:
        """Raises ValueError when no filters."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="hi")], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="hey")])

        with pytest.raises(ValueError, match="At least one of the filters"):
            await provider.after_run(agent=None, session=session, context=ctx, state=session.state)  # type: ignore[arg-type]

    async def test_stores_with_application_id_metadata(self, mock_mem0_client: AsyncMock) -> None:
        """application_id is passed in metadata."""
        provider = Mem0ContextProvider(
            source_id="mem0", mem0_client=mock_mem0_client, user_id="u1", application_id="app1"
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="hi")], session_id="s1")
        ctx._response = AgentResponse(messages=[])

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert mock_mem0_client.add.call_args.kwargs["metadata"] == {"application_id": "app1"}


# -- _validate_filters tests --------------------------------------------------


class TestValidateFilters:
    """Test _validate_filters method."""

    def test_raises_when_no_filters(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)
        with pytest.raises(ValueError, match="At least one of the filters"):
            provider._validate_filters()

    def test_passes_with_user_id(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        provider._validate_filters()  # should not raise

    def test_passes_with_agent_id(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, agent_id="a1")
        provider._validate_filters()

    def test_passes_with_application_id(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, application_id="app1")
        provider._validate_filters()


# -- _build_filters tests -----------------------------------------------------


class TestBuildFilters:
    """Test _build_filters method."""

    def test_user_id_only(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        assert provider._build_filters() == {"user_id": "u1"}

    def test_all_params(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(
            source_id="mem0",
            mem0_client=mock_mem0_client,
            user_id="u1",
            agent_id="a1",
            application_id="app1",
        )
        assert provider._build_filters() == {
            "user_id": "u1",
            "agent_id": "a1",
            "app_id": "app1",
        }

    def test_excludes_none_values(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        filters = provider._build_filters()
        assert "agent_id" not in filters
        assert "run_id" not in filters
        assert "app_id" not in filters

    def test_no_run_id_in_search_filters(self, mock_mem0_client: AsyncMock) -> None:
        """run_id is excluded from search filters so memories work across sessions."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        filters = provider._build_filters()
        assert "run_id" not in filters

    def test_empty_when_no_params(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client)
        assert provider._build_filters() == {}


# -- Context manager tests -----------------------------------------------------


class TestContextManager:
    """Test __aenter__/__aexit__ delegation."""

    async def test_aenter_delegates_to_client(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        result = await provider.__aenter__()
        assert result is provider
        mock_mem0_client.__aenter__.assert_awaited_once()

    async def test_aexit_closes_auto_created_client(self, mock_mem0_client: AsyncMock) -> None:
        """Auto-created clients (_should_close_client=True) are closed on exit."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        provider._should_close_client = True
        await provider.__aexit__(None, None, None)
        mock_mem0_client.__aexit__.assert_awaited_once()

    async def test_aexit_does_not_close_provided_client(self, mock_mem0_client: AsyncMock) -> None:
        """Provided clients (_should_close_client=False) are NOT closed on exit."""
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        assert provider._should_close_client is False
        await provider.__aexit__(None, None, None)
        mock_mem0_client.__aexit__.assert_not_awaited()

    async def test_async_with_syntax(self, mock_mem0_client: AsyncMock) -> None:
        provider = Mem0ContextProvider(source_id="mem0", mem0_client=mock_mem0_client, user_id="u1")
        async with provider as p:
            assert p is provider

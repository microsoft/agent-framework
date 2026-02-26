# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from agent_framework import AGENT_FRAMEWORK_USER_AGENT, AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext

from agent_framework_azure_ai._foundry_memory_provider import FoundryMemoryProvider


@pytest.fixture
def mock_project_client() -> AsyncMock:
    """Create a mock AIProjectClient."""
    mock_client = AsyncMock()
    mock_client.memory_stores = AsyncMock()
    mock_client.memory_stores.search_memories = AsyncMock()
    mock_client.memory_stores.begin_update_memories = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


@pytest.fixture
def mock_credential() -> Mock:
    """Create a mock Azure credential."""
    return Mock()


# -- Initialization tests ------------------------------------------------------


class TestInit:
    """Test FoundryMemoryProvider initialization."""

    def test_init_with_all_params(self, mock_project_client: AsyncMock) -> None:
        provider = FoundryMemoryProvider(
            source_id="custom_source",
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
            context_prompt="Custom prompt",
            update_delay=60,
        )
        assert provider.source_id == "custom_source"
        assert provider.project_client is mock_project_client
        assert provider.memory_store_name == "test_store"
        assert provider.scope == "user_123"
        assert provider.context_prompt == "Custom prompt"
        assert provider.update_delay == 60

    def test_init_default_source_id(self, mock_project_client: AsyncMock) -> None:
        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        assert provider.source_id == FoundryMemoryProvider.DEFAULT_SOURCE_ID

    def test_init_default_context_prompt(self, mock_project_client: AsyncMock) -> None:
        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        assert provider.context_prompt == FoundryMemoryProvider.DEFAULT_CONTEXT_PROMPT

    def test_init_default_update_delay(self, mock_project_client: AsyncMock) -> None:
        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        assert provider.update_delay == 300

    def test_init_with_project_endpoint_and_credential(
        self, mock_project_client: AsyncMock, mock_credential: Mock
    ) -> None:
        with patch("agent_framework_azure_ai._foundry_memory_provider.AIProjectClient") as mock_ai_project_client:
            mock_ai_project_client.return_value = mock_project_client
            provider = FoundryMemoryProvider(
                project_endpoint="https://test.project.endpoint",
                credential=mock_credential,  # type: ignore[arg-type]
                memory_store_name="test_store",
                scope="user_123",
            )
            assert provider.project_client is mock_project_client
            mock_ai_project_client.assert_called_once_with(
                endpoint="https://test.project.endpoint",
                credential=mock_credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )

    def test_init_requires_project_endpoint_without_project_client(self) -> None:
        with (
            patch("agent_framework_azure_ai._foundry_memory_provider.load_settings") as mock_load_settings,
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ValueError, match="project endpoint is required"),
        ):
            mock_load_settings.return_value = {"project_endpoint": None}
            FoundryMemoryProvider(
                memory_store_name="test_store",
                scope="user_123",
            )

    def test_init_requires_credential_without_project_client(self) -> None:
        with pytest.raises(ValueError, match="Azure credential is required"):
            FoundryMemoryProvider(
                project_endpoint="https://test.project.endpoint",
                memory_store_name="test_store",
                scope="user_123",
            )

    def test_init_requires_memory_store_name(self, mock_project_client: AsyncMock) -> None:
        with pytest.raises(ValueError, match="memory_store_name is required"):
            FoundryMemoryProvider(
                project_client=mock_project_client,
                memory_store_name="",
                scope="user_123",
            )

    def test_init_requires_scope(self, mock_project_client: AsyncMock) -> None:
        with pytest.raises(ValueError, match="scope is required"):
            FoundryMemoryProvider(
                project_client=mock_project_client,
                memory_store_name="test_store",
                scope="",
            )


# -- before_run tests ----------------------------------------------------------


class TestBeforeRun:
    """Test before_run hook."""

    async def test_retrieves_static_memories_on_first_run(self, mock_project_client: AsyncMock) -> None:
        """First call retrieves static (user profile) memories."""
        mem1 = Mock()
        mem1.memory_item.content = "User prefers Python"
        mem2 = Mock()
        mem2.memory_item.content = "User is based in Seattle"
        mock_search_result = Mock()
        mock_search_result.memories = [mem1, mem2]
        mock_project_client.memory_stores.search_memories.return_value = mock_search_result

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        await provider.before_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Should call search_memories twice: once for static, once for contextual
        assert mock_project_client.memory_stores.search_memories.call_count == 2
        # Static memories should be cached
        assert len(session.state[provider.source_id]["static_memories"]) == 2
        assert session.state[provider.source_id]["initialized"] is True

    async def test_contextual_memories_added_to_context(self, mock_project_client: AsyncMock) -> None:
        """Contextual search returns memories → messages added to context with prompt."""
        # Mock static search (first call)
        static_mem = Mock()
        static_mem.memory_item.content = "User prefers Python"
        static_result = Mock()
        static_result.memories = [static_mem]

        # Mock contextual search (second call)
        contextual_mem = Mock()
        contextual_mem.memory_item.content = "Last discussed async patterns"
        contextual_result = Mock()
        contextual_result.memories = [contextual_mem]
        contextual_result.search_id = "search-123"

        mock_project_client.memory_stores.search_memories.side_effect = [static_result, contextual_result]

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        await provider.before_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Check that memories were added to context
        assert provider.source_id in ctx.context_messages
        added = ctx.context_messages[provider.source_id]
        assert len(added) == 1
        assert "User prefers Python" in added[0].text  # type: ignore[operator]
        assert "Last discussed async patterns" in added[0].text  # type: ignore[operator]
        assert provider.context_prompt in added[0].text  # type: ignore[operator]
        assert session.state[provider.source_id]["previous_search_id"] == "search-123"

    async def test_empty_input_skips_contextual_search(self, mock_project_client: AsyncMock) -> None:
        """Empty input messages → only static search performed, no contextual search."""
        static_result = Mock()
        static_result.memories = []
        mock_project_client.memory_stores.search_memories.return_value = static_result

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="")], session_id="s1")

        await provider.before_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Should only call search_memories once for static memories
        assert mock_project_client.memory_stores.search_memories.call_count == 1
        assert provider.source_id not in ctx.context_messages

    async def test_empty_search_results_no_messages(self, mock_project_client: AsyncMock) -> None:
        """Empty search results → no messages added."""
        mock_search_result = Mock()
        mock_search_result.memories = []
        mock_project_client.memory_stores.search_memories.return_value = mock_search_result

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="test")], session_id="s1")

        await provider.before_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert provider.source_id not in ctx.context_messages

    async def test_static_memories_only_retrieved_once(self, mock_project_client: AsyncMock) -> None:
        """Static memories are only retrieved on the first call."""
        static_mem = Mock()
        static_mem.memory_item.content = "Static memory"
        static_result = Mock()
        static_result.memories = [static_mem]
        contextual_result = Mock()
        contextual_result.memories = []

        mock_project_client.memory_stores.search_memories.side_effect = [static_result, contextual_result]

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        # First call
        await provider.before_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )
        assert mock_project_client.memory_stores.search_memories.call_count == 2

        # Reset mock for second call
        mock_project_client.memory_stores.search_memories.reset_mock()
        contextual_result2 = Mock()
        contextual_result2.memories = []
        mock_project_client.memory_stores.search_memories.return_value = contextual_result2

        # Second call - should only search contextual, not static
        ctx2 = SessionContext(input_messages=[Message(role="user", text="World")], session_id="s1")
        await provider.before_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx2, state=session.state.setdefault(provider.source_id, {})
        )
        assert mock_project_client.memory_stores.search_memories.call_count == 1

    async def test_handles_search_exception_gracefully(self, mock_project_client: AsyncMock) -> None:
        """Search exception is logged but doesn't fail the operation."""
        mock_project_client.memory_stores.search_memories.side_effect = Exception("API error")

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="Hello")], session_id="s1")

        # Should not raise exception
        await provider.before_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # No memories added
        assert provider.source_id not in ctx.context_messages


# -- after_run tests -----------------------------------------------------------


class TestAfterRun:
    """Test after_run hook."""

    async def test_stores_input_and_response(self, mock_project_client: AsyncMock) -> None:
        """Stores input+response messages via begin_update_memories."""
        mock_poller = Mock()
        mock_poller.update_id = "update-456"
        mock_project_client.memory_stores.begin_update_memories.return_value = mock_poller

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="question")], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="answer")])

        await provider.after_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        mock_project_client.memory_stores.begin_update_memories.assert_awaited_once()
        call_kwargs = mock_project_client.memory_stores.begin_update_memories.call_args.kwargs
        assert call_kwargs["name"] == "test_store"
        assert call_kwargs["scope"] == "user_123"
        assert len(call_kwargs["items"]) == 2
        assert call_kwargs["items"][0]["content"] == "question"
        assert call_kwargs["items"][1]["content"] == "answer"
        assert session.state[provider.source_id]["previous_update_id"] == "update-456"

    async def test_only_stores_user_assistant_system(self, mock_project_client: AsyncMock) -> None:
        """Only stores user/assistant/system messages with text."""
        mock_poller = Mock()
        mock_project_client.memory_stores.begin_update_memories.return_value = mock_poller

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", text="hello"),
                Message(role="tool", text="tool output"),
            ],
            session_id="s1",
        )
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="reply")])

        await provider.after_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        call_kwargs = mock_project_client.memory_stores.begin_update_memories.call_args.kwargs
        items = call_kwargs["items"]
        assert len(items) == 2
        assert items[0]["content"] == "hello"
        assert items[1]["content"] == "reply"

    async def test_skips_empty_messages(self, mock_project_client: AsyncMock) -> None:
        """Skips messages with empty text."""
        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", text=""),
                Message(role="user", text="   "),
            ],
            session_id="s1",
        )
        ctx._response = AgentResponse(messages=[])

        await provider.after_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        mock_project_client.memory_stores.begin_update_memories.assert_not_awaited()

    async def test_uses_configured_update_delay(self, mock_project_client: AsyncMock) -> None:
        """Uses the configured update_delay parameter."""
        mock_poller = Mock()
        mock_project_client.memory_stores.begin_update_memories.return_value = mock_poller

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
            update_delay=60,
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="hi")], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="hey")])

        await provider.after_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        call_kwargs = mock_project_client.memory_stores.begin_update_memories.call_args.kwargs
        assert call_kwargs["update_delay"] == 60

    async def test_uses_previous_update_id_for_incremental_updates(self, mock_project_client: AsyncMock) -> None:
        """Uses previous_update_id for incremental updates."""
        mock_poller1 = Mock()
        mock_poller1.update_id = "update-1"
        mock_poller2 = Mock()
        mock_poller2.update_id = "update-2"

        mock_project_client.memory_stores.begin_update_memories.side_effect = [mock_poller1, mock_poller2]

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx1 = SessionContext(input_messages=[Message(role="user", text="first")], session_id="s1")
        ctx1._response = AgentResponse(messages=[Message(role="assistant", text="response1")])

        # First update
        await provider.after_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx1, state=session.state.setdefault(provider.source_id, {})
        )
        assert session.state[provider.source_id]["previous_update_id"] == "update-1"

        # Second update should use previous_update_id
        ctx2 = SessionContext(input_messages=[Message(role="user", text="second")], session_id="s1")
        ctx2._response = AgentResponse(messages=[Message(role="assistant", text="response2")])

        await provider.after_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx2, state=session.state.setdefault(provider.source_id, {})
        )

        call_kwargs = mock_project_client.memory_stores.begin_update_memories.call_args.kwargs
        assert call_kwargs["previous_update_id"] == "update-1"
        assert session.state[provider.source_id]["previous_update_id"] == "update-2"

    async def test_handles_update_exception_gracefully(self, mock_project_client: AsyncMock) -> None:
        """Update exception is logged but doesn't fail the operation."""
        mock_project_client.memory_stores.begin_update_memories.side_effect = Exception("API error")

        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", text="hi")], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", text="hey")])

        # Should not raise exception
        await provider.after_run(  # type: ignore[arg-type]
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )


# -- Context manager tests -----------------------------------------------------


class TestContextManager:
    """Test __aenter__/__aexit__ delegation."""

    async def test_aenter_delegates_to_client(self, mock_project_client: AsyncMock) -> None:
        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        result = await provider.__aenter__()
        assert result is provider
        mock_project_client.__aenter__.assert_awaited_once()

    async def test_aexit_delegates_to_client(self, mock_project_client: AsyncMock) -> None:
        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        await provider.__aexit__(None, None, None)
        mock_project_client.__aexit__.assert_awaited_once()

    async def test_async_with_syntax(self, mock_project_client: AsyncMock) -> None:
        provider = FoundryMemoryProvider(
            project_client=mock_project_client,
            memory_store_name="test_store",
            scope="user_123",
        )
        async with provider as p:
            assert p is provider

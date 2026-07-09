# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false
# ruff: noqa: E402

"""Unit tests for CosmosMemoryContextProvider with mocked dependencies."""

from __future__ import annotations

import pytest

# The Agent Memory Toolkit requires Python 3.11+, so it is not installed on the 3.10 CI
# leg. Skip this module there (mirrors the github_copilot package's importorskip guard).
pytest.importorskip("azure.cosmos.agent_memory")

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.exceptions import SettingNotFoundError

from agent_framework_azure_cosmos_memory._context_provider import (
    DEFAULT_CONTEXT_PROMPT,
    CosmosMemoryContextProvider,
)

# The provider methods accept an ``agent`` implementing ``SupportsAgentRun`` but never
# use it in these tests, so a typed ``None`` stub keeps the call sites clean.
_STUB_AGENT: Any = None


@pytest.fixture
def mock_memory_client() -> AsyncMock:
    """Create a mock AsyncCosmosMemoryClient."""
    mock_client = AsyncMock()
    mock_client.search_cosmos = AsyncMock(return_value=[])
    mock_client.get_user_summary = AsyncMock(return_value=None)
    mock_client.add_cosmos = AsyncMock()
    mock_client.create_memory_store = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


# -- Initialization tests ------------------------------------------------------


class TestInit:
    """Test CosmosMemoryContextProvider initialization."""

    def test_init_with_all_params(self, mock_memory_client: AsyncMock) -> None:
        """Initialize with all parameters provided."""
        provider = CosmosMemoryContextProvider(
            source_id="test_memory",
            memory_client=mock_memory_client,
            top_k=10,
            min_confidence=0.8,
            memory_types=["fact", "episodic"],
            context_prompt="Custom prompt:",
            auto_extract=True,
        )

        assert provider.source_id == "test_memory"
        assert provider.top_k == 10
        assert provider.min_confidence == 0.8
        assert provider.memory_types == ["fact", "episodic"]
        assert provider.context_prompt == "Custom prompt:"
        assert provider.auto_extract is True
        assert provider.memory_client is mock_memory_client
        assert provider._should_close_client is False

    def test_init_default_values(self, mock_memory_client: AsyncMock) -> None:
        """Initialize with default values."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)

        assert provider.source_id == "cosmos_memory"
        assert provider.top_k == 5
        assert provider.min_confidence == 0.7
        assert provider.memory_types == ["fact", "procedural"]
        assert provider.context_prompt == DEFAULT_CONTEXT_PROMPT
        assert provider.auto_extract is True

    def test_init_creates_client_when_none(self) -> None:
        """When no client provided, creates AsyncCosmosMemoryClient with default credential."""
        with patch(
            "agent_framework_azure_cosmos_memory._context_provider.AsyncCosmosMemoryClient"
        ) as mock_client_class:
            mock_client_class.return_value = AsyncMock()

            provider = CosmosMemoryContextProvider(
                cosmos_endpoint="https://test.documents.azure.com:443/",
                cosmos_database="test_db",
                foundry_endpoint="https://test.ai.azure.com",
            )

            mock_client_class.assert_called_once()
            # With no explicit credential, the toolkit builds its own DefaultAzureCredential.
            _, kwargs = mock_client_class.call_args
            assert kwargs["use_default_credential"] is True
            assert "cosmos_credential" not in kwargs
            assert provider._should_close_client is True

    def test_init_wires_explicit_credential(self) -> None:
        """An explicit credential is passed to both Cosmos and AI Foundry, disabling default."""
        with patch(
            "agent_framework_azure_cosmos_memory._context_provider.AsyncCosmosMemoryClient"
        ) as mock_client_class:
            mock_client_class.return_value = AsyncMock()
            sentinel = MagicMock()

            CosmosMemoryContextProvider(
                cosmos_endpoint="https://test.documents.azure.com:443/",
                foundry_endpoint="https://test.ai.azure.com",
                credential=sentinel,
            )

            _, kwargs = mock_client_class.call_args
            assert kwargs["cosmos_credential"] is sentinel
            assert kwargs["ai_foundry_credential"] is sentinel
            assert kwargs["use_default_credential"] is False

    def test_init_raises_without_endpoints(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises SettingNotFoundError when the Cosmos endpoint is not provided."""
        for var in ("COSMOS_ENDPOINT", "COSMOS_DATABASE", "FOUNDRY_ENDPOINT", "EMBEDDING_MODEL", "CHAT_MODEL"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(SettingNotFoundError, match="cosmos_endpoint"):
            CosmosMemoryContextProvider()

    def test_init_raises_without_foundry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises SettingNotFoundError when the Foundry endpoint is not provided."""
        for var in ("COSMOS_ENDPOINT", "COSMOS_DATABASE", "FOUNDRY_ENDPOINT", "EMBEDDING_MODEL", "CHAT_MODEL"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(SettingNotFoundError, match="foundry_endpoint"):
            CosmosMemoryContextProvider(cosmos_endpoint="https://test.documents.azure.com:443/")

    def test_init_processor_config_forwarded_to_built_client(self) -> None:
        """processor_config is forwarded to the built client via cadence_thresholds."""
        with patch(
            "agent_framework_azure_cosmos_memory._context_provider.AsyncCosmosMemoryClient"
        ) as mock_client_class:
            mock_client_class.return_value = AsyncMock()

            CosmosMemoryContextProvider(
                cosmos_endpoint="https://test.documents.azure.com:443/",
                foundry_endpoint="https://test.ai.azure.com",
                processor_config={"FACT_EXTRACTION_EVERY_N": 10},
            )

            _, kwargs = mock_client_class.call_args
            assert kwargs["cadence_thresholds"] == {"FACT_EXTRACTION_EVERY_N": 10}

    def test_auto_extract_false_zeroes_extraction_cadence(self) -> None:
        """auto_extract=False forwards zeroed extraction/summary cadence to the built client."""
        with patch(
            "agent_framework_azure_cosmos_memory._context_provider.AsyncCosmosMemoryClient"
        ) as mock_client_class:
            mock_client_class.return_value = AsyncMock()

            CosmosMemoryContextProvider(
                cosmos_endpoint="https://test.documents.azure.com:443/",
                foundry_endpoint="https://test.ai.azure.com",
                auto_extract=False,
            )

            _, kwargs = mock_client_class.call_args
            assert kwargs["cadence_thresholds"] == {
                "FACT_EXTRACTION_EVERY_N": 0,
                "THREAD_SUMMARY_EVERY_N": 0,
                "USER_SUMMARY_EVERY_N": 0,
            }

    def test_default_cadence_thresholds_is_none(self) -> None:
        """With no cadence config, the built client receives cadence_thresholds=None (env/defaults)."""
        with patch(
            "agent_framework_azure_cosmos_memory._context_provider.AsyncCosmosMemoryClient"
        ) as mock_client_class:
            mock_client_class.return_value = AsyncMock()

            CosmosMemoryContextProvider(
                cosmos_endpoint="https://test.documents.azure.com:443/",
                foundry_endpoint="https://test.ai.azure.com",
            )

            _, kwargs = mock_client_class.call_args
            assert kwargs["cadence_thresholds"] is None

    def test_processor_config_with_supplied_client_raises(self, mock_memory_client: AsyncMock) -> None:
        """Cadence config cannot apply to a caller-supplied client, so combining them raises."""
        with pytest.raises(ValueError, match="processor_config"):
            CosmosMemoryContextProvider(
                memory_client=mock_memory_client, processor_config={"FACT_EXTRACTION_EVERY_N": 10}
            )

    def test_auto_extract_false_with_supplied_client_raises(self, mock_memory_client: AsyncMock) -> None:
        """auto_extract=False cannot apply to a caller-supplied client, so combining them raises."""
        with pytest.raises(ValueError, match="processor_config"):
            CosmosMemoryContextProvider(memory_client=mock_memory_client, auto_extract=False)


# -- before_run tests ----------------------------------------------------------


class TestBeforeRun:
    """Test before_run hook - memory retrieval and context injection."""

    async def test_retrieves_and_injects_memories(self, mock_memory_client: AsyncMock) -> None:
        """Searches for memories and injects them into context."""
        mock_memory_client.search_cosmos.return_value = [
            {"content": "User prefers Python", "memory_type": "fact", "confidence": 0.95},
            {"content": "User completed ML course", "memory_type": "episodic", "confidence": 0.85},
        ]

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["What do you know about me?"])], session_id="s1"
        )

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Verify search was called
        mock_memory_client.search_cosmos.assert_awaited_once()
        call_kwargs = mock_memory_client.search_cosmos.call_args.kwargs
        assert call_kwargs["user_id"] == "test-session"
        assert call_kwargs["search_terms"] == "What do you know about me?"
        assert call_kwargs["top_k"] == 5
        assert call_kwargs["memory_types"] == ["fact", "procedural"]
        assert call_kwargs["min_confidence"] == 0.7

        # Verify memories added to context
        assert "cosmos_memory" in ctx.context_messages
        added = ctx.context_messages["cosmos_memory"]
        assert len(added) == 1
        assert "User prefers Python" in added[0].text  # type: ignore
        assert "User completed ML course" in added[0].text  # type: ignore
        assert "0.95" in added[0].text  # type: ignore
        assert "0.85" in added[0].text  # type: ignore

    async def test_user_summary_injected_as_instruction(self, mock_memory_client: AsyncMock) -> None:
        """User summary is retrieved and injected as instruction."""
        mock_memory_client.search_cosmos.return_value = []
        # get_user_summary returns the Cosmos summary document (a dict) whose roll-up text
        # lives in the "content" field.
        mock_memory_client.get_user_summary.return_value = {
            "content": "Tech enthusiast, prefers concise answers",
            "type": "user_summary",
        }

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["Hello"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert len(ctx.instructions) == 1
        assert "User Profile:" in ctx.instructions[0]
        assert "Tech enthusiast" in ctx.instructions[0]

    async def test_empty_user_summary_dict_not_injected(self, mock_memory_client: AsyncMock) -> None:
        """A user summary document with empty content is not injected."""
        mock_memory_client.search_cosmos.return_value = []
        mock_memory_client.get_user_summary.return_value = {"content": "   ", "type": "user_summary"}

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["Hello"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert len(ctx.instructions) == 0

    async def test_no_user_summary_not_injected(self, mock_memory_client: AsyncMock) -> None:
        """No user summary (None) does not inject an instruction."""
        mock_memory_client.search_cosmos.return_value = []
        mock_memory_client.get_user_summary.return_value = None

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["Hello"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert len(ctx.instructions) == 0

    async def test_empty_input_skips_search(self, mock_memory_client: AsyncMock) -> None:
        """Empty input messages skip memory search."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=[""])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        mock_memory_client.search_cosmos.assert_not_awaited()
        assert "cosmos_memory" not in ctx.context_messages

    async def test_empty_search_results_no_injection(self, mock_memory_client: AsyncMock) -> None:
        """Empty search results don't inject messages."""
        mock_memory_client.search_cosmos.return_value = []

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert "cosmos_memory" not in ctx.context_messages

    async def test_uses_user_id_from_state(self, mock_memory_client: AsyncMock) -> None:
        """Uses user_id from the provider-scoped state if available."""
        mock_memory_client.search_cosmos.return_value = []

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        session.state.setdefault(provider.source_id, {})["user_id"] = "custom-user-123"
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        call_kwargs = mock_memory_client.search_cosmos.call_args.kwargs
        assert call_kwargs["user_id"] == "custom-user-123"

    async def test_search_failure_logs_warning(
        self, mock_memory_client: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Search failures are logged but don't raise."""
        mock_memory_client.search_cosmos.side_effect = Exception("Cosmos DB connection failed")

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test"])], session_id="s1")

        # Should not raise
        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert "Failed to retrieve memories" in caplog.text

    async def test_search_failure_does_not_block_user_summary(self, mock_memory_client: AsyncMock) -> None:
        """A search failure must not suppress user-summary injection (split error handling)."""
        mock_memory_client.search_cosmos.side_effect = Exception("search boom")
        mock_memory_client.get_user_summary.return_value = {"content": "Prefers concise answers"}

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        session.state.setdefault(provider.source_id, {})["user_id"] = "u1"
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Memories failed, but the user summary was still injected as an instruction.
        assert any("Prefers concise answers" in instr for instr in ctx.instructions)

    async def test_user_summary_failure_does_not_block_search(self, mock_memory_client: AsyncMock) -> None:
        """A user-summary failure must not suppress memory injection (split error handling)."""
        mock_memory_client.search_cosmos.return_value = [
            {"content": "User likes hiking", "memory_type": "fact", "confidence": 0.9}
        ]
        mock_memory_client.get_user_summary.side_effect = Exception("summary boom")

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        session.state.setdefault(provider.source_id, {})["user_id"] = "u1"
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        injected = ctx.context_messages[provider.source_id]
        assert any("User likes hiking" in m.text for m in injected)  # type: ignore[arg-type]

    async def test_falls_back_to_session_id_without_user_id(self, mock_memory_client: AsyncMock) -> None:
        """With no user_id in provider state, memory scopes to the session id."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="ephemeral-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test"])], session_id="s1")

        await provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Search used the session id as the fallback user id.
        assert mock_memory_client.search_cosmos.call_args.kwargs["user_id"] == "ephemeral-session"


# -- after_run tests -----------------------------------------------------------


class TestAfterRun:
    """Test after_run hook - conversation storage."""

    async def test_stores_input_and_response_messages(self, mock_memory_client: AsyncMock) -> None:
        """Stores both input and response messages."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["Hello assistant"])],
            session_id="s1",
        )
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["Hello! How can I help?"])])

        await provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert mock_memory_client.add_cosmos.await_count == 2
        calls = mock_memory_client.add_cosmos.await_args_list

        # Check input message stored
        assert calls[0].kwargs["role"] == "user"
        assert calls[0].kwargs["content"] == "Hello assistant"
        assert calls[0].kwargs["user_id"] == "test-session"
        assert calls[0].kwargs["thread_id"] == "test-session"

        # Check response message stored
        assert calls[1].kwargs["role"] == "agent"
        assert calls[1].kwargs["content"] == "Hello! How can I help?"

    async def test_assistant_role_mapped_to_agent(self, mock_memory_client: AsyncMock) -> None:
        """Agent Framework 'assistant' role is mapped to the toolkit's 'agent' role.

        The Agent Memory Toolkit's TurnRecord only accepts {user, agent, tool, system};
        storing 'assistant' raises a pydantic validation error.
        """
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["Hi"])],
            session_id="s1",
        )
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["Hello there"])])

        await provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        stored_roles = [c.kwargs["role"] for c in mock_memory_client.add_cosmos.await_args_list]
        assert stored_roles == ["user", "agent"]
        # No raw "assistant" role should ever be sent to the toolkit.
        assert "assistant" not in stored_roles

    async def test_uses_custom_user_and_thread_ids(self, mock_memory_client: AsyncMock) -> None:
        """Uses custom user_id and thread_id from state."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        scoped = session.state.setdefault(provider.source_id, {})
        scoped["user_id"] = "user-456"
        scoped["thread_id"] = "thread-789"
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["test"])],
            session_id="s1",
        )

        await provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        call_kwargs = mock_memory_client.add_cosmos.await_args_list[0].kwargs
        assert call_kwargs["user_id"] == "user-456"
        assert call_kwargs["thread_id"] == "thread-789"

    async def test_skips_empty_messages(self, mock_memory_client: AsyncMock) -> None:
        """Skips messages with no text content."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", contents=[""]),
                Message(role="user", contents=["Valid message"]),
            ],
            session_id="s1",
        )

        await provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Only one message should be stored
        assert mock_memory_client.add_cosmos.await_count == 1
        call_kwargs = mock_memory_client.add_cosmos.await_args_list[0].kwargs
        assert call_kwargs["content"] == "Valid message"

    async def test_skips_whitespace_only_messages(self, mock_memory_client: AsyncMock) -> None:
        """Whitespace-only turns are skipped and stored content is stripped."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", contents=["   "]),
                Message(role="user", contents=["  Trimmed message  "]),
            ],
            session_id="s1",
        )
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["\n\t "])])

        await provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        # Whitespace-only input and the whitespace-only response are both skipped.
        assert mock_memory_client.add_cosmos.await_count == 1
        call_kwargs = mock_memory_client.add_cosmos.await_args_list[0].kwargs
        assert call_kwargs["content"] == "Trimmed message"

    async def test_storage_failure_logs_warning(
        self, mock_memory_client: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Storage failures are logged but don't raise."""
        mock_memory_client.add_cosmos.side_effect = Exception("Storage failed")

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test"])], session_id="s1")

        # Should not raise
        await provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )

        assert "Failed to store conversation turns" in caplog.text


# -- Helper method tests -------------------------------------------------------


class TestFormatMemories:
    """Test _format_memories helper method."""

    def test_formats_with_type_and_confidence(self, mock_memory_client: AsyncMock) -> None:
        """Formats memories with type and confidence."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        memories = [
            {"content": "User likes Python", "memory_type": "fact", "confidence": 0.95},
            {"content": "User prefers vim", "memory_type": "procedural", "confidence": 0.82},
        ]

        result = provider._format_memories(memories)

        assert "[fact] User likes Python (confidence: 0.95)" in result
        assert "[procedural] User prefers vim (confidence: 0.82)" in result

    def test_formats_without_metadata(self, mock_memory_client: AsyncMock) -> None:
        """Formats memories without type/confidence metadata."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        memories = [{"content": "Some memory"}]

        result = provider._format_memories(memories)

        assert result == "Some memory"

    def test_formats_with_zero_confidence(self, mock_memory_client: AsyncMock) -> None:
        """A confidence of 0.0 is still shown (not treated as missing metadata)."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        memories = [{"content": "Edge fact", "memory_type": "fact", "confidence": 0.0}]

        result = provider._format_memories(memories)

        assert result == "[fact] Edge fact (confidence: 0.00)"

    def test_formats_with_string_confidence(self, mock_memory_client: AsyncMock) -> None:
        """A string confidence is coerced to float rather than raising."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        memories = [{"content": "Str fact", "memory_type": "fact", "confidence": "0.5"}]

        result = provider._format_memories(memories)

        assert result == "[fact] Str fact (confidence: 0.50)"


# -- Context manager tests -----------------------------------------------------


class TestContextManager:
    """Test async context manager protocol."""

    async def test_enters_and_exits_client(self, mock_memory_client: AsyncMock) -> None:
        """Enters and exits the memory client when provider owns it."""
        # When provider creates the client, it should manage its lifecycle
        with patch(
            "agent_framework_azure_cosmos_memory._context_provider.AsyncCosmosMemoryClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            provider = CosmosMemoryContextProvider(
                cosmos_endpoint="https://test.documents.azure.com:443/",
                foundry_endpoint="https://test.ai.azure.com",
            )

            async with provider:
                pass

            mock_client.__aenter__.assert_awaited_once()
            mock_client.__aexit__.assert_awaited_once()

    async def test_provided_client_not_closed(self, mock_memory_client: AsyncMock) -> None:
        """When client is provided externally, provider should not close it."""
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)

        async with provider:
            pass

        # Should still enter the client
        mock_memory_client.__aenter__.assert_awaited_once()
        # But should NOT exit it (caller owns it)
        mock_memory_client.__aexit__.assert_not_awaited()

    async def test_aenter_creates_memory_store(self, mock_memory_client: AsyncMock) -> None:
        """Entering the provider creates/connects the Cosmos memory store.

        The async client cannot create or connect Cosmos containers in __init__
        (no running event loop), so the provider must call create_memory_store()
        on entry. Without this, add_cosmos/search_cosmos raise CosmosNotConnectedError
        and no containers are ever created.
        """
        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)

        async with provider:
            pass

        mock_memory_client.create_memory_store.assert_awaited_once()


class TestFlush:
    """Test flush() draining of pending background extraction tasks."""

    async def test_flush_waits_for_pending_tasks(self, mock_memory_client: AsyncMock) -> None:
        """flush() awaits in-flight background tasks so extraction can complete."""
        import asyncio

        completed = False

        async def _work() -> None:
            nonlocal completed
            await asyncio.sleep(0.01)
            completed = True

        task = asyncio.ensure_future(_work())
        mock_memory_client._background_tasks = {task}

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        await provider.flush()

        assert task.done()
        assert completed is True

    async def test_flush_no_tasks_is_noop(self, mock_memory_client: AsyncMock) -> None:
        """flush() returns cleanly when there are no background tasks."""
        mock_memory_client._background_tasks = set()

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        # Should not raise.
        await provider.flush()

    async def test_flush_handles_missing_attribute(self, mock_memory_client: AsyncMock) -> None:
        """flush() is a no-op if the client exposes no background-task registry."""
        # Simulate a client without a usable background-task registry.
        mock_memory_client._background_tasks = None

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        # Should not raise.
        await provider.flush()

    async def test_only_closes_owned_client(self) -> None:
        """Only closes client if provider created it."""
        with patch(
            "agent_framework_azure_cosmos_memory._context_provider.AsyncCosmosMemoryClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            provider = CosmosMemoryContextProvider(
                cosmos_endpoint="https://test.documents.azure.com:443/",
                foundry_endpoint="https://test.ai.azure.com",
            )

            assert provider._should_close_client is True

            async with provider:
                pass

            mock_client.__aenter__.assert_awaited_once()
            mock_client.__aexit__.assert_awaited_once()


class TestCustomPromptsDir:
    """The ``prompts_dir`` option redirects the toolkit pipeline's Prompty template loader."""

    async def test_prompts_dir_redirects_pipeline_loader(self, mock_memory_client: AsyncMock) -> None:
        """Entering the provider points the pipeline's Prompty loader at the custom directory."""
        mock_pipeline = MagicMock()
        # _get_pipeline is synchronous on the toolkit client; return our stand-in pipeline.
        mock_memory_client._get_pipeline = MagicMock(return_value=mock_pipeline)

        provider = CosmosMemoryContextProvider(
            memory_client=mock_memory_client,
            prompts_dir="/custom/prompts",
        )
        async with provider:
            pass

        from azure.cosmos.agent_memory.services._pipeline_helpers import PromptyLoader

        mock_memory_client._get_pipeline.assert_called_once()
        assert isinstance(mock_pipeline._prompty, PromptyLoader)
        assert mock_pipeline._prompty.prompts_dir == "/custom/prompts"

    async def test_no_prompts_dir_leaves_pipeline_untouched(self, mock_memory_client: AsyncMock) -> None:
        """Without ``prompts_dir`` the provider never builds or touches the pipeline loader."""
        mock_memory_client._get_pipeline = MagicMock()

        provider = CosmosMemoryContextProvider(memory_client=mock_memory_client)
        async with provider:
            pass

        mock_memory_client._get_pipeline.assert_not_called()

# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

import os
from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.exceptions import ServiceInitializationError, SettingNotFoundError

from agent_framework_azure_ai_search._context_provider import AzureAISearchContextProvider

# -- Helpers -------------------------------------------------------------------


class MockSearchResults:
    """Async-iterable mock for Azure SearchClient.search() results."""

    def __init__(self, docs: list[dict]):
        self._docs = docs
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return doc


@pytest.fixture
def mock_search_client() -> AsyncMock:
    """Create a mock SearchClient that returns one document."""
    client = AsyncMock()

    async def _search(**kwargs):
        return MockSearchResults([{"id": "doc1", "content": "test document"}])

    client.search = AsyncMock(side_effect=_search)
    return client


@pytest.fixture
def mock_search_client_empty() -> AsyncMock:
    """Create a mock SearchClient that returns no results."""
    client = AsyncMock()

    async def _search(**kwargs):
        return MockSearchResults([])

    client.search = AsyncMock(side_effect=_search)
    return client


def _make_provider(**overrides) -> AzureAISearchContextProvider:
    """Create a semantic-mode provider with mocked internals (skips auto-discovery)."""
    defaults = {
        "source_id": AzureAISearchContextProvider.DEFAULT_SOURCE_ID,
        "endpoint": "https://test.search.windows.net",
        "index_name": "test-index",
        "api_key": "test-key",
    }
    defaults.update(overrides)
    provider = AzureAISearchContextProvider(**defaults)
    provider._auto_discovered_vector_field = True  # skip auto-discovery
    return provider


# -- Initialization: semantic mode ---------------------------------------------


class TestInitSemantic:
    """Initialization tests for semantic mode."""

    def test_valid_init(self) -> None:
        provider = _make_provider()
        assert provider.source_id == AzureAISearchContextProvider.DEFAULT_SOURCE_ID
        assert provider.endpoint == "https://test.search.windows.net"
        assert provider.index_name == "test-index"
        assert provider.mode == "semantic"

    def test_source_id_set(self) -> None:
        provider = _make_provider(source_id="my-source")
        assert provider.source_id == "my-source"

    def test_missing_endpoint_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True), pytest.raises(SettingNotFoundError, match="endpoint"):
            AzureAISearchContextProvider(
                source_id="s",
                endpoint=None,
                index_name="idx",
                api_key="key",
            )

    def test_missing_index_name_semantic_raises(self) -> None:
        with pytest.raises(SettingNotFoundError, match="index_name"):
            AzureAISearchContextProvider(
                source_id="s",
                endpoint="https://test.search.windows.net",
                index_name=None,
                api_key="key",
            )

    def test_env_variable_fallback(self) -> None:
        env = {
            "AZURE_SEARCH_ENDPOINT": "https://env.search.windows.net",
            "AZURE_SEARCH_INDEX_NAME": "env-index",
            "AZURE_SEARCH_API_KEY": "env-key",
        }
        with patch.dict(os.environ, env, clear=False):
            provider = AzureAISearchContextProvider(source_id="env-test")
            assert provider.endpoint == "https://env.search.windows.net"
            assert provider.index_name == "env-index"


# -- Initialization: agentic mode validation -----------------------------------


class TestInitAgenticValidation:
    """Initialization validation tests for agentic mode."""

    def test_both_index_and_kb_raises(self) -> None:
        with pytest.raises(SettingNotFoundError, match="multiple were set"):
            AzureAISearchContextProvider(
                source_id="s",
                endpoint="https://test.search.windows.net",
                index_name="idx",
                knowledge_base_name="kb",
                api_key="key",
                mode="agentic",
                model_deployment_name="deploy",
                azure_openai_resource_url="https://aoai.openai.azure.com",
            )

    def test_neither_index_nor_kb_raises(self) -> None:
        with pytest.raises(SettingNotFoundError, match="none was set"):
            AzureAISearchContextProvider(
                source_id="s",
                endpoint="https://test.search.windows.net",
                api_key="key",
                mode="agentic",
            )

    def test_missing_model_deployment_name_raises(self) -> None:
        with pytest.raises(ServiceInitializationError, match="model_deployment_name"):
            AzureAISearchContextProvider(
                source_id="s",
                endpoint="https://test.search.windows.net",
                index_name="idx",
                api_key="key",
                mode="agentic",
                azure_openai_resource_url="https://aoai.openai.azure.com",
            )

    def test_vector_field_without_embedding_raises(self) -> None:
        with pytest.raises(ValueError, match="embedding_function"):
            AzureAISearchContextProvider(
                source_id="s",
                endpoint="https://test.search.windows.net",
                index_name="idx",
                api_key="key",
                vector_field_name="embedding",
            )


# -- before_run: semantic mode -------------------------------------------------


class TestBeforeRunSemantic:
    """Tests for before_run in semantic mode."""

    async def test_results_added_to_context(self, mock_search_client: AsyncMock) -> None:
        provider = _make_provider()
        provider._search_client = mock_search_client

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["test query"])],
            session_id="s1",
        )
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_search_client.search.assert_awaited_once()
        msgs = ctx.context_messages.get(provider.source_id, [])
        assert len(msgs) >= 2  # context_prompt + at least one result
        assert msgs[0].text == provider.context_prompt

    async def test_empty_input_no_search(self, mock_search_client: AsyncMock) -> None:
        provider = _make_provider()
        provider._search_client = mock_search_client

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[], session_id="s1")
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_search_client.search.assert_not_awaited()
        assert ctx.context_messages.get(provider.source_id) is None

    async def test_no_results_no_messages(self, mock_search_client_empty: AsyncMock) -> None:
        provider = _make_provider()
        provider._search_client = mock_search_client_empty

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["test query"])],
            session_id="s1",
        )
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_search_client_empty.search.assert_awaited_once()
        assert ctx.context_messages.get(provider.source_id) is None

    async def test_context_prompt_prepended(self, mock_search_client: AsyncMock) -> None:
        custom_prompt = "Custom search context:"
        provider = _make_provider(context_prompt=custom_prompt)
        provider._search_client = mock_search_client

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["test query"])],
            session_id="s1",
        )
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        msgs = ctx.context_messages[provider.source_id]
        assert msgs[0].text == custom_prompt


# -- before_run: message filtering ---------------------------------------------


class TestBeforeRunFiltering:
    """Tests that only user/assistant messages are used for search."""

    async def test_filters_non_user_assistant(self, mock_search_client: AsyncMock) -> None:
        provider = _make_provider()
        provider._search_client = mock_search_client

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="system", contents=["system prompt"]),
                Message(role="user", contents=["actual question"]),
            ],
            session_id="s1",
        )
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_search_client.search.assert_awaited_once()
        call_kwargs = mock_search_client.search.call_args[1]
        # The search text should contain only the user message, not the system message
        assert "actual question" in call_kwargs["search_text"]
        assert "system prompt" not in call_kwargs["search_text"]

    async def test_only_system_messages_no_search(self, mock_search_client: AsyncMock) -> None:
        provider = _make_provider()
        provider._search_client = mock_search_client

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="system", contents=["system prompt"])],
            session_id="s1",
        )
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_search_client.search.assert_not_awaited()


# -- __aexit__ -----------------------------------------------------------------


class TestAexit:
    """Tests for async context manager cleanup."""

    async def test_closes_retrieval_client(self) -> None:
        provider = _make_provider()
        mock_retrieval = AsyncMock()
        provider._retrieval_client = mock_retrieval

        await provider.__aexit__(None, None, None)

        mock_retrieval.close.assert_awaited_once()
        assert provider._retrieval_client is None

    async def test_no_retrieval_client_no_error(self) -> None:
        provider = _make_provider()
        assert provider._retrieval_client is None

        await provider.__aexit__(None, None, None)  # should not raise

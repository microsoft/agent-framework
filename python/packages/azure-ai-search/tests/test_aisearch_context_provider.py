# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from agent_framework import Content, Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.exceptions import SettingNotFoundError
from azure.core.credentials import AzureKeyCredential

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


def _make_mock_index(
    fields: list[SimpleNamespace] | None = None,
    profiles: list[SimpleNamespace] | None = None,
    has_vector_search: bool = True,
) -> SimpleNamespace:
    """Create a mock search index with the given fields and vector search profiles."""
    vector_search = None
    if has_vector_search:
        vector_search = SimpleNamespace(profiles=profiles or [])
    return SimpleNamespace(fields=fields or [], vector_search=vector_search)


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

    def test_top_k_and_semantic_config(self) -> None:
        provider = _make_provider(top_k=10, semantic_configuration_name="my-config")
        assert provider.top_k == 10
        assert provider.semantic_configuration_name == "my-config"

    def test_default_context_prompt(self) -> None:
        provider = _make_provider()
        assert provider.context_prompt == AzureAISearchContextProvider._DEFAULT_SEARCH_CONTEXT_PROMPT

    def test_custom_context_prompt(self) -> None:
        provider = _make_provider(context_prompt="Custom prompt:")
        assert provider.context_prompt == "Custom prompt:"

    def test_model_name_falls_back_to_deployment_name(self) -> None:
        """model_name defaults to model_deployment_name when not explicitly set."""
        provider = _make_provider(model_deployment_name="my-deploy")
        assert provider.model_name == "my-deploy"

    def test_model_name_explicit(self) -> None:
        provider = _make_provider(model_deployment_name="deploy", model_name="gpt-4")
        assert provider.model_name == "gpt-4"


# -- Initialization: credential resolution ------------------------------------


class TestInitCredentialResolution:
    """Tests for credential resolution paths."""

    def test_token_credential_used(self) -> None:
        mock_cred = AsyncMock()
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="idx",
            credential=mock_cred,
        )
        provider._auto_discovered_vector_field = True
        assert provider.credential is mock_cred

    def test_azure_key_credential_passed_through(self) -> None:
        akc = AzureKeyCredential("my-key")
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="idx",
            api_key=akc,
        )
        provider._auto_discovered_vector_field = True
        assert provider.credential is akc

    def test_no_credential_raises(self) -> None:
        with pytest.raises(ValueError, match="Azure credential is required"):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="idx",
            )


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
        with pytest.raises(ValueError, match="model_deployment_name"):
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

    def test_agentic_missing_aoai_url_with_index_raises(self) -> None:
        with pytest.raises(ValueError, match="azure_openai_resource_url"):
            AzureAISearchContextProvider(
                source_id="s",
                endpoint="https://test.search.windows.net",
                index_name="idx",
                api_key="key",
                mode="agentic",
                model_deployment_name="deploy",
            )

    def test_agentic_with_kb_name_sets_use_existing(self) -> None:
        provider = AzureAISearchContextProvider(
            source_id="s",
            endpoint="https://test.search.windows.net",
            knowledge_base_name="my-kb",
            api_key="key",
            mode="agentic",
        )
        assert provider._use_existing_knowledge_base is True
        assert provider.knowledge_base_name == "my-kb"

    def test_agentic_with_index_generates_kb_name(self) -> None:
        provider = AzureAISearchContextProvider(
            source_id="s",
            endpoint="https://test.search.windows.net",
            index_name="idx",
            api_key="key",
            mode="agentic",
            model_deployment_name="deploy",
            azure_openai_resource_url="https://aoai.openai.azure.com",
        )
        assert provider._use_existing_knowledge_base is False
        assert provider.knowledge_base_name == "idx-kb"


# -- __aenter__ / __aexit__ ---------------------------------------------------


class TestAsyncContextManager:
    """Tests for async context manager."""

    async def test_aenter_returns_self(self) -> None:
        provider = _make_provider()
        result = await provider.__aenter__()
        assert result is provider

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

    async def test_whitespace_only_messages_filtered(self, mock_search_client: AsyncMock) -> None:
        provider = _make_provider()
        provider._search_client = mock_search_client

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["   "])],
            session_id="s1",
        )
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_search_client.search.assert_not_awaited()

    async def test_assistant_messages_included(self, mock_search_client: AsyncMock) -> None:
        provider = _make_provider()
        provider._search_client = mock_search_client

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[
                Message(role="user", contents=["first question"]),
                Message(role="assistant", contents=["first answer"]),
                Message(role="user", contents=["follow up"]),
            ],
            session_id="s1",
        )
        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        call_kwargs = mock_search_client.search.call_args[1]
        assert "first question" in call_kwargs["search_text"]
        assert "first answer" in call_kwargs["search_text"]
        assert "follow up" in call_kwargs["search_text"]


# -- _find_vector_fields -------------------------------------------------------


class TestFindVectorFields:
    """Tests for _find_vector_fields helper."""

    def test_finds_fields_with_dimensions(self) -> None:
        provider = _make_provider()
        index = _make_mock_index(
            fields=[
                SimpleNamespace(name="embedding", vector_search_dimensions=1536),
                SimpleNamespace(name="content", vector_search_dimensions=None),
                SimpleNamespace(name="title", vector_search_dimensions=0),
            ]
        )
        result = provider._find_vector_fields(index)
        assert result == ["embedding"]

    def test_returns_empty_for_no_vector_fields(self) -> None:
        provider = _make_provider()
        index = _make_mock_index(
            fields=[
                SimpleNamespace(name="content", vector_search_dimensions=None),
                SimpleNamespace(name="title", vector_search_dimensions=0),
            ]
        )
        result = provider._find_vector_fields(index)
        assert result == []

    def test_multiple_vector_fields(self) -> None:
        provider = _make_provider()
        index = _make_mock_index(
            fields=[
                SimpleNamespace(name="emb1", vector_search_dimensions=768),
                SimpleNamespace(name="emb2", vector_search_dimensions=1536),
            ]
        )
        result = provider._find_vector_fields(index)
        assert result == ["emb1", "emb2"]


# -- _find_vectorizable_fields ------------------------------------------------


class TestFindVectorizableFields:
    """Tests for _find_vectorizable_fields helper."""

    def test_finds_vectorizable_fields(self) -> None:
        provider = _make_provider()
        profiles = [SimpleNamespace(name="profile1", vectorizer_name="my-vectorizer")]
        fields = [
            SimpleNamespace(name="embedding", vector_search_dimensions=1536, vector_search_profile_name="profile1"),
        ]
        index = _make_mock_index(fields=fields, profiles=profiles)
        result = provider._find_vectorizable_fields(index, ["embedding"])
        assert result == ["embedding"]

    def test_returns_empty_when_no_vector_search(self) -> None:
        provider = _make_provider()
        index = _make_mock_index(has_vector_search=False)
        result = provider._find_vectorizable_fields(index, ["embedding"])
        assert result == []

    def test_returns_empty_when_no_profiles(self) -> None:
        provider = _make_provider()
        index = _make_mock_index(profiles=None)
        index.vector_search = SimpleNamespace(profiles=None)
        result = provider._find_vectorizable_fields(index, ["embedding"])
        assert result == []

    def test_field_not_in_vector_fields_excluded(self) -> None:
        provider = _make_provider()
        profiles = [SimpleNamespace(name="profile1", vectorizer_name="my-vectorizer")]
        fields = [
            SimpleNamespace(name="other_field", vector_search_dimensions=1536, vector_search_profile_name="profile1"),
        ]
        index = _make_mock_index(fields=fields, profiles=profiles)
        result = provider._find_vectorizable_fields(index, ["embedding"])
        assert result == []

    def test_profile_without_vectorizer_not_included(self) -> None:
        provider = _make_provider()
        profiles = [SimpleNamespace(name="profile1", vectorizer_name=None)]
        fields = [
            SimpleNamespace(name="embedding", vector_search_dimensions=1536, vector_search_profile_name="profile1"),
        ]
        index = _make_mock_index(fields=fields, profiles=profiles)
        result = provider._find_vectorizable_fields(index, ["embedding"])
        assert result == []

    def test_field_without_profile_name_excluded(self) -> None:
        provider = _make_provider()
        profiles = [SimpleNamespace(name="profile1", vectorizer_name="my-vectorizer")]
        fields = [
            SimpleNamespace(name="embedding", vector_search_dimensions=1536, vector_search_profile_name=None),
        ]
        index = _make_mock_index(fields=fields, profiles=profiles)
        result = provider._find_vectorizable_fields(index, ["embedding"])
        assert result == []


# -- _auto_discover_vector_field -----------------------------------------------


class TestAutoDiscoverVectorField:
    """Tests for _auto_discover_vector_field."""

    async def test_skip_if_already_discovered(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = True
        await provider._auto_discover_vector_field()
        # No error, no side effects

    async def test_skip_if_vector_field_set(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        provider.vector_field_name = "my_field"
        await provider._auto_discover_vector_field()
        # Should return immediately

    async def test_no_index_name_warns(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        provider.index_name = None
        provider._index_client = AsyncMock()

        await provider._auto_discover_vector_field()
        assert provider._auto_discovered_vector_field is True

    async def test_no_vector_fields_sets_flag(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        mock_index_client = AsyncMock()
        mock_index_client.get_index.return_value = _make_mock_index(
            fields=[SimpleNamespace(name="content", vector_search_dimensions=None)]
        )
        provider._index_client = mock_index_client

        await provider._auto_discover_vector_field()
        assert provider._auto_discovered_vector_field is True
        assert provider.vector_field_name is None

    async def test_single_vectorizable_field_discovered(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        profiles = [SimpleNamespace(name="profile1", vectorizer_name="my-vectorizer")]
        fields = [
            SimpleNamespace(name="embedding", vector_search_dimensions=1536, vector_search_profile_name="profile1"),
        ]
        mock_index_client = AsyncMock()
        mock_index_client.get_index.return_value = _make_mock_index(fields=fields, profiles=profiles)
        provider._index_client = mock_index_client

        await provider._auto_discover_vector_field()
        assert provider.vector_field_name == "embedding"
        assert provider._use_vectorizable_query is True
        assert provider._auto_discovered_vector_field is True

    async def test_multiple_vectorizable_fields_warns(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        profiles = [
            SimpleNamespace(name="profile1", vectorizer_name="v1"),
            SimpleNamespace(name="profile2", vectorizer_name="v2"),
        ]
        fields = [
            SimpleNamespace(name="emb1", vector_search_dimensions=768, vector_search_profile_name="profile1"),
            SimpleNamespace(name="emb2", vector_search_dimensions=1536, vector_search_profile_name="profile2"),
        ]
        mock_index_client = AsyncMock()
        mock_index_client.get_index.return_value = _make_mock_index(fields=fields, profiles=profiles)
        provider._index_client = mock_index_client

        await provider._auto_discover_vector_field()
        assert provider._auto_discovered_vector_field is True
        # vector_field_name should not be set when multiple found
        assert provider.vector_field_name is None

    async def test_single_vector_field_without_embedding_clears_field(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        provider.embedding_function = None
        fields = [
            SimpleNamespace(name="embedding", vector_search_dimensions=1536, vector_search_profile_name=None),
        ]
        mock_index_client = AsyncMock()
        mock_index_client.get_index.return_value = _make_mock_index(fields=fields, profiles=[])
        provider._index_client = mock_index_client

        await provider._auto_discover_vector_field()
        assert provider._auto_discovered_vector_field is True
        assert provider.vector_field_name is None

    async def test_single_vector_field_with_embedding_function(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        provider.embedding_function = AsyncMock(return_value=[0.1] * 1536)
        fields = [
            SimpleNamespace(name="embedding", vector_search_dimensions=1536, vector_search_profile_name=None),
        ]
        mock_index_client = AsyncMock()
        mock_index_client.get_index.return_value = _make_mock_index(fields=fields, profiles=[])
        provider._index_client = mock_index_client

        await provider._auto_discover_vector_field()
        assert provider.vector_field_name == "embedding"
        assert provider._use_vectorizable_query is False

    async def test_multiple_vector_fields_no_vectorizable_warns(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        fields = [
            SimpleNamespace(name="emb1", vector_search_dimensions=768, vector_search_profile_name=None),
            SimpleNamespace(name="emb2", vector_search_dimensions=1536, vector_search_profile_name=None),
        ]
        mock_index_client = AsyncMock()
        mock_index_client.get_index.return_value = _make_mock_index(fields=fields, profiles=[])
        provider._index_client = mock_index_client

        await provider._auto_discover_vector_field()
        assert provider._auto_discovered_vector_field is True
        assert provider.vector_field_name is None

    async def test_exception_falls_back_to_keyword_search(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        mock_index_client = AsyncMock()
        mock_index_client.get_index.side_effect = Exception("network error")
        provider._index_client = mock_index_client

        await provider._auto_discover_vector_field()
        assert provider._auto_discovered_vector_field is True

    async def test_creates_index_client_if_none(self) -> None:
        provider = _make_provider()
        provider._auto_discovered_vector_field = False
        provider._index_client = None

        with patch("agent_framework_azure_ai_search._context_provider.SearchIndexClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_index.return_value = _make_mock_index(
                fields=[SimpleNamespace(name="content", vector_search_dimensions=None)]
            )
            mock_cls.return_value = mock_client

            await provider._auto_discover_vector_field()
            mock_cls.assert_called_once()
            assert provider._auto_discovered_vector_field is True


# -- _semantic_search ----------------------------------------------------------


class TestSemanticSearch:
    """Tests for _semantic_search method."""

    async def test_basic_keyword_search(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()

        async def _search(**kwargs):
            return MockSearchResults([{"id": "d1", "content": "result text"}])

        mock_client.search = AsyncMock(side_effect=_search)
        provider._search_client = mock_client

        results = await provider._semantic_search("test query")
        assert len(results) == 1
        assert "result text" in results[0].text
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["search_text"] == "test query"

    async def test_vectorizable_text_query(self) -> None:
        provider = _make_provider()
        provider._use_vectorizable_query = True
        provider.vector_field_name = "embedding"
        mock_client = AsyncMock()

        async def _search(**kwargs):
            return MockSearchResults([{"id": "d1", "content": "vector result"}])

        mock_client.search = AsyncMock(side_effect=_search)
        provider._search_client = mock_client

        results = await provider._semantic_search("vector query")
        assert len(results) == 1
        call_kwargs = mock_client.search.call_args[1]
        assert "vector_queries" in call_kwargs
        assert len(call_kwargs["vector_queries"]) == 1

    async def test_vectorized_query_with_embedding_function(self) -> None:
        provider = _make_provider()
        provider._use_vectorizable_query = False
        provider.vector_field_name = "embedding"

        async def _embed(query: str) -> list[float]:
            return [0.1, 0.2, 0.3]

        provider.embedding_function = _embed
        mock_client = AsyncMock()

        async def _search(**kwargs):
            return MockSearchResults([{"id": "d1", "content": "embed result"}])

        mock_client.search = AsyncMock(side_effect=_search)
        provider._search_client = mock_client

        results = await provider._semantic_search("embed query")
        assert len(results) == 1
        call_kwargs = mock_client.search.call_args[1]
        assert "vector_queries" in call_kwargs

    async def test_semantic_configuration_params(self) -> None:
        provider = _make_provider(semantic_configuration_name="my-semantic-config")
        mock_client = AsyncMock()

        async def _search(**kwargs):
            return MockSearchResults([{"id": "d1", "content": "semantic result"}])

        mock_client.search = AsyncMock(side_effect=_search)
        provider._search_client = mock_client

        await provider._semantic_search("sem query")
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["query_type"] == "semantic"
        assert call_kwargs["semantic_configuration_name"] == "my-semantic-config"
        assert "query_caption" in call_kwargs

    async def test_vector_k_with_semantic_config(self) -> None:
        provider = _make_provider(semantic_configuration_name="sc", top_k=3)
        provider._use_vectorizable_query = True
        provider.vector_field_name = "embedding"
        mock_client = AsyncMock()

        async def _search(**kwargs):
            return MockSearchResults([])

        mock_client.search = AsyncMock(side_effect=_search)
        provider._search_client = mock_client

        await provider._semantic_search("query")
        call_kwargs = mock_client.search.call_args[1]
        assert "vector_queries" in call_kwargs
        assert len(call_kwargs["vector_queries"]) == 1

    async def test_no_search_client_raises(self) -> None:
        provider = _make_provider()
        provider._search_client = None

        with pytest.raises(RuntimeError, match="Search client is not initialized"):
            await provider._semantic_search("query")

    async def test_empty_results_returns_empty_list(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()

        async def _search(**kwargs):
            return MockSearchResults([])

        mock_client.search = AsyncMock(side_effect=_search)
        provider._search_client = mock_client

        results = await provider._semantic_search("query")
        assert results == []

    async def test_doc_without_text_excluded(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()

        async def _search(**kwargs):
            # doc with only @search metadata and id - no extractable text
            return MockSearchResults([{"id": "d1", "@search.score": 0.9}])

        mock_client.search = AsyncMock(side_effect=_search)
        provider._search_client = mock_client

        results = await provider._semantic_search("query")
        assert results == []


# -- _extract_document_text ----------------------------------------------------


class TestExtractDocumentText:
    """Tests for _extract_document_text."""

    def test_content_field_extracted(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"content": "Hello world"}, doc_id="d1")
        assert result == "[Source: d1] Hello world"

    def test_text_field_extracted(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"text": "Some text"}, doc_id="d1")
        assert result == "[Source: d1] Some text"

    def test_description_field_extracted(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"description": "A description"}, doc_id="d1")
        assert result == "[Source: d1] A description"

    def test_body_field_extracted(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"body": "Body content"}, doc_id="d1")
        assert result == "[Source: d1] Body content"

    def test_chunk_field_extracted(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"chunk": "Chunk data"}, doc_id="d1")
        assert result == "[Source: d1] Chunk data"

    def test_content_field_priority(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text(
            {"content": "Primary", "text": "Secondary", "description": "Tertiary"}, doc_id="d1"
        )
        assert result == "[Source: d1] Primary"

    def test_fallback_to_string_fields(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text(
            {"title": "My Title", "summary": "My Summary", "id": "skip-this", "@search.score": "skip-meta"},
            doc_id="d1",
        )
        assert "title: My Title" in result
        assert "summary: My Summary" in result
        assert "id" not in result.split("] ")[1]  # id should be excluded from fallback
        assert "@search.score" not in result

    def test_empty_doc_returns_empty(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({})
        assert result == ""

    def test_no_doc_id_returns_text_only(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"content": "Hello"}, doc_id=None)
        assert result == "Hello"

    def test_search_id_fallback(self) -> None:
        """Test that doc results using @search.id work too (via before_run path)."""
        provider = _make_provider()
        result = provider._extract_document_text({"content": "data"}, doc_id="alt-id")
        assert result == "[Source: alt-id] data"

    def test_only_id_and_metadata_returns_empty(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"id": "d1", "@search.score": 0.9})
        assert result == ""

    def test_non_string_values_excluded_from_fallback(self) -> None:
        provider = _make_provider()
        result = provider._extract_document_text({"count": 42, "tags": ["a", "b"]}, doc_id="d1")
        # Non-string values should not appear in fallback
        assert result == ""


# -- _ensure_knowledge_base ---------------------------------------------------


class TestEnsureKnowledgeBase:
    """Tests for _ensure_knowledge_base."""

    async def test_already_initialized_returns_early(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True

        await provider._ensure_knowledge_base()  # should not raise

    async def test_missing_kb_name_raises(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider.knowledge_base_name = None

        with pytest.raises(ValueError, match="knowledge_base_name is required"):
            await provider._ensure_knowledge_base()

    async def test_existing_kb_sets_initialized(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = True
        provider.knowledge_base_name = "existing-kb"

        with patch("agent_framework_azure_ai_search._context_provider.KnowledgeBaseRetrievalClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await provider._ensure_knowledge_base()
            assert provider._knowledge_base_initialized is True

    async def test_missing_index_client_raises(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider._index_client = None

        with pytest.raises(ValueError, match="Index client is required"):
            await provider._ensure_knowledge_base()

    async def test_missing_aoai_url_raises(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider._index_client = AsyncMock()
        provider.azure_openai_resource_url = None

        with pytest.raises(ValueError, match="azure_openai_resource_url is required"):
            await provider._ensure_knowledge_base()

    async def test_missing_deployment_name_raises(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider._index_client = AsyncMock()
        provider.azure_openai_resource_url = "https://aoai.openai.azure.com"
        provider.azure_openai_deployment_name = None

        with pytest.raises(ValueError, match="model_deployment_name is required"):
            await provider._ensure_knowledge_base()

    async def test_missing_index_name_raises(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider._index_client = AsyncMock()
        provider.azure_openai_resource_url = "https://aoai.openai.azure.com"
        provider.azure_openai_deployment_name = "deploy"
        provider.index_name = None

        with pytest.raises(ValueError, match="index_name is required"):
            await provider._ensure_knowledge_base()

    async def test_creates_knowledge_source_when_not_found(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider.azure_openai_resource_url = "https://aoai.openai.azure.com"
        provider.azure_openai_deployment_name = "deploy"
        provider.model_name = "gpt-4"
        provider.index_name = "test-index"

        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.side_effect = ResourceNotFoundError("not found")
        mock_index_client.create_knowledge_source = AsyncMock()
        mock_index_client.create_or_update_knowledge_base = AsyncMock()
        provider._index_client = mock_index_client

        with patch("agent_framework_azure_ai_search._context_provider.KnowledgeBaseRetrievalClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await provider._ensure_knowledge_base()

        mock_index_client.create_knowledge_source.assert_awaited_once()
        mock_index_client.create_or_update_knowledge_base.assert_awaited_once()
        assert provider._knowledge_base_initialized is True

    async def test_uses_existing_knowledge_source(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider.azure_openai_resource_url = "https://aoai.openai.azure.com"
        provider.azure_openai_deployment_name = "deploy"
        provider.model_name = "gpt-4"
        provider.index_name = "test-index"

        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.return_value = Mock()  # source already exists
        mock_index_client.create_or_update_knowledge_base = AsyncMock()
        provider._index_client = mock_index_client

        with patch("agent_framework_azure_ai_search._context_provider.KnowledgeBaseRetrievalClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await provider._ensure_knowledge_base()

        mock_index_client.create_knowledge_source.assert_not_awaited()
        mock_index_client.create_or_update_knowledge_base.assert_awaited_once()

    async def test_answer_synthesis_output_mode(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider.azure_openai_resource_url = "https://aoai.openai.azure.com"
        provider.azure_openai_deployment_name = "deploy"
        provider.model_name = "gpt-4"
        provider.index_name = "test-index"
        provider.knowledge_base_output_mode = "answer_synthesis"

        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.return_value = Mock()
        mock_index_client.create_or_update_knowledge_base = AsyncMock()
        provider._index_client = mock_index_client

        with patch("agent_framework_azure_ai_search._context_provider.KnowledgeBaseRetrievalClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await provider._ensure_knowledge_base()

        assert provider._knowledge_base_initialized is True

    async def test_medium_reasoning_effort(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = False
        provider._use_existing_knowledge_base = False
        provider.knowledge_base_name = "test-kb"
        provider.azure_openai_resource_url = "https://aoai.openai.azure.com"
        provider.azure_openai_deployment_name = "deploy"
        provider.model_name = "gpt-4"
        provider.index_name = "test-index"
        provider.retrieval_reasoning_effort = "medium"

        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.return_value = Mock()
        mock_index_client.create_or_update_knowledge_base = AsyncMock()
        provider._index_client = mock_index_client

        with patch("agent_framework_azure_ai_search._context_provider.KnowledgeBaseRetrievalClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await provider._ensure_knowledge_base()

        assert provider._knowledge_base_initialized is True


# -- _agentic_search ----------------------------------------------------------


class TestAgenticSearch:
    """Tests for _agentic_search."""

    async def test_no_retrieval_client_raises(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider._retrieval_client = None

        with pytest.raises(RuntimeError, match="Retrieval client not initialized"):
            await provider._agentic_search([Message(role="user", contents=["query"])])

    async def test_minimal_reasoning_returns_results(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider.retrieval_reasoning_effort = "minimal"

        mock_content = Mock()
        mock_content.text = "Answer text"
        mock_message = Mock()
        mock_message.role = "assistant"
        mock_message.content = [mock_content]
        mock_result = Mock()
        mock_result.response = [mock_message]
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        # Patch isinstance check for KnowledgeBaseMessageTextContent
        with patch(
            "agent_framework_azure_ai_search._context_provider.KnowledgeBaseMessageTextContent",
            type(mock_content),
        ):
            results = await provider._agentic_search([Message(role="user", contents=["test query"])])

        assert len(results) == 1
        assert results[0].text == "Answer text"
        assert results[0].role == "assistant"

    async def test_non_minimal_reasoning_uses_messages(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider.retrieval_reasoning_effort = "medium"

        mock_content = Mock()
        mock_content.text = "Medium answer"
        mock_message = Mock()
        mock_message.role = "assistant"
        mock_message.content = [mock_content]
        mock_result = Mock()
        mock_result.response = [mock_message]
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        with patch(
            "agent_framework_azure_ai_search._context_provider.KnowledgeBaseMessageTextContent",
            type(mock_content),
        ):
            results = await provider._agentic_search([
                Message(role="user", contents=["question"]),
                Message(role="assistant", contents=["answer"]),
            ])

        assert len(results) == 1
        assert results[0].text == "Medium answer"
        mock_retrieval.retrieve.assert_awaited_once()

    async def test_no_response_returns_default_message(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider.retrieval_reasoning_effort = "minimal"

        mock_result = Mock()
        mock_result.response = []
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        results = await provider._agentic_search([Message(role="user", contents=["query"])])
        assert len(results) == 1
        assert results[0].text == "No results found from Knowledge Base."

    async def test_empty_content_returns_default_message(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider.retrieval_reasoning_effort = "minimal"

        mock_message = Mock()
        mock_message.content = None
        mock_result = Mock()
        mock_result.response = [mock_message]
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        results = await provider._agentic_search([Message(role="user", contents=["query"])])
        assert len(results) == 1
        assert results[0].text == "No results found from Knowledge Base."

    async def test_answer_synthesis_output_mode(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider.retrieval_reasoning_effort = "low"
        provider.knowledge_base_output_mode = "answer_synthesis"

        mock_content = Mock()
        mock_content.text = "Synthesized answer"
        mock_message = Mock()
        mock_message.role = "assistant"
        mock_message.content = [mock_content]
        mock_result = Mock()
        mock_result.response = [mock_message]
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        with patch(
            "agent_framework_azure_ai_search._context_provider.KnowledgeBaseMessageTextContent",
            type(mock_content),
        ):
            results = await provider._agentic_search([Message(role="user", contents=["query"])])

        assert len(results) == 1
        assert results[0].text == "Synthesized answer"

    async def test_content_without_text_excluded(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider.retrieval_reasoning_effort = "minimal"

        mock_content_with_text = Mock()
        mock_content_with_text.text = "Good content"
        mock_content_no_text = Mock()
        mock_content_no_text.text = None
        mock_message = Mock()
        mock_message.role = "assistant"
        mock_message.content = [mock_content_no_text, mock_content_with_text]
        mock_result = Mock()
        mock_result.response = [mock_message]
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        with patch(
            "agent_framework_azure_ai_search._context_provider.KnowledgeBaseMessageTextContent",
            type(mock_content_with_text),
        ):
            results = await provider._agentic_search([Message(role="user", contents=["query"])])

        assert len(results) == 1
        assert results[0].text == "Good content"

    async def test_none_response_returns_default_message(self) -> None:
        provider = _make_provider()
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"
        provider.retrieval_reasoning_effort = "minimal"

        mock_result = Mock()
        mock_result.response = None
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        results = await provider._agentic_search([Message(role="user", contents=["query"])])
        assert len(results) == 1
        assert results[0].text == "No results found from Knowledge Base."


# -- before_run: agentic mode --------------------------------------------------


# -- _prepare_messages_for_kb_search / _parse_content_from_kb_response --------


class TestPrepareMessagesForKbSearch:
    """Tests for _prepare_messages_for_kb_search."""

    def test_text_only_messages(self) -> None:
        messages = [
            Message(role="user", contents=["hello"]),
            Message(role="assistant", contents=["world"]),
        ]
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search(messages)
        assert len(result) == 2
        assert result[0].role == "user"
        assert result[1].role == "assistant"
        # Verify content is KnowledgeBaseMessageTextContent
        from azure.search.documents.knowledgebases.models import KnowledgeBaseMessageTextContent

        assert isinstance(result[0].content[0], KnowledgeBaseMessageTextContent)
        assert result[0].content[0].text == "hello"

    def test_image_uri_content(self) -> None:

        img = Content.from_uri(uri="https://example.com/photo.png", media_type="image/png")
        messages = [Message(role="user", contents=[img])]
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search(messages)
        assert len(result) == 1
        from azure.search.documents.knowledgebases.models import KnowledgeBaseMessageImageContent

        assert isinstance(result[0].content[0], KnowledgeBaseMessageImageContent)
        assert result[0].content[0].image.url == "https://example.com/photo.png"

    def test_mixed_text_and_image_content(self) -> None:

        text = Content.from_text("describe this image")
        img = Content.from_uri(uri="https://example.com/img.jpg", media_type="image/jpeg")
        messages = [Message(role="user", contents=[text, img])]
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search(messages)
        assert len(result) == 1
        assert len(result[0].content) == 2

    def test_skips_non_text_non_image_content(self) -> None:

        error = Content.from_error(message="oops")
        messages = [Message(role="user", contents=[error])]
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search(messages)
        assert len(result) == 0  # message had no usable content

    def test_skips_empty_text(self) -> None:

        empty = Content.from_text("")
        messages = [Message(role="user", contents=[empty])]
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search(messages)
        assert len(result) == 0

    def test_fallback_to_msg_text_when_no_contents(self) -> None:
        msg = Message(role="user", text="fallback text")
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search([msg])
        assert len(result) == 1
        assert result[0].content[0].text == "fallback text"

    def test_data_uri_image(self) -> None:

        img = Content.from_data(data=b"\x89PNG", media_type="image/png")
        messages = [Message(role="user", contents=[img])]
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search(messages)
        assert len(result) == 1
        from azure.search.documents.knowledgebases.models import KnowledgeBaseMessageImageContent

        assert isinstance(result[0].content[0], KnowledgeBaseMessageImageContent)

    def test_non_image_uri_skipped(self) -> None:

        pdf = Content.from_uri(uri="https://example.com/doc.pdf", media_type="application/pdf")
        messages = [Message(role="user", contents=[pdf])]
        result = AzureAISearchContextProvider._prepare_messages_for_kb_search(messages)
        assert len(result) == 0


class TestParseReferencesToAnnotations:
    """Tests for _parse_references_to_annotations."""

    def test_none_references(self) -> None:
        result = AzureAISearchContextProvider._parse_references_to_annotations(None)
        assert result == []

    def test_empty_references(self) -> None:
        result = AzureAISearchContextProvider._parse_references_to_annotations([])
        assert result == []

    def test_search_index_reference_captures_doc_key(self) -> None:
        from azure.search.documents.knowledgebases.models import KnowledgeBaseSearchIndexReference

        ref = KnowledgeBaseSearchIndexReference(id="ref-1", activity_source=0, doc_key="doc-1")
        result = AzureAISearchContextProvider._parse_references_to_annotations([ref])
        assert len(result) == 1
        assert result[0]["type"] == "citation"
        assert result[0]["title"] == "ref-1"
        extra = result[0]["additional_properties"]
        assert extra["reference_id"] == "ref-1"
        assert extra["reference_type"] == "searchIndex"
        assert extra["activity_source"] == 0
        assert extra["doc_key"] == "doc-1"

    def test_web_reference_with_url_and_title(self) -> None:
        from azure.search.documents.knowledgebases.models import KnowledgeBaseWebReference

        ref = KnowledgeBaseWebReference(
            id="ref-2", activity_source=0, url="https://example.com/page", title="Example Page"
        )
        result = AzureAISearchContextProvider._parse_references_to_annotations([ref])
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/page"
        assert result[0]["title"] == "Example Page"
        assert result[0]["additional_properties"]["reference_type"] == "web"

    def test_blob_reference_extracts_blob_url(self) -> None:
        from azure.search.documents.knowledgebases.models import KnowledgeBaseAzureBlobReference

        ref = KnowledgeBaseAzureBlobReference(
            id="ref-3", activity_source=0, blob_url="https://storage.blob.core.windows.net/doc.pdf"
        )
        result = AzureAISearchContextProvider._parse_references_to_annotations([ref])
        assert result[0]["url"] == "https://storage.blob.core.windows.net/doc.pdf"
        assert result[0]["additional_properties"]["reference_type"] == "azureBlob"

    def test_source_data_and_reranker_score(self) -> None:
        from azure.search.documents.knowledgebases.models import KnowledgeBaseSearchIndexReference

        ref = KnowledgeBaseSearchIndexReference(
            id="ref-4", activity_source=0, source_data={"chunk": "some text"}, reranker_score=0.95
        )
        result = AzureAISearchContextProvider._parse_references_to_annotations([ref])
        extra = result[0]["additional_properties"]
        assert extra["source_data"] == {"chunk": "some text"}
        assert extra["reranker_score"] == 0.95

    def test_raw_representation_stores_original_ref(self) -> None:
        from azure.search.documents.knowledgebases.models import KnowledgeBaseSearchIndexReference

        ref = KnowledgeBaseSearchIndexReference(id="ref-5", activity_source=0)
        result = AzureAISearchContextProvider._parse_references_to_annotations([ref])
        assert result[0]["raw_representation"] is ref

    def test_remote_sharepoint_captures_sensitivity_label(self) -> None:
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseRemoteSharePointReference,
            SharePointSensitivityLabelInfo,
        )

        label = SharePointSensitivityLabelInfo(
            display_name="Confidential", sensitivity_label_id="lbl-1", is_encrypted=True
        )
        ref = KnowledgeBaseRemoteSharePointReference(
            id="ref-6", activity_source=0, web_url="https://sp.example.com/doc", search_sensitivity_label_info=label
        )
        result = AzureAISearchContextProvider._parse_references_to_annotations([ref])
        assert result[0]["url"] == "https://sp.example.com/doc"
        sl = result[0]["additional_properties"]["sensitivity_label"]
        assert sl["display_name"] == "Confidential"
        assert sl["sensitivity_label_id"] == "lbl-1"
        assert sl["is_encrypted"] is True

    def test_multiple_references(self) -> None:
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseSearchIndexReference,
            KnowledgeBaseWebReference,
        )

        refs = [
            KnowledgeBaseSearchIndexReference(id="ref-a", activity_source=0),
            KnowledgeBaseWebReference(id="ref-b", activity_source=1, url="https://example.com"),
        ]
        result = AzureAISearchContextProvider._parse_references_to_annotations(refs)
        assert len(result) == 2
        assert result[0]["additional_properties"]["activity_source"] == 0
        assert result[1]["additional_properties"]["activity_source"] == 1


class TestParseMessagesFromKbResponse:
    """Tests for _parse_messages_from_kb_response."""

    def test_converts_all_messages(self) -> None:
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseMessage,
            KnowledgeBaseMessageTextContent,
            KnowledgeBaseRetrievalResponse,
        )

        response = KnowledgeBaseRetrievalResponse(
            response=[
                KnowledgeBaseMessage(role="user", content=[KnowledgeBaseMessageTextContent(text="q")]),
                KnowledgeBaseMessage(role="assistant", content=[KnowledgeBaseMessageTextContent(text="answer")]),
            ],
            references=None,
        )
        result = AzureAISearchContextProvider._parse_messages_from_kb_response(response)
        assert len(result) == 2
        assert result[0].role == "user"
        assert result[0].text == "q"
        assert result[1].role == "assistant"
        assert result[1].text == "answer"

    def test_none_response_returns_default(self) -> None:
        from azure.search.documents.knowledgebases.models import KnowledgeBaseRetrievalResponse

        response = KnowledgeBaseRetrievalResponse(response=None, references=None)
        result = AzureAISearchContextProvider._parse_messages_from_kb_response(response)
        assert len(result) == 1
        assert result[0].text == "No results found from Knowledge Base."

    def test_empty_response_returns_default(self) -> None:
        from azure.search.documents.knowledgebases.models import KnowledgeBaseRetrievalResponse

        response = KnowledgeBaseRetrievalResponse(response=[], references=None)
        result = AzureAISearchContextProvider._parse_messages_from_kb_response(response)
        assert len(result) == 1
        assert result[0].text == "No results found from Knowledge Base."

    def test_image_content(self) -> None:
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseMessage,
            KnowledgeBaseMessageImageContent,
            KnowledgeBaseMessageImageContentImage,
            KnowledgeBaseRetrievalResponse,
        )

        response = KnowledgeBaseRetrievalResponse(
            response=[
                KnowledgeBaseMessage(
                    role="assistant",
                    content=[
                        KnowledgeBaseMessageImageContent(
                            image=KnowledgeBaseMessageImageContentImage(url="https://img.example.com/a.png")
                        )
                    ],
                ),
            ],
            references=None,
        )
        result = AzureAISearchContextProvider._parse_messages_from_kb_response(response)
        assert len(result) == 1
        assert result[0].contents[0].type == "uri"
        assert result[0].contents[0].uri == "https://img.example.com/a.png"

    def test_mixed_text_and_image_content(self) -> None:
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseMessage,
            KnowledgeBaseMessageImageContent,
            KnowledgeBaseMessageImageContentImage,
            KnowledgeBaseMessageTextContent,
            KnowledgeBaseRetrievalResponse,
        )

        response = KnowledgeBaseRetrievalResponse(
            response=[
                KnowledgeBaseMessage(
                    role="assistant",
                    content=[
                        KnowledgeBaseMessageTextContent(text="description"),
                        KnowledgeBaseMessageImageContent(
                            image=KnowledgeBaseMessageImageContentImage(url="https://img.example.com/b.png")
                        ),
                    ],
                ),
            ],
            references=None,
        )
        result = AzureAISearchContextProvider._parse_messages_from_kb_response(response)
        assert len(result) == 1
        assert len(result[0].contents) == 2
        assert result[0].contents[0].type == "text"
        assert result[0].contents[1].type == "uri"

    def test_references_become_annotations(self) -> None:
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseMessage,
            KnowledgeBaseMessageTextContent,
            KnowledgeBaseRetrievalResponse,
            KnowledgeBaseWebReference,
        )

        response = KnowledgeBaseRetrievalResponse(
            response=[
                KnowledgeBaseMessage(role="assistant", content=[KnowledgeBaseMessageTextContent(text="answer")]),
            ],
            references=[
                KnowledgeBaseWebReference(id="ref-1", activity_source=0, url="https://example.com", title="Example"),
            ],
        )
        result = AzureAISearchContextProvider._parse_messages_from_kb_response(response)
        assert len(result) == 1
        annotations = result[0].contents[0].annotations
        assert annotations is not None
        assert len(annotations) == 1
        assert annotations[0]["type"] == "citation"
        assert annotations[0]["url"] == "https://example.com"
        assert annotations[0]["title"] == "Example"

    def test_multiple_messages_with_references(self) -> None:
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseMessage,
            KnowledgeBaseMessageTextContent,
            KnowledgeBaseRetrievalResponse,
            KnowledgeBaseSearchIndexReference,
        )

        response = KnowledgeBaseRetrievalResponse(
            response=[
                KnowledgeBaseMessage(role="user", content=[KnowledgeBaseMessageTextContent(text="q")]),
                KnowledgeBaseMessage(
                    role="assistant",
                    content=[
                        KnowledgeBaseMessageTextContent(text="part1"),
                        KnowledgeBaseMessageTextContent(text="part2"),
                    ],
                ),
            ],
            references=[KnowledgeBaseSearchIndexReference(id="doc-1", activity_source=0)],
        )
        result = AzureAISearchContextProvider._parse_messages_from_kb_response(response)
        assert len(result) == 2
        # All content items get annotations
        for msg in result:
            for c in msg.contents:
                assert c.annotations is not None
                assert len(c.annotations) == 1


# -- before_run: agentic mode --------------------------------------------------


class TestBeforeRunAgentic:
    """Tests for before_run in agentic mode."""

    async def test_agentic_mode_calls_agentic_search(self) -> None:
        provider = _make_provider()
        provider.mode = "agentic"
        provider.agentic_message_history_count = 5
        provider._knowledge_base_initialized = True
        provider.knowledge_base_name = "kb"

        mock_content = Mock()
        mock_content.text = "agentic result"
        mock_message = Mock()
        mock_message.role = "assistant"
        mock_message.content = [mock_content]
        mock_result = Mock()
        mock_result.response = [mock_message]
        mock_result.references = None

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve = AsyncMock(return_value=mock_result)
        provider._retrieval_client = mock_retrieval

        session = AgentSession(session_id="test-session")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["agentic question"])],
            session_id="s1",
        )

        with patch(
            "agent_framework_azure_ai_search._context_provider.KnowledgeBaseMessageTextContent",
            type(mock_content),
        ):
            await provider.before_run(
                agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
            )  # type: ignore[arg-type]

        msgs = ctx.context_messages.get(provider.source_id, [])
        assert len(msgs) >= 2
        assert msgs[0].text == provider.context_prompt
        assert msgs[1].text == "agentic result"

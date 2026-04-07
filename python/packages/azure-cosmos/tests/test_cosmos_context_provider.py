# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext
from azure.cosmos.exceptions import CosmosResourceNotFoundError

import agent_framework_azure_cosmos._context_provider as context_provider_module
from agent_framework_azure_cosmos import AzureCosmosContextProvider, CosmosContextSearchMode


def _to_async_iter(items: list[Any]) -> AsyncIterator[Any]:
    async def _iterator() -> AsyncIterator[Any]:
        for item in items:
            yield item

    return _iterator()


def test_provider_uses_existing_container_client() -> None:
    container = MagicMock()
    provider = AzureCosmosContextProvider(source_id="ctx", container_client=container)

    assert provider.source_id == "ctx"
    assert provider.container_name == ""
    assert provider.database_name == ""
    assert provider.default_search_mode is CosmosContextSearchMode.FULL_TEXT


def test_provider_constructs_client_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    database_client = MagicMock()
    cosmos_client = MagicMock()
    cosmos_client.get_database_client.return_value = database_client
    cosmos_client_factory = MagicMock(return_value=cosmos_client)

    monkeypatch.setattr(context_provider_module, "CosmosClient", cosmos_client_factory)
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://account.documents.azure.com:443/")
    monkeypatch.setenv("AZURE_COSMOS_DATABASE_NAME", "agent-framework")
    monkeypatch.setenv("AZURE_COSMOS_CONTAINER_NAME", "knowledge")
    monkeypatch.setenv("AZURE_COSMOS_KEY", "test-key")
    monkeypatch.setenv("AZURE_COSMOS_TOP_K", "4")
    monkeypatch.setenv("AZURE_COSMOS_SCAN_LIMIT", "9")

    provider = AzureCosmosContextProvider()

    cosmos_client_factory.assert_called_once()
    kwargs = cosmos_client_factory.call_args.kwargs
    assert kwargs["url"] == "https://account.documents.azure.com:443/"
    assert kwargs["credential"] == "test-key"
    assert provider.database_name == "agent-framework"
    assert provider.container_name == "knowledge"
    assert provider.top_k == 4
    assert provider.scan_limit == 9


class TestAzureCosmosContextProviderBeforeRun:
    async def test_before_run_no_valid_messages_skips_query(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([]))
        provider = AzureCosmosContextProvider(container_client=container)

        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="system", contents=["ignore this"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        container.query_items.assert_not_called()
        assert context.context_messages.get(provider.source_id) is None

    async def test_before_run_full_text_default_adds_prompt_and_ranked_context_messages(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {"id": "1", "content": "Azure Cosmos DB supports vector search and hybrid search."},
                {
                    "id": "3",
                    "title": "Ranking",
                    "content": "Hybrid search can combine full text and vector search.",
                },
                {"id": "2", "content": "This unrelated document should not be returned."},
            ])
        )
        provider = AzureCosmosContextProvider(container_client=container)

        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["How does hybrid search use vector search?"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        container.query_items.assert_called_once()
        provider_messages = context.context_messages[provider.source_id]
        assert provider_messages[0].text == provider.context_prompt
        assert len(provider_messages) == 3
        assert "vector search" in provider_messages[1].text.lower()
        assert "hybrid search" in provider_messages[2].text.lower()
        query_kwargs = container.query_items.call_args.kwargs
        assert query_kwargs["max_item_count"] == provider.scan_limit
        assert "NOT IS_DEFINED(c.document_type)" in query_kwargs["query"]
        assert "ORDER BY RANK FullTextScore(" in query_kwargs["query"]
        assert query_kwargs["parameters"] == [
            {"name": "@writeback_document_type", "value": provider._WRITEBACK_DOCUMENT_TYPE},
            {"name": "@query_text", "value": "how does hybrid search use vector"},
        ]
        assert "search_mode" not in session.state[provider.source_id]

    async def test_before_run_respects_top_k_and_partition_key(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {"id": "1", "content": "Vector search for Cosmos DB."},
                {"id": "2", "content": "Hybrid search for Cosmos DB."},
                {"id": "3", "content": "Full text search for Cosmos DB."},
            ])
        )
        provider = AzureCosmosContextProvider(
            container_client=container, top_k=1, scan_limit=7, partition_key="knowledge"
        )

        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain hybrid search and vector search"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        provider_messages = context.context_messages[provider.source_id]
        assert len(provider_messages) == 2
        query_kwargs = container.query_items.call_args.kwargs
        assert query_kwargs["partition_key"] == "knowledge"
        assert query_kwargs["max_item_count"] == 7
        assert "FullTextScore(" in query_kwargs["query"]

    async def test_before_run_runtime_overrides_top_k_scan_limit_and_partition_key(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {"id": "1", "content": "Vector search for Cosmos DB."},
                {"id": "2", "content": "Hybrid search for Cosmos DB."},
                {"id": "3", "content": "Full text search for Cosmos DB."},
            ])
        )
        provider = AzureCosmosContextProvider(
            container_client=container,
            top_k=3,
            scan_limit=9,
            partition_key="default-knowledge",
        )

        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain hybrid search and vector search"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None,
            session=session,
            context=context,
            state=session.state.setdefault(provider.source_id, {}),
            top_k=1,
            scan_limit=4,
            partition_key="runtime-knowledge",
        )  # type: ignore[arg-type]

        provider_messages = context.context_messages[provider.source_id]
        assert len(provider_messages) == 2
        query_kwargs = container.query_items.call_args.kwargs
        assert query_kwargs["partition_key"] == "runtime-knowledge"
        assert query_kwargs["max_item_count"] == 4
        assert "SELECT TOP 4" in query_kwargs["query"]
        assert provider.top_k == 3
        assert provider.scan_limit == 9
        assert provider.partition_key == "default-knowledge"

    async def test_before_run_supports_custom_field_mapping(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {
                    "doc_id": "doc-1",
                    "headline": "Cosmos context",
                    "body": "Custom mapped content can be used for hybrid search retrieval.",
                    "link": "https://example.com/context",
                    "attributes": {"kind": "knowledge"},
                }
            ])
        )
        provider = AzureCosmosContextProvider(
            container_client=container,
            id_field_name="doc_id",
            content_field_names=("body", "summary"),
            title_field_name="headline",
            url_field_name="link",
            message_field_name=None,
            metadata_field_name="attributes",
        )

        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["How do I configure hybrid search retrieval?"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        provider_messages = context.context_messages[provider.source_id]
        assert "Title: Cosmos context" in provider_messages[1].text
        assert "Source: https://example.com/context" in provider_messages[1].text
        assert provider_messages[1].additional_properties["cosmos_document_id"] == "doc-1"
        assert provider_messages[1].additional_properties["cosmos_metadata"] == {"kind": "knowledge"}
        query_text = container.query_items.call_args.kwargs["query"]
        assert "c.doc_id" in query_text
        assert "c.body" in query_text
        assert "c.headline" in query_text
        assert "c.link" in query_text
        assert "c.attributes" in query_text
        assert "FullTextScore(c.body, @query_text)" in query_text

    async def test_before_run_joins_all_filtered_messages_for_query_text(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {"id": "1", "content": "Cosmos hybrid search combines full text and vector retrieval."}
            ])
        )
        provider = AzureCosmosContextProvider(container_client=container)

        session = AgentSession(session_id="test-session")
        state = session.state.setdefault(provider.source_id, {})
        context = SessionContext(
            input_messages=[
                Message(role="user", contents=["Tell me about Cosmos search"]),
                Message(role="system", contents=["ignore this"]),
                Message(role="assistant", contents=["Do you mean vector or hybrid?"]),
                Message(role="user", contents=["Hybrid"]),
            ],
            session_id="s1",
        )

        await provider.before_run(agent=None, session=session, context=context, state=state)  # type: ignore[arg-type]

        assert state["query_text"] == "Tell me about Cosmos search\nDo you mean vector or hybrid?\nHybrid"
        assert "search_mode" not in state

    async def test_before_run_uses_existing_container_from_database_client(self) -> None:
        container = MagicMock()
        container.read = AsyncMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([{"id": "1", "text": "Cosmos full text search is available."}])
        )
        database_client = MagicMock()
        database_client.get_container_client.return_value = container
        cosmos_client = MagicMock()
        cosmos_client.get_database_client.return_value = database_client

        provider = AzureCosmosContextProvider(
            cosmos_client=cosmos_client,
            database_name="db1",
            container_name="knowledge",
        )

        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Tell me about full text search"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        database_client.get_container_client.assert_called_once_with("knowledge")
        container.read.assert_awaited_once()
        assert context.context_messages[provider.source_id][0].text == provider.context_prompt

    async def test_before_run_runtime_vector_mode_builds_vector_distance_query(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {
                    "id": "1",
                    "content": "Hybrid search combines vector and lexical retrieval.",
                    "embedding": [1.0, 0.0],
                },
                {
                    "id": "2",
                    "content": "A document about something unrelated.",
                    "embedding": [0.0, 1.0],
                },
            ])
        )

        async def embed_query(_: str) -> list[float]:
            return [1.0, 0.0]

        provider = AzureCosmosContextProvider(
            container_client=container,
            vector_field_name="embedding",
            embedding_function=embed_query,
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Find semantically similar docs"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None,
            session=session,
            context=context,
            state=session.state.setdefault(provider.source_id, {}),
            search_mode=CosmosContextSearchMode.VECTOR,
        )  # type: ignore[arg-type]

        provider_messages = context.context_messages[provider.source_id]
        assert provider_messages[0].text == provider.context_prompt
        assert "hybrid search" in provider_messages[1].text.lower()
        query_kwargs = container.query_items.call_args.kwargs
        assert "NOT IS_DEFINED(c.document_type)" in query_kwargs["query"]
        assert "ORDER BY VectorDistance(c.embedding, @query_vector) ASC" in query_kwargs["query"]
        assert query_kwargs["parameters"] == [
            {"name": "@writeback_document_type", "value": provider._WRITEBACK_DOCUMENT_TYPE},
            {"name": "@query_vector", "value": [1.0, 0.0]},
        ]
        assert "search_mode" not in session.state[provider.source_id]
        assert "c.embedding" not in query_kwargs["query"].split("FROM c", maxsplit=1)[0]

    async def test_before_run_runtime_hybrid_mode_builds_rrf_query_with_weights(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {
                    "id": "1",
                    "content": "Hybrid search combines vector search with lexical retrieval.",
                    "embedding": [1.0, 0.0],
                },
                {
                    "id": "2",
                    "content": "Vector search embeddings and similarity basics.",
                    "embedding": [0.8, 0.2],
                },
                {
                    "id": "3",
                    "content": "Completely unrelated document.",
                    "embedding": [0.0, 1.0],
                },
            ])
        )

        async def embed_query(_: str) -> list[float]:
            return [1.0, 0.0]

        provider = AzureCosmosContextProvider(
            container_client=container,
            vector_field_name="embedding",
            embedding_function=embed_query,
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain hybrid search and vector search"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None,
            session=session,
            context=context,
            state=session.state.setdefault(provider.source_id, {}),
            search_mode=CosmosContextSearchMode.HYBRID,
            weights=[2.0, 1.0],
        )  # type: ignore[arg-type]

        provider_messages = context.context_messages[provider.source_id]
        assert provider_messages[0].text == provider.context_prompt
        assert "hybrid search" in provider_messages[1].text.lower()
        query_kwargs = container.query_items.call_args.kwargs
        assert "NOT IS_DEFINED(c.document_type)" in query_kwargs["query"]
        assert "ORDER BY RANK RRF(" in query_kwargs["query"]
        assert "FullTextScore(c.content, @query_text)" in query_kwargs["query"]
        assert "VectorDistance(c.embedding, @query_vector)" in query_kwargs["query"]
        assert "[2, 1]" in query_kwargs["query"]
        assert query_kwargs["parameters"][0] == {
            "name": "@writeback_document_type",
            "value": provider._WRITEBACK_DOCUMENT_TYPE,
        }

    async def test_before_run_runtime_hybrid_mode_uses_default_weights_when_omitted(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([{"id": "1", "content": "Hybrid search combines text and vector ranking."}])
        )

        async def embed_query(_: str) -> list[float]:
            return [0.5, 0.5]

        provider = AzureCosmosContextProvider(
            container_client=container,
            vector_field_name="embedding",
            embedding_function=embed_query,
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain hybrid ranking"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None,
            session=session,
            context=context,
            state=session.state.setdefault(provider.source_id, {}),
            search_mode=CosmosContextSearchMode.HYBRID,
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        assert "[1, 1]" in query_kwargs["query"]

    async def test_before_run_vector_mode_allows_non_lexical_query_text(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"id": "1", "content": "Emoji query result"}]))

        async def embed_query(_: str) -> list[float]:
            return [1.0, 0.0]

        provider = AzureCosmosContextProvider(
            container_client=container,
            vector_field_name="embedding",
            embedding_function=embed_query,
        )
        session = AgentSession(session_id="test-session")
        state = session.state.setdefault(provider.source_id, {})
        context = SessionContext(input_messages=[Message(role="user", contents=["🔎"])], session_id="s1")

        await provider.before_run(
            agent=None,
            session=session,
            context=context,
            state=state,
            search_mode=CosmosContextSearchMode.VECTOR,
        )  # type: ignore[arg-type]

        container.query_items.assert_called_once()
        assert state["query_text"] == "🔎"
        assert context.context_messages[provider.source_id][0].text == provider.context_prompt

    async def test_before_run_hybrid_mode_without_text_terms_skips_query(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([]))

        async def embed_query(_: str) -> list[float]:
            return [1.0, 0.0]

        provider = AzureCosmosContextProvider(
            container_client=container,
            vector_field_name="embedding",
            embedding_function=embed_query,
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(input_messages=[Message(role="user", contents=["🔎"])], session_id="s1")

        await provider.before_run(
            agent=None,
            session=session,
            context=context,
            state=session.state.setdefault(provider.source_id, {}),
            search_mode=CosmosContextSearchMode.HYBRID,
        )  # type: ignore[arg-type]

        container.query_items.assert_not_called()
        assert context.context_messages.get(provider.source_id) is None

    async def test_before_run_invalid_message_payload_falls_back_to_content(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {"id": "1", "message": {"bad": "payload"}, "content": "Fallback content for Cosmos retrieval."}
            ])
        )
        provider = AzureCosmosContextProvider(container_client=container)
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Find Cosmos retrieval details"])],
            session_id="s1",
        )

        await provider.before_run(
            agent=None,
            session=session,
            context=context,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        assert "Fallback content for Cosmos retrieval." in context.context_messages[provider.source_id][1].text

    async def test_before_run_reuses_same_provider_with_different_runtime_search_modes(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            side_effect=[
                _to_async_iter([{"id": "1", "content": "Cosmos full text search is available."}]),
                _to_async_iter([
                    {
                        "id": "2",
                        "content": "Hybrid search combines vector and lexical retrieval.",
                        "embedding": [1.0, 0.0],
                    }
                ]),
            ]
        )

        async def embed_query(_: str) -> list[float]:
            return [1.0, 0.0]

        provider = AzureCosmosContextProvider(
            container_client=container,
            default_search_mode=CosmosContextSearchMode.FULL_TEXT,
            vector_field_name="embedding",
            embedding_function=embed_query,
        )

        first_session = AgentSession(session_id="first-session")
        first_context = SessionContext(
            input_messages=[Message(role="user", contents=["Tell me about Cosmos full text search"])],
            session_id="s1",
        )
        await provider.before_run(
            agent=None,
            session=first_session,
            context=first_context,
            state=first_session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        second_session = AgentSession(session_id="second-session")
        second_context = SessionContext(
            input_messages=[Message(role="user", contents=["Find semantically similar docs"])],
            session_id="s2",
        )
        await provider.before_run(
            agent=None,
            session=second_session,
            context=second_context,
            state=second_session.state.setdefault(provider.source_id, {}),
            search_mode=CosmosContextSearchMode.VECTOR,
        )  # type: ignore[arg-type]

        first_query = container.query_items.call_args_list[0].kwargs["query"]
        second_query = container.query_items.call_args_list[1].kwargs["query"]
        assert "FullTextScore(" in first_query
        assert "VectorDistance(" in second_query
        assert provider.default_search_mode is CosmosContextSearchMode.FULL_TEXT

    async def test_before_run_reuses_same_provider_with_different_runtime_query_overrides(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            side_effect=[
                _to_async_iter([
                    {"id": "1", "content": "Vector search for Cosmos DB."},
                    {"id": "2", "content": "Hybrid search for Cosmos DB."},
                ]),
                _to_async_iter([
                    {"id": "3", "content": "Full text search for Cosmos DB."},
                ]),
            ]
        )
        provider = AzureCosmosContextProvider(
            container_client=container,
            top_k=3,
            scan_limit=8,
            partition_key="default-knowledge",
        )

        first_session = AgentSession(session_id="first-session")
        first_context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain hybrid search and vector search"])],
            session_id="s1",
        )
        await provider.before_run(
            agent=None,
            session=first_session,
            context=first_context,
            state=first_session.state.setdefault(provider.source_id, {}),
            top_k=1,
            scan_limit=4,
            partition_key="runtime-knowledge",
        )  # type: ignore[arg-type]

        second_session = AgentSession(session_id="second-session")
        second_context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain full text search"])],
            session_id="s2",
        )
        await provider.before_run(
            agent=None,
            session=second_session,
            context=second_context,
            state=second_session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        first_kwargs = container.query_items.call_args_list[0].kwargs
        second_kwargs = container.query_items.call_args_list[1].kwargs
        assert first_kwargs["max_item_count"] == 4
        assert first_kwargs["partition_key"] == "runtime-knowledge"
        assert "SELECT TOP 4" in first_kwargs["query"]
        assert second_kwargs["max_item_count"] == 8
        assert second_kwargs["partition_key"] == "default-knowledge"
        assert "SELECT TOP 8" in second_kwargs["query"]
        assert provider.top_k == 3
        assert provider.scan_limit == 8
        assert provider.partition_key == "default-knowledge"

    async def test_before_run_missing_container_raises_runtime_error(self) -> None:
        container = MagicMock()
        container.read = AsyncMock(side_effect=CosmosResourceNotFoundError(message="missing"))
        database_client = MagicMock()
        database_client.get_container_client.return_value = container
        cosmos_client = MagicMock()
        cosmos_client.get_database_client.return_value = database_client
        provider = AzureCosmosContextProvider(
            cosmos_client=cosmos_client,
            database_name="db1",
            container_name="missing-container",
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        try:
            await provider.before_run(
                agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
            )  # type: ignore[arg-type]
        except RuntimeError as exc:
            assert "missing-container" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError when Cosmos container does not exist.")


class TestAzureCosmosContextProviderValidation:
    def test_invalid_top_k_raises(self) -> None:
        try:
            AzureCosmosContextProvider(container_client=MagicMock(), top_k=0)
        except ValueError as exc:
            assert "top_k" in str(exc)
        else:
            raise AssertionError("Expected ValueError for non-positive top_k")

    def test_invalid_field_name_raises(self) -> None:
        try:
            AzureCosmosContextProvider(container_client=MagicMock(), content_field_names=("content", "bad-field"))
        except ValueError as exc:
            assert "content_field_names" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid Cosmos field name")

    async def test_before_run_invalid_top_k_override_raises(self) -> None:
        provider = AzureCosmosContextProvider(container_client=MagicMock())
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        with pytest.raises(ValueError, match="top_k"):
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                top_k=0,
            )  # type: ignore[arg-type]

    async def test_before_run_invalid_scan_limit_override_raises(self) -> None:
        provider = AzureCosmosContextProvider(container_client=MagicMock())
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        with pytest.raises(ValueError, match="scan_limit"):
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                scan_limit=0,
            )  # type: ignore[arg-type]

    async def test_before_run_vector_mode_requires_vector_field(self) -> None:
        provider = AzureCosmosContextProvider(container_client=MagicMock())
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        try:
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                search_mode=CosmosContextSearchMode.VECTOR,
            )  # type: ignore[arg-type]
        except ValueError as exc:
            assert "vector_field_name" in str(exc)
        else:
            raise AssertionError("Expected ValueError when vector_field_name is missing")

    async def test_before_run_vector_mode_requires_embedding_function(self) -> None:
        provider = AzureCosmosContextProvider(
            container_client=MagicMock(),
            vector_field_name="embedding",
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        try:
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                search_mode=CosmosContextSearchMode.VECTOR,
            )  # type: ignore[arg-type]
        except ValueError as exc:
            assert "embedding_function" in str(exc)
        else:
            raise AssertionError("Expected ValueError when embedding_function is missing")

    async def test_before_run_invalid_weights_length_raises(self) -> None:
        provider = AzureCosmosContextProvider(
            container_client=MagicMock(),
            vector_field_name="embedding",
            embedding_function=AsyncMock(return_value=[1.0, 0.0]),
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        try:
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                search_mode=CosmosContextSearchMode.HYBRID,
                weights=[2.0, 1.0, 0.5],
            )  # type: ignore[arg-type]
        except ValueError as exc:
            assert "weights" in str(exc)
        else:
            raise AssertionError("Expected ValueError when weights length does not match hybrid components")

    async def test_before_run_weights_cannot_all_be_zero(self) -> None:
        provider = AzureCosmosContextProvider(
            container_client=MagicMock(),
            vector_field_name="embedding",
            embedding_function=AsyncMock(return_value=[1.0, 0.0]),
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        try:
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                search_mode=CosmosContextSearchMode.HYBRID,
                weights=[0.0, 0.0],
            )  # type: ignore[arg-type]
        except ValueError as exc:
            assert "weights" in str(exc)
        else:
            raise AssertionError("Expected ValueError when all hybrid weights are zero")

    async def test_before_run_negative_weight_raises(self) -> None:
        provider = AzureCosmosContextProvider(
            container_client=MagicMock(),
            vector_field_name="embedding",
            embedding_function=AsyncMock(return_value=[1.0, 0.0]),
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        with pytest.raises(ValueError, match="weights"):
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                search_mode=CosmosContextSearchMode.HYBRID,
                weights=[-1.0, 1.0],
            )  # type: ignore[arg-type]

    async def test_before_run_empty_embedding_raises(self) -> None:
        provider = AzureCosmosContextProvider(
            container_client=MagicMock(),
            vector_field_name="embedding",
            embedding_function=AsyncMock(return_value=[]),
        )
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["find docs"])],
            session_id="s1",
        )

        with pytest.raises(ValueError, match="empty embedding"):
            await provider.before_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
                search_mode=CosmosContextSearchMode.VECTOR,
            )  # type: ignore[arg-type]


class TestAzureCosmosContextProviderAfterRun:
    async def test_after_run_writeback_stores_input_and_response_messages(self) -> None:
        retrieval_container = MagicMock()
        retrieval_container.upsert_item = AsyncMock()
        provider = AzureCosmosContextProvider(container_client=retrieval_container)
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["hello cosmos"])],
            session_id="s1",
        )
        context._response = AgentResponse(messages=[Message(role="assistant", contents=["hello back"])])

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert retrieval_container.upsert_item.await_count == 2
        first_document = retrieval_container.upsert_item.await_args_list[0].args[0]
        second_document = retrieval_container.upsert_item.await_args_list[1].args[0]
        assert first_document["document_type"] == provider._WRITEBACK_DOCUMENT_TYPE
        assert first_document["session_id"] == "s1"
        assert first_document["source_id"] == provider.source_id
        assert first_document["content"] == "hello cosmos"
        assert second_document["content"] == "hello back"

    async def test_after_run_without_session_id_generates_partition_key(self, caplog: pytest.LogCaptureFixture) -> None:
        retrieval_container = MagicMock()
        retrieval_container.upsert_item = AsyncMock()
        provider = AzureCosmosContextProvider(container_client=retrieval_container)
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["hello cosmos"])],
            session_id=None,
        )

        with caplog.at_level("WARNING"):
            await provider.after_run(
                agent=None,
                session=session,
                context=context,
                state=session.state.setdefault(provider.source_id, {}),
            )  # type: ignore[arg-type]

        stored_document = retrieval_container.upsert_item.await_args.args[0]
        uuid.UUID(stored_document["session_id"])
        assert "Received empty session_id" in caplog.text


class TestAzureCosmosContextProviderLifecycle:
    async def test_close_closes_owned_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        database_client = MagicMock()
        cosmos_client = MagicMock()
        cosmos_client.get_database_client.return_value = database_client
        cosmos_client.close = AsyncMock()
        cosmos_client_factory = MagicMock(return_value=cosmos_client)

        monkeypatch.setattr(context_provider_module, "CosmosClient", cosmos_client_factory)

        provider = AzureCosmosContextProvider(
            endpoint="https://account.documents.azure.com:443/",
            credential="test-key",
            database_name="db1",
            container_name="knowledge",
        )

        await provider.close()

        cosmos_client.close.assert_awaited_once()

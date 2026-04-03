# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext
from azure.cosmos.exceptions import CosmosResourceNotFoundError

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

    async def test_before_run_expands_short_query_with_context(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {"id": "1", "content": "Cosmos hybrid search combines full text and vector retrieval."}
            ])
        )
        provider = AzureCosmosContextProvider(
            container_client=container,
            query_builder_mode="latest_user_with_context",
            recent_message_count=3,
            short_query_term_threshold=3,
        )

        session = AgentSession(session_id="test-session")
        state = session.state.setdefault(provider.source_id, {})
        context = SessionContext(
            input_messages=[
                Message(role="user", contents=["Tell me about Cosmos search"]),
                Message(role="assistant", contents=["Do you mean vector or hybrid?"]),
                Message(role="user", contents=["Hybrid"]),
            ],
            session_id="s1",
        )

        await provider.before_run(agent=None, session=session, context=context, state=state)  # type: ignore[arg-type]

        assert "Primary retrieval need: Hybrid" in state["query_text"]
        assert "user: Tell me about Cosmos search" in state["query_text"]
        assert state["query_builder_mode"] == "latest_user_with_context"
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


class TestAzureCosmosContextProviderAfterRun:
    async def test_after_run_can_be_disabled(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = AzureCosmosContextProvider(container_client=container, writeback_enabled=False)
        session = AgentSession(session_id="test-session")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["hello"])],
            session_id="s1",
        )

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        container.upsert_item.assert_not_awaited()

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

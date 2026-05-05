# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext

import agent_framework_azure_cosmos._context_provider as context_provider_module
from agent_framework_azure_cosmos import CosmosContextProvider, CosmosContextSearchMode


def _to_async_iter(items: list[Any]) -> AsyncIterator[Any]:
    async def _iterator() -> AsyncIterator[Any]:
        for item in items:
            yield item

    return _iterator()


async def _stub_embed(_: str) -> list[float]:
    return [1.0, 0.0]


def test_provider_uses_existing_container_client() -> None:
    container = MagicMock()
    provider = CosmosContextProvider(
        source_id="ctx",
        container_client=container,
        search_mode=CosmosContextSearchMode.FULL_TEXT,
    )
    assert provider.source_id == "ctx"
    assert provider.search_mode is CosmosContextSearchMode.FULL_TEXT


def test_provider_default_search_mode_is_vector() -> None:
    provider = CosmosContextProvider(container_client=MagicMock(), embedding_function=_stub_embed)
    assert provider.search_mode is CosmosContextSearchMode.VECTOR
    assert provider.vector_field_name == "embedding"


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

    provider = CosmosContextProvider(search_mode=CosmosContextSearchMode.FULL_TEXT)

    cosmos_client_factory.assert_called_once()
    kwargs = cosmos_client_factory.call_args.kwargs
    assert kwargs["url"] == "https://account.documents.azure.com:443/"
    assert kwargs["credential"] == "test-key"
    assert "CosmosContextProvider" in kwargs["user_agent_suffix"]
    assert provider.database_name == "agent-framework"
    assert provider.container_name == "knowledge"
    assert provider.top_k == 4
    assert provider.scan_limit == 9


class TestBeforeRun:
    async def test_skips_when_no_user_or_assistant_messages(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([]))
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="system", contents=["ignore"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        container.query_items.assert_not_called()
        assert context.context_messages.get(provider.source_id) is None

    async def test_full_text_queries_cosmos_and_adds_context(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([
                {"content": "Cosmos DB supports vector search."},
                {"content": "Full text search is also available."},
            ])
        )
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["How does search work?"])], session_id="s1"
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        container.query_items.assert_called_once()
        provider_messages = context.context_messages[provider.source_id]
        assert provider_messages[0].text == provider.context_prompt
        assert len(provider_messages) >= 2
        query_kwargs = container.query_items.call_args.kwargs
        assert "ORDER BY RANK FullTextScore(" in query_kwargs["query"]
        assert "WHERE" not in query_kwargs["query"]

    async def test_vector_mode_builds_vector_distance_query(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Vector search result."}]))
        provider = CosmosContextProvider(container_client=container, embedding_function=_stub_embed)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["Find similar docs"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        assert "ORDER BY VectorDistance(c.embedding, @query_vector)" in query_kwargs["query"]
        assert query_kwargs["parameters"] == [{"name": "@query_vector", "value": [1.0, 0.0]}]

    async def test_hybrid_mode_builds_rrf_query_with_weights(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Hybrid result."}]))
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.HYBRID,
            weights=[2.0, 1.0],
        )
        session = AgentSession(session_id="s")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain hybrid search"])], session_id="s1"
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        assert "ORDER BY RANK RRF(" in query_kwargs["query"]
        assert "[2, 1]" in query_kwargs["query"]

    async def test_hybrid_mode_omits_weights_when_none(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Hybrid result."}]))
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.HYBRID,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["Explain hybrid ranking"])], session_id="s1"
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        assert "RRF(FullTextScore(" in query_kwargs["query"]
        assert "[" not in query_kwargs["query"].split("RRF(", 1)[1]

    async def test_respects_top_k(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([{"content": "Result 1."}, {"content": "Result 2."}, {"content": "Result 3."}])
        )
        provider = CosmosContextProvider(
            container_client=container, top_k=1, search_mode=CosmosContextSearchMode.FULL_TEXT
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["search query"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        # prompt + 1 result
        assert len(context.context_messages[provider.source_id]) == 2

    async def test_respects_partition_key(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(
            container_client=container,
            partition_key="tenant-a",
            search_mode=CosmosContextSearchMode.FULL_TEXT,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["search"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert container.query_items.call_args.kwargs["partition_key"] == "tenant-a"

    async def test_joins_user_and_assistant_messages_for_query(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        state = session.state.setdefault(provider.source_id, {})
        context = SessionContext(
            input_messages=[
                Message(role="user", contents=["Tell me about Cosmos"]),
                Message(role="system", contents=["ignored"]),
                Message(role="assistant", contents=["Vector or hybrid?"]),
                Message(role="user", contents=["Hybrid"]),
            ],
            session_id="s1",
        )

        await provider.before_run(agent=None, session=session, context=context, state=state)  # type: ignore[arg-type]

        assert state["query_text"] == "Tell me about Cosmos\nVector or hybrid?\nHybrid"

    async def test_vector_mode_works_with_non_lexical_input(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Emoji result"}]))
        provider = CosmosContextProvider(container_client=container, embedding_function=_stub_embed)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["🔎"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        container.query_items.assert_called_once()

    async def test_hybrid_falls_back_to_vector_when_no_text_terms(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Emoji result"}]))
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.HYBRID,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["🔎"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        # With no text terms, hybrid gracefully falls back to vector-only via RRF
        container.query_items.assert_called_once()
        query_kwargs = container.query_items.call_args.kwargs
        assert "VectorDistance(" in query_kwargs["query"]
        assert "FullTextScore(" not in query_kwargs["query"]

    async def test_message_field_deserialized_when_valid(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(
            return_value=_to_async_iter([{"message": {"bad": "payload"}, "content": "Fallback content."}])
        )
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["find stuff"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert "Fallback content." in context.context_messages[provider.source_id][1].text

    async def test_container_resolved_from_database_client(self) -> None:
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"text": "Result."}]))
        database_client = MagicMock()
        database_client.get_container_client.return_value = container
        cosmos_client = MagicMock()
        cosmos_client.get_database_client.return_value = database_client

        provider = CosmosContextProvider(
            cosmos_client=cosmos_client,
            database_name="db1",
            container_name="knowledge",
            search_mode=CosmosContextSearchMode.FULL_TEXT,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["search"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        database_client.get_container_client.assert_called_once_with("knowledge")


class TestAfterRun:
    async def test_writeback_stores_messages(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")
        context._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert container.upsert_item.await_count == 2
        first = container.upsert_item.await_args_list[0].args[0]
        second = container.upsert_item.await_args_list[1].args[0]
        assert first["session_id"] == "s1"
        assert first["content"] == "hello"
        assert second["content"] == "hi"
        assert "document_type" not in first

    async def test_excludes_system_messages(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(
            input_messages=[
                Message(role="system", contents=["You are helpful."]),
                Message(role="user", contents=["hello"]),
            ],
            session_id="s1",
        )
        context._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert container.upsert_item.await_count == 2
        roles = [call.args[0]["role"] for call in container.upsert_item.await_args_list]
        assert "system" not in roles
        assert roles == ["user", "assistant"]

    async def test_writeback_includes_embedding_when_function_available(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.VECTOR,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        doc = container.upsert_item.await_args.args[0]
        assert "embedding" in doc
        assert doc["embedding"] == [1.0, 0.0]

    async def test_writeback_skips_embedding_when_no_function(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        doc = container.upsert_item.await_args.args[0]
        assert "embedding" not in doc

    async def test_writeback_includes_agent_and_user_metadata(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        agent = MagicMock()
        agent.name = "test-agent"
        context = SessionContext(
            input_messages=[Message(role="user", contents=["hello"])],
            session_id="s1",
            metadata={"user_id": "user-42"},
        )

        await provider.after_run(
            agent=agent, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )

        doc = container.upsert_item.await_args.args[0]
        assert doc["agent_name"] == "test-agent"
        assert doc["user_id"] == "user-42"

    async def test_writeback_omits_metadata_when_not_available(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")

        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        doc = container.upsert_item.await_args.args[0]
        assert "agent_name" not in doc
        assert "user_id" not in doc

    async def test_writeback_includes_partition_key(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(
            container_client=container,
            partition_key="tenant-a",
            search_mode=CosmosContextSearchMode.FULL_TEXT,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        doc = container.upsert_item.await_args.args[0]
        assert doc["partition_key"] == "tenant-a"

    async def test_writeback_omits_partition_key_when_not_set(self) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        doc = container.upsert_item.await_args.args[0]
        assert "partition_key" not in doc

    async def test_writeback_continues_when_embedding_fails(self) -> None:
        async def _failing_embed(_: str) -> list[float]:
            raise RuntimeError("embedding service down")

        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_failing_embed,
            search_mode=CosmosContextSearchMode.VECTOR,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert container.upsert_item.await_count == 1
        doc = container.upsert_item.await_args.args[0]
        assert doc["content"] == "hello"
        assert "embedding" not in doc

    async def test_generates_session_id_when_missing(self, caplog: pytest.LogCaptureFixture) -> None:
        container = MagicMock()
        container.upsert_item = AsyncMock()
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id=None)

        with caplog.at_level("WARNING"):
            await provider.after_run(
                agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
            )  # type: ignore[arg-type]

        doc = container.upsert_item.await_args.args[0]
        uuid.UUID(doc["session_id"])
        assert "session_id" in caplog.text


class TestLifecycle:
    async def test_close_closes_owned_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        database_client = MagicMock()
        cosmos_client = MagicMock()
        cosmos_client.get_database_client.return_value = database_client
        cosmos_client.close = AsyncMock()
        cosmos_client_factory = MagicMock(return_value=cosmos_client)

        monkeypatch.setattr(context_provider_module, "CosmosClient", cosmos_client_factory)

        provider = CosmosContextProvider(
            endpoint="https://account.documents.azure.com:443/",
            credential="test-key",
            database_name="db1",
            container_name="knowledge",
            search_mode=CosmosContextSearchMode.FULL_TEXT,
        )

        await provider.close()
        cosmos_client.close.assert_awaited_once()


class TestFullTextChunking:
    """Tests for the RRF chunking bypass of the 5-term FullTextScore limit."""

    async def test_full_text_5_terms_no_rrf(self) -> None:
        """With exactly 5 terms, use a single FullTextScore (no RRF wrapping)."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        # 5 unique words
        context = SessionContext(
            input_messages=[Message(role="user", contents=["alpha beta gamma delta epsilon"])], session_id="s1"
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        assert "ORDER BY RANK FullTextScore(c.content" in query_kwargs["query"]
        assert "RRF(" not in query_kwargs["query"]
        assert len(query_kwargs["parameters"]) == 5

    async def test_full_text_6_terms_uses_rrf(self) -> None:
        """With 6 terms, chunk into RRF(FTS(5), FTS(1))."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["alpha beta gamma delta epsilon zeta"])], session_id="s1"
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        query = query_kwargs["query"]
        assert "ORDER BY RANK RRF(" in query
        # Two FullTextScore components
        assert query.count("FullTextScore(") == 2
        assert len(query_kwargs["parameters"]) == 6

    async def test_full_text_10_terms_two_batches(self) -> None:
        """With 10 terms, chunk into RRF(FTS(5), FTS(5))."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        terms = " ".join(f"word{i}" for i in range(10))
        context = SessionContext(input_messages=[Message(role="user", contents=[terms])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        query = query_kwargs["query"]
        assert "ORDER BY RANK RRF(" in query
        assert query.count("FullTextScore(") == 2
        assert len(query_kwargs["parameters"]) == 10
        # No weights for full-text-only RRF
        rrf_section = query.split("RRF(", 1)[1]
        assert "[" not in rrf_section

    async def test_full_text_7_terms_batch_5_plus_2(self) -> None:
        """With 7 terms, chunk into RRF(FTS(5), FTS(2))."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(container_client=container, search_mode=CosmosContextSearchMode.FULL_TEXT)
        session = AgentSession(session_id="s")
        terms = " ".join(f"term{i}" for i in range(7))
        context = SessionContext(input_messages=[Message(role="user", contents=[terms])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        query = query_kwargs["query"]
        assert query.count("FullTextScore(") == 2
        # First batch has 5 params, second has 2
        params = query_kwargs["parameters"]
        assert params[0]["name"] == "@term0"
        assert params[4]["name"] == "@term4"
        assert params[5]["name"] == "@term5"
        assert params[6]["name"] == "@term6"
        assert len(params) == 7

    async def test_hybrid_6_terms_uses_rrf_with_all_components(self) -> None:
        """Hybrid with 6 terms: RRF(FTS(5), FTS(1), VD)."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.HYBRID,
        )
        session = AgentSession(session_id="s")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["alpha beta gamma delta epsilon zeta"])], session_id="s1"
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        query = query_kwargs["query"]
        assert "ORDER BY RANK RRF(" in query
        assert query.count("FullTextScore(") == 2
        assert "VectorDistance(" in query
        # 6 term params + 1 vector param
        assert len(query_kwargs["parameters"]) == 7

    async def test_hybrid_6_terms_with_weights_expands_correctly(self) -> None:
        """Hybrid with 6 terms + weights=[2.0, 1.0]: expands to [1, 1, 1] (2/2 per FTS batch, 1 for VD)."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.HYBRID,
            weights=[2.0, 1.0],
        )
        session = AgentSession(session_id="s")
        context = SessionContext(
            input_messages=[Message(role="user", contents=["alpha beta gamma delta epsilon zeta"])], session_id="s1"
        )

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        query = query_kwargs["query"]
        # 2 FTS batches + 1 VD = 3 components, weights should be [2/2, 2/2, 1] = [1, 1, 1]
        assert "[1, 1, 1]" in query

    async def test_hybrid_5_terms_with_weights_unchanged(self) -> None:
        """Hybrid with ≤5 terms + weights: single FTS, no expansion needed."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.HYBRID,
            weights=[2.0, 1.0],
        )
        session = AgentSession(session_id="s")
        context = SessionContext(input_messages=[Message(role="user", contents=["alpha beta gamma"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        query = query_kwargs["query"]
        assert "[2, 1]" in query
        assert query.count("FullTextScore(") == 1

    async def test_hybrid_many_terms_weights_preserve_balance(self) -> None:
        """With 15 terms and weights=[6.0, 3.0], each of 3 FTS batches gets 2.0, VD gets 3.0."""
        container = MagicMock()
        container.query_items = MagicMock(return_value=_to_async_iter([{"content": "Result."}]))
        provider = CosmosContextProvider(
            container_client=container,
            embedding_function=_stub_embed,
            search_mode=CosmosContextSearchMode.HYBRID,
            weights=[6.0, 3.0],
        )
        session = AgentSession(session_id="s")
        terms = " ".join(f"w{i}" for i in range(15))
        context = SessionContext(input_messages=[Message(role="user", contents=[terms])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        query_kwargs = container.query_items.call_args.kwargs
        query = query_kwargs["query"]
        assert query.count("FullTextScore(") == 3
        # 3 batches × 2.0 + VD 3.0
        assert "[2, 2, 2, 3]" in query

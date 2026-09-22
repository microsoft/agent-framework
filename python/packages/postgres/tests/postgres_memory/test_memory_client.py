# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatResponse, Embedding, GeneratedEmbeddings, Message
from agent_framework.exceptions import IntegrationInvalidResponseException
from psycopg import AsyncConnection, Error

from agent_framework_postgres import (
    PostgresMemoryClient,
    PostgresMemoryClientOptions,
    PostgresMemoryRecord,
    PostgresMemoryScope,
    PostgresMemoryType,
    PostgresMemoryVectorIndexKind,
)
from agent_framework_postgres._memory_store import (
    _PostgresMemoryRerankResult,
    _PostgresMemoryStore,
    _ProcessingState,
)


class _EmbeddingClient:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.vector = vector or [1.0, 0.0, 0.0]
        self.inputs: list[str] = []

    async def get_embeddings(self, values: list[str], *, options: Any = None) -> GeneratedEmbeddings[list[float], Any]:
        self.inputs.extend(values)
        return GeneratedEmbeddings([Embedding(vector=list(self.vector)) for _ in values], options=options)


class _ChatClient:
    def __init__(self, *responses: str, on_response: Callable[[], None] | None = None) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.responses = list(responses)
        self.messages: list[list[Message]] = []
        self.on_response = on_response

    async def get_response(self, messages: list[Message], **kwargs: Any) -> ChatResponse[Any]:
        self.messages.append(messages)
        if self.on_response is not None:
            self.on_response()
        return ChatResponse(messages=[Message(role="assistant", contents=[self.responses.pop(0)])])


def _turn(turn_id: int, role: str, content: str) -> PostgresMemoryRecord:
    now = datetime.now(timezone.utc)
    return PostgresMemoryRecord(
        id=turn_id,
        memory_type=PostgresMemoryType.TURN,
        content=content,
        user_id="user-1",
        thread_id="thread-1",
        role=role,
        created_at=now,
        updated_at=now,
    )


def _memory(memory_id: int, content: str, *, score: float | None = None) -> PostgresMemoryRecord:
    now = datetime.now(timezone.utc)
    return PostgresMemoryRecord(
        id=memory_id,
        memory_type=PostgresMemoryType.FACT,
        content=content,
        user_id="user-1",
        confidence=0.9,
        score=score,
        created_at=now,
        updated_at=now,
    )


def _create_client(
    store: MagicMock,
    chat_client: _ChatClient,
    *,
    embedding_client: _EmbeddingClient | None = None,
    options: PostgresMemoryClientOptions | None = None,
) -> PostgresMemoryClient:
    client = PostgresMemoryClient(
        embedding_generator=cast(Any, embedding_client or _EmbeddingClient()),
        chat_client=cast(Any, chat_client),
        client=MagicMock(spec=AsyncConnection),
        options=options or PostgresMemoryClientOptions(embedding_dimensions=3, auto_process=False),
    )
    client._store = store
    return client


def _store() -> MagicMock:
    store = MagicMock()
    store.ensure_schema = AsyncMock()
    store.get_processing_state = AsyncMock(return_value=_ProcessingState())
    store.get_turns_after = AsyncMock(return_value=[])
    store.get_active_memories = AsyncMock(return_value=[])
    store.find_duplicate = AsyncMock(return_value=None)
    store.insert_derived_memory = AsyncMock(return_value=10)
    store.upsert_processing_state = AsyncMock()
    store.search = AsyncMock(return_value=[])
    store.rerank = AsyncMock(return_value=[])
    store.compute_scope_key = MagicMock(return_value="scope-key")
    return store


def test_scope_and_options_validate_identity_and_dimensions() -> None:
    scope = PostgresMemoryScope(
        user_id=" user-1 ",
        thread_id=" thread-1 ",
        application_id=" app ",
        agent_id=" agent ",
    )
    assert scope == PostgresMemoryScope(
        user_id="user-1",
        thread_id="thread-1",
        application_id="app",
        agent_id="agent",
    )
    assert scope.to_user_scope().thread_id is None

    with pytest.raises(ValueError, match="user_id"):
        PostgresMemoryScope(user_id=" ")
    with pytest.raises(ValueError, match="embedding_dimensions"):
        PostgresMemoryClientOptions(embedding_dimensions=2001)
    with pytest.raises(ValueError, match="vector_index_kind"):
        PostgresMemoryClientOptions(vector_index_kind=cast(Any, "disk_ann"))
    with pytest.raises(ValueError, match="reranking_candidate_count"):
        PostgresMemoryClientOptions(reranking_candidate_count=0)
    with pytest.raises(ValueError, match="azure_ai_reranker_model"):
        PostgresMemoryClientOptions(enable_azure_ai_reranking=True, azure_ai_reranker_model=" ")
    with pytest.raises(ValueError, match="dedupe"):
        PostgresMemoryClientOptions(dedupe_similarity_threshold=float("nan"))


@pytest.mark.parametrize(
    ("index_kind", "created_kind", "dropped_name"),
    [
        (PostgresMemoryVectorIndexKind.HNSW, "hnsw", "ix_memory_memories_diskann"),
        (PostgresMemoryVectorIndexKind.DISK_ANN, "diskann", "ix_memory_memories_embedding"),
    ],
)
def test_memory_vector_index_sql_replaces_the_other_managed_index(
    index_kind: PostgresMemoryVectorIndexKind,
    created_kind: str,
    dropped_name: str,
) -> None:
    options = PostgresMemoryClientOptions(
        table_name="memory",
        embedding_dimensions=3,
        vector_index_kind=index_kind,
        auto_process=False,
    )
    store = _PostgresMemoryStore(MagicMock(), options)

    statements = store._get_vector_index_statements(
        store._memories,
        "ix_memory_memories_embedding",
        "ix_memory_memories_diskann",
    )
    rendered = [statement.as_string() for statement in statements]

    assert dropped_name in rendered[0]
    assert f"USING {created_kind}" in rendered[1]


async def test_search_reranks_expanded_candidate_pool() -> None:
    store = _store()
    candidates = [
        _memory(1, "PostgreSQL tuning guidance.", score=0.03),
        _memory(2, "The user prefers PostgreSQL.", score=0.02),
        _memory(3, "A MySQL migration occurred.", score=0.01),
    ]
    store.search.return_value = candidates
    store.rerank.return_value = [
        _PostgresMemoryRerankResult(id=2, rank=1, relevance_score=0.98),
        _PostgresMemoryRerankResult(id=1, rank=2, relevance_score=0.63),
        _PostgresMemoryRerankResult(id=3, rank=3, relevance_score=0.12),
    ]
    options = PostgresMemoryClientOptions(
        embedding_dimensions=3,
        enable_azure_ai_reranking=True,
        auto_process=False,
    )
    client = _create_client(store, _ChatClient(), options=options)

    results = await client.search(PostgresMemoryScope(user_id="user-1"), "preferred database", top_k=2)

    assert [result.id for result in results] == [2, 1]
    assert [result.reranker_score for result in results] == [0.98, 0.63]
    assert [result.score for result in results] == [0.02, 0.03]
    assert store.search.await_args.args[4] == 25
    store.rerank.assert_awaited_once_with("preferred database", candidates, "cohere-rerank-v3.5")


async def test_search_returns_hybrid_order_when_reranking_fails() -> None:
    store = _store()
    candidates = [
        _memory(1, "First hybrid result."),
        _memory(2, "Second hybrid result."),
        _memory(3, "Third hybrid result."),
    ]
    store.search.return_value = candidates
    store.rerank.side_effect = Error("Reranker unavailable.")
    options = PostgresMemoryClientOptions(
        embedding_dimensions=3,
        enable_azure_ai_reranking=True,
        auto_process=False,
    )
    client = _create_client(store, _ChatClient(), options=options)

    results = await client.search(PostgresMemoryScope(user_id="user-1"), "database", top_k=2)

    assert [result.id for result in results] == [1, 2]
    assert all(result.reranker_score is None for result in results)


async def test_store_rerank_batches_candidates_in_one_database_call() -> None:
    client = MagicMock()
    connection = MagicMock()
    cursor = MagicMock()
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=[("2", 1, 0.98), ("1", 2, 0.63)])
    connection.cursor.return_value.__aenter__ = AsyncMock(return_value=cursor)
    connection.cursor.return_value.__aexit__ = AsyncMock(return_value=None)
    client.connection.return_value.__aenter__ = AsyncMock(return_value=connection)
    client.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    store = _PostgresMemoryStore(
        client,
        PostgresMemoryClientOptions(embedding_dimensions=3, auto_process=False),
    )
    candidates = [_memory(1, "First"), _memory(2, "Second")]

    results = await store.rerank("preferred database", candidates, "cohere-rerank-v3.5")

    assert [(result.id, result.rank, result.relevance_score) for result in results] == [
        (2, 1, 0.98),
        (1, 2, 0.63),
    ]
    params = cursor.execute.await_args.args[1]
    assert params == ["preferred database", ["First", "Second"], ["1", "2"], "cohere-rerank-v3.5"]
    cursor.execute.assert_awaited_once()


async def test_extract_memories_inserts_typed_records_and_advances_checkpoint() -> None:
    store = _store()
    store.get_turns_after.return_value = [
        _turn(1, "user", "I prefer Python."),
        _turn(2, "agent", "I will remember that."),
    ]
    chat_client = _ChatClient(
        """
        [{"content":"User prefers Python","memory_type":"fact","confidence":0.95,
          "salience":0.8,"tags":["language"]}]
        """
    )
    client = _create_client(store, chat_client)
    scope = PostgresMemoryScope(user_id="user-1", thread_id="thread-1")

    assert await client.extract_memories(scope) == 1

    inserted = store.insert_derived_memory.await_args.args
    assert inserted[0] == scope
    assert inserted[1] is PostgresMemoryType.FACT
    assert inserted[2] == "User prefers Python"
    assert inserted[3] == 0.95
    assert inserted[4] == 0.8
    assert inserted[5] == ("language",)
    state = store.upsert_processing_state.await_args.args[1]
    assert state.fact_through_turn_id == 2
    assert state.extraction_runs == 1


async def test_malformed_extraction_does_not_advance_checkpoint() -> None:
    store = _store()
    store.get_turns_after.return_value = [_turn(1, "user", "Remember this.")]
    client = _create_client(store, _ChatClient("not json"))

    with pytest.raises(IntegrationInvalidResponseException, match="valid JSON array"):
        await client.extract_memories(PostgresMemoryScope(user_id="user-1", thread_id="thread-1"))

    store.upsert_processing_state.assert_not_awaited()
    store.insert_derived_memory.assert_not_awaited()


async def test_partially_malformed_extraction_is_rejected_as_one_response() -> None:
    store = _store()
    store.get_turns_after.return_value = [_turn(1, "user", "Remember this.")]
    client = _create_client(
        store,
        _ChatClient(
            '[{"content":"Valid","memory_type":"fact","confidence":0.8},'
            '{"content":"Missing confidence","memory_type":"fact"}]'
        ),
    )

    with pytest.raises(IntegrationInvalidResponseException, match="confidence"):
        await client.extract_memories(PostgresMemoryScope(user_id="user-1", thread_id="thread-1"))

    store.upsert_processing_state.assert_not_awaited()
    store.insert_derived_memory.assert_not_awaited()


async def test_duplicate_extraction_still_advances_checkpoint() -> None:
    store = _store()
    store.get_turns_after.return_value = [_turn(3, "user", "I prefer Python.")]
    store.find_duplicate.return_value = MagicMock()
    client = _create_client(
        store,
        _ChatClient('[{"content":"User prefers Python","memory_type":"fact","confidence":0.9}]'),
    )

    assert await client.extract_memories(PostgresMemoryScope(user_id="user-1", thread_id="thread-1")) == 0
    store.insert_derived_memory.assert_not_awaited()
    assert store.upsert_processing_state.await_args.args[1].fact_through_turn_id == 3


async def test_embedding_response_shape_is_validated() -> None:
    store = _store()
    client = _create_client(
        store,
        _ChatClient(),
        embedding_client=_EmbeddingClient([1.0, 0.0]),
    )

    with pytest.raises(IntegrationInvalidResponseException, match="2 dimensions"):
        await client.search(
            PostgresMemoryScope(user_id="user-1"),
            "python",
        )

    store.search.assert_not_awaited()


async def test_upsert_normalizes_assistant_role_without_auto_processing() -> None:
    store = _store()
    store.insert_turn = AsyncMock(return_value=42)
    client = _create_client(store, _ChatClient())
    scope = PostgresMemoryScope(user_id="user-1", thread_id="thread-1")

    assert await client.upsert_memory(scope, "assistant", "  response  ") == 42
    store.insert_turn.assert_awaited_once_with(scope, "agent", "response", None)
    assert not client._background_tasks


async def test_flush_timeout_leaves_unfinished_processing_running() -> None:
    client = _create_client(_store(), _ChatClient())
    release = asyncio.Event()

    async def _wait() -> None:
        await release.wait()

    task = asyncio.create_task(_wait())
    client._background_tasks.add(task)
    task.add_done_callback(client._background_tasks.discard)

    await client.flush(timeout=0)

    assert not task.done()
    release.set()
    await client.flush()
    assert task.done()


async def test_flush_rejects_invalid_timeout() -> None:
    client = _create_client(_store(), _ChatClient())

    with pytest.raises(ValueError, match="timeout"):
        await client.flush(timeout=-1)
    with pytest.raises(ValueError, match="timeout"):
        await client.flush(timeout=float("nan"))


async def test_close_cancels_processing_left_after_timeout() -> None:
    client = _create_client(_store(), _ChatClient())
    started = asyncio.Event()

    async def _wait() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(_wait())
    client._background_tasks.add(task)
    task.add_done_callback(client._background_tasks.discard)
    await started.wait()

    with patch.object(client._client, "close", new_callable=AsyncMock) as close:
        await client.close(timeout=0)

    assert task.cancelled()
    assert not client._background_tasks
    close.assert_awaited_once()


def test_auto_processing_rejects_one_borrowed_connection() -> None:
    with pytest.raises(ValueError, match="connection pool"):
        PostgresMemoryClient(
            embedding_generator=cast(Any, _EmbeddingClient()),
            chat_client=cast(Any, _ChatClient()),
            client=MagicMock(spec=AsyncConnection),
            options=PostgresMemoryClientOptions(embedding_dimensions=3),
        )


def test_scope_keys_do_not_collide_when_identifiers_contain_separators() -> None:
    left = PostgresMemoryScope(
        user_id="d",
        thread_id="e",
        application_id="a\x1fb",
        agent_id="c",
    )
    right = PostgresMemoryScope(
        user_id="c\x1fd",
        thread_id="e",
        application_id="a",
        agent_id="b",
    )

    assert _PostgresMemoryStore.compute_scope_key(
        left,
        include_thread=True,
    ) != _PostgresMemoryStore.compute_scope_key(
        right,
        include_thread=True,
    )


async def test_user_summary_uses_turn_cutoff_captured_before_model_call() -> None:
    store = _store()
    now = datetime.now(timezone.utc)
    store.get_latest_summary = AsyncMock(return_value=(None, 0))
    store.get_turn_stats_after = AsyncMock(return_value=(2, 10))
    store.get_active_memories.return_value = [
        PostgresMemoryRecord(
            id=1,
            memory_type=PostgresMemoryType.FACT,
            content="User prefers Python.",
            user_id="user-1",
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    ]
    store.get_recent_thread_summaries = AsyncMock(return_value=[])
    store.insert_summary = AsyncMock(return_value=20)
    store.upsert_processing_state = AsyncMock()

    def add_turn_during_model_call() -> None:
        store.get_turn_stats_after.return_value = (3, 11)

    client = _create_client(
        store,
        _ChatClient("User prefers Python.", on_response=add_turn_during_model_call),
    )

    await client.generate_user_summary(PostgresMemoryScope(user_id="user-1"))

    insert_call = store.insert_summary.await_args
    assert insert_call is not None
    assert insert_call.args[-1] == 10
    assert store.get_turn_stats_after.await_count == 1
    processing_call = store.upsert_processing_state.await_args
    assert processing_call is not None
    assert processing_call.args[1].user_summary_through_turn_id == 10


async def test_client_context_entry_closes_owned_pool_after_schema_failure() -> None:
    client = PostgresMemoryClient(
        embedding_generator=cast(Any, _EmbeddingClient()),
        chat_client=cast(Any, _ChatClient()),
        connection_string="host=unused",
        options=PostgresMemoryClientOptions(embedding_dimensions=3, auto_process=False),
    )
    with (
        patch.object(client._store, "ensure_schema", new=AsyncMock(side_effect=RuntimeError("schema failed"))),
        patch.object(client._client, "close", new_callable=AsyncMock) as close,
        pytest.raises(RuntimeError, match="schema failed"),
    ):
        await client.__aenter__()

    close.assert_awaited_once()

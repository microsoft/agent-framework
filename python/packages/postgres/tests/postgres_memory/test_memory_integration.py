# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from collections import deque
from collections.abc import Sequence
from typing import Any, cast

import pytest
from agent_framework import ChatResponse, Embedding, GeneratedEmbeddings, Message
from agent_framework.exceptions import IntegrationInvalidResponseException
from psycopg import sql

from agent_framework_postgres import (
    PostgresMemoryClient,
    PostgresMemoryClientOptions,
    PostgresMemoryScope,
    PostgresMemoryType,
)
from agent_framework_postgres._memory_store import _ProcessingState

pytestmark = [pytest.mark.flaky, pytest.mark.integration]


class _EmbeddingClient:
    def __init__(self) -> None:
        self.additional_properties: dict[str, Any] = {}

    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: Any = None,
    ) -> GeneratedEmbeddings[list[float], Any]:
        embeddings: list[Embedding[list[float]]] = []
        for value in values:
            normalized = value.lower()
            if "python" in normalized:
                vector = [1.0, 0.0, 0.0]
            elif "travel" in normalized:
                vector = [0.0, 1.0, 0.0]
            else:
                vector = [0.0, 0.0, 1.0]
            embeddings.append(Embedding(vector=vector))
        return GeneratedEmbeddings(embeddings, options=options)


class _ChatClient:
    def __init__(self, *responses: str) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.responses: deque[str] = deque(responses)

    async def get_response(self, messages: Sequence[Message], **kwargs: Any) -> ChatResponse[Any]:
        return ChatResponse(messages=[Message(role="assistant", contents=[self.responses.popleft()])])


def _options(schema: str, table_name: str = "memory") -> PostgresMemoryClientOptions:
    return PostgresMemoryClientOptions(
        schema=schema,
        table_name=table_name,
        embedding_dimensions=3,
        auto_process=False,
    )


async def test_schema_turns_extraction_hybrid_search_and_scope_isolation(database: Any) -> None:
    connection, schema = database
    chat = _ChatClient(
        '[{"content":"User prefers Python","memory_type":"fact","confidence":0.95}]',
        '[{"content":"User prefers travel by train","memory_type":"fact","confidence":0.9}]',
    )
    client = PostgresMemoryClient(
        embedding_generator=_EmbeddingClient(),
        chat_client=cast(Any, chat),
        client=connection,
        options=_options(schema),
    )
    scope = PostgresMemoryScope(
        user_id="user-1",
        thread_id="thread-1",
        application_id="app-1",
        agent_id="agent-1",
    )
    other_scope = PostgresMemoryScope(
        user_id="user-1",
        thread_id="thread-2",
        application_id="app-2",
        agent_id="agent-1",
    )

    await client.ensure_schema()
    await client.upsert_memory(scope, "user", "I prefer Python for backend services.")
    await client.upsert_memory(scope, "assistant", "I will remember that.")
    await client.upsert_memory(other_scope, "user", "I prefer travel by train.")
    assert await client.extract_memories(scope) == 1
    assert await client.extract_memories(other_scope) == 1

    turns = await client.get_thread(scope)
    assert [turn.role for turn in turns] == ["user", "agent"]
    results = await client.search(scope.to_user_scope(), "python", top_k=5)
    assert [result.content for result in results] == ["User prefers Python"]
    assert results[0].score is not None
    assert (
        await client.search(
            PostgresMemoryScope(
                user_id="user-1",
                application_id="app-1",
                agent_id="different-agent",
            ),
            "python",
        )
        == []
    )

    cursor = await connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
        [schema],
    )
    assert [row[0] for row in await cursor.fetchall()] == [
        "memory_memories",
        "memory_processing",
        "memory_summaries",
        "memory_turns",
    ]


async def test_malformed_extraction_preserves_unprocessed_turns(database: Any) -> None:
    connection, schema = database
    chat = _ChatClient(
        "not json",
        '[{"content":"User prefers Python","memory_type":"fact","confidence":0.9}]',
    )
    client = PostgresMemoryClient(
        embedding_generator=_EmbeddingClient(),
        chat_client=cast(Any, chat),
        client=connection,
        options=_options(schema),
    )
    scope = PostgresMemoryScope(user_id="user-1", thread_id="thread-1")
    await client.upsert_memory(scope, "user", "Remember that I prefer Python.")

    with pytest.raises(IntegrationInvalidResponseException, match="valid JSON array"):
        await client.extract_memories(scope)

    assert await client.extract_memories(scope) == 1
    assert [memory.content for memory in await client.get_memories(scope.to_user_scope())] == ["User prefers Python"]


async def test_summary_versions_and_processing_checkpoints_are_concurrency_safe(database: Any) -> None:
    connection, schema = database
    client = PostgresMemoryClient(
        embedding_generator=_EmbeddingClient(),
        chat_client=cast(Any, _ChatClient()),
        connection_string=os.environ["POSTGRES_TEST_CONNECTION_STRING"],
        options=_options(schema),
    )
    scope = PostgresMemoryScope(user_id="user-1", thread_id="thread-1")
    await client.ensure_schema()

    await asyncio.gather(
        client._store.insert_summary(scope, PostgresMemoryType.SUMMARY, "summary one", [1.0, 0.0, 0.0], 1),
        client._store.insert_summary(scope, PostgresMemoryType.SUMMARY, "summary two", [1.0, 0.0, 0.0], 2),
    )
    cursor = await connection.execute(
        sql.SQL("SELECT version, covers_through_turn_id FROM {}.{} ORDER BY version").format(
            sql.Identifier(schema),
            sql.Identifier("memory_summaries"),
        )
    )
    summary_rows = await cursor.fetchall()
    assert [row[0] for row in summary_rows] in ([1], [1, 2])
    assert summary_rows[-1][1] == 2

    scope_key = client._store.compute_scope_key(scope, include_thread=True)
    await client._store.upsert_processing_state(
        scope_key,
        _ProcessingState(
            fact_through_turn_id=10,
            summary_through_turn_id=11,
            user_summary_through_turn_id=12,
            extraction_runs=5,
        ),
    )
    await client._store.upsert_processing_state(
        scope_key,
        _ProcessingState(
            fact_through_turn_id=1,
            summary_through_turn_id=2,
            user_summary_through_turn_id=3,
            extraction_runs=1,
        ),
    )
    assert await client._store.get_processing_state(scope_key) == _ProcessingState(
        fact_through_turn_id=10,
        summary_through_turn_id=11,
        user_summary_through_turn_id=12,
        extraction_runs=5,
    )
    await client.close()

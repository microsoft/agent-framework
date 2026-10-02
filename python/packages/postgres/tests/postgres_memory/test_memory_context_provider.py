# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import AgentResponse, AgentSession, Message, SessionContext

from agent_framework_postgres import (
    PostgresMemoryClientOptions,
    PostgresMemoryContextProvider,
    PostgresMemoryContextProviderState,
    PostgresMemoryRecord,
    PostgresMemoryScope,
    PostgresMemoryType,
)
from agent_framework_postgres._feature_usage import FeatureIndex

_STUB_AGENT: Any = None


def _memory(
    memory_id: int,
    memory_type: PostgresMemoryType,
    content: str,
    *,
    confidence: float | None = None,
) -> PostgresMemoryRecord:
    now = datetime.now(timezone.utc)
    return PostgresMemoryRecord(
        id=memory_id,
        memory_type=memory_type,
        content=content,
        user_id="user-1",
        thread_id=None,
        confidence=confidence,
        created_at=now,
        updated_at=now,
    )


def _client() -> AsyncMock:
    client = AsyncMock()
    client.options = PostgresMemoryClientOptions()
    client.search = AsyncMock(return_value=[])
    client.get_user_summary = AsyncMock(return_value=None)
    client.upsert_memory = AsyncMock()
    client.ensure_schema = AsyncMock()
    client.process_now = AsyncMock()
    client.flush = AsyncMock()
    client.close = AsyncMock()
    return client


async def test_before_run_injects_memories_and_user_summary() -> None:
    memory_client = _client()
    memory_client.search.return_value = [_memory(1, PostgresMemoryType.FACT, "User prefers Python.", confidence=0.95)]
    memory_client.get_user_summary.return_value = _memory(
        2,
        PostgresMemoryType.USER_SUMMARY,
        "The user values concise examples.",
    )
    provider = PostgresMemoryContextProvider(
        memory_client=cast(Any, memory_client),
        application_id="app",
        agent_id="agent",
    )
    session = AgentSession(session_id="thread-1")
    context = SessionContext(
        session_id="thread-1",
        input_messages=[Message(role="user", contents=["What do I prefer?"])],
    )

    await provider.before_run(
        agent=_STUB_AGENT,
        session=session,
        context=context,
        state={"user_id": "user-1"},
    )

    search_scope = memory_client.search.await_args.args[0]
    assert search_scope == PostgresMemoryScope(
        user_id="user-1",
        application_id="app",
        agent_id="agent",
    )
    assert memory_client.search.await_args.args[1] == "What do I prefer?"
    messages = context.context_messages["postgres_memory"]
    assert len(messages) == 2
    assert "User prefers Python" in messages[0].text
    assert "untrusted reference information" in messages[1].text


async def test_summary_retrieval_is_independent_of_search_failure() -> None:
    memory_client = _client()
    memory_client.search.side_effect = RuntimeError("search unavailable")
    memory_client.get_user_summary.return_value = _memory(
        2,
        PostgresMemoryType.USER_SUMMARY,
        "Stable profile.",
    )
    provider = PostgresMemoryContextProvider(memory_client=cast(Any, memory_client), user_id="user-1")
    context = SessionContext(
        session_id="thread-1",
        input_messages=[Message(role="user", contents=["Question"])],
    )

    await provider.before_run(
        agent=_STUB_AGENT,
        session=AgentSession(session_id="thread-1"),
        context=context,
        state={},
    )

    assert "Stable profile." in context.context_messages["postgres_memory"][0].text


async def test_memory_retrieval_is_independent_of_summary_failure() -> None:
    memory_client = _client()
    memory_client.search.return_value = [_memory(1, PostgresMemoryType.FACT, "User prefers Python.", confidence=0.95)]
    memory_client.get_user_summary.side_effect = RuntimeError("summary unavailable")
    provider = PostgresMemoryContextProvider(memory_client=cast(Any, memory_client), user_id="user-1")
    context = SessionContext(
        session_id="thread-1",
        input_messages=[Message(role="user", contents=["Question"])],
    )

    await provider.before_run(
        agent=_STUB_AGENT,
        session=AgentSession(session_id="thread-1"),
        context=context,
        state={},
    )

    assert "User prefers Python." in context.context_messages["postgres_memory"][0].text


async def test_after_run_stores_supported_messages_with_session_thread() -> None:
    memory_client = _client()
    provider = PostgresMemoryContextProvider(memory_client=cast(Any, memory_client))
    session = AgentSession(session_id="thread-1")
    context = SessionContext(
        session_id="thread-1",
        input_messages=[
            Message(role="user", contents=[" request "]),
            Message(role="tool", contents=["tool output"]),
        ],
    )
    context._response = AgentResponse(
        messages=[
            Message(role="assistant", contents=[" response "]),
            Message(role="assistant", contents=["  "]),
        ]
    )

    await provider.after_run(
        agent=_STUB_AGENT,
        session=session,
        context=context,
        state={"user_id": "user-1"},
    )

    scope = PostgresMemoryScope(user_id="user-1", thread_id="thread-1")
    assert memory_client.upsert_memory.await_args_list[0].args == (scope, "user", "request")
    assert memory_client.upsert_memory.await_args_list[1].args == (scope, "assistant", "response")
    assert memory_client.upsert_memory.await_count == 2


async def test_missing_stable_user_id_fails_before_storage() -> None:
    memory_client = _client()
    provider = PostgresMemoryContextProvider(memory_client=cast(Any, memory_client))
    context = SessionContext(
        session_id="thread-1",
        input_messages=[Message(role="user", contents=["request"])],
    )

    with pytest.raises(ValueError, match="stable user identifier"):
        await provider.after_run(
            agent=_STUB_AGENT,
            session=AgentSession(session_id="thread-1"),
            context=context,
            state={},
        )

    memory_client.upsert_memory.assert_not_awaited()


async def test_session_id_user_fallback_is_explicit_and_session_scoped() -> None:
    memory_client = _client()
    provider = PostgresMemoryContextProvider(
        memory_client=cast(Any, memory_client),
        fallback_to_session_id=True,
    )
    session = AgentSession(session_id="thread-1")
    context = SessionContext(
        session_id="thread-1",
        input_messages=[Message(role="user", contents=["request"])],
    )

    await provider.after_run(
        agent=_STUB_AGENT,
        session=session,
        context=context,
        state={},
    )

    scope = memory_client.upsert_memory.await_args.args[0]
    assert scope == PostgresMemoryScope(user_id="thread-1", thread_id="thread-1")


def test_auto_extract_configures_only_provider_created_clients() -> None:
    owned = _client()
    with patch(
        "agent_framework_postgres._memory_context_provider.PostgresMemoryClient",
        return_value=owned,
    ) as client_type:
        provider = PostgresMemoryContextProvider(
            embedding_generator=cast(Any, object()),
            chat_client=cast(Any, object()),
            connection_string="host=unused",
            client_options=PostgresMemoryClientOptions(embedding_dimensions=3),
            auto_extract=False,
            user_id="user-1",
        )

    options = client_type.call_args.kwargs["options"]
    assert options.embedding_dimensions == 3
    assert options.auto_process is False
    assert provider.auto_extract is False

    with pytest.raises(ValueError, match="auto_extract only applies"):
        PostgresMemoryContextProvider(
            memory_client=cast(Any, _client()),
            auto_extract=False,
            user_id="user-1",
        )


async def test_process_now_resolves_scope_and_flush_forwards_timeout() -> None:
    memory_client = _client()
    provider = PostgresMemoryContextProvider(
        memory_client=cast(Any, memory_client),
        application_id="app",
        agent_id="agent",
        user_id="user-1",
    )
    session = AgentSession(session_id="thread-1")

    await provider.process_now(session=session, state={"thread_id": "custom-thread"})
    await provider.flush(timeout=1.5)

    memory_client.process_now.assert_awaited_once_with(
        PostgresMemoryScope(
            user_id="user-1",
            thread_id="custom-thread",
            application_id="app",
            agent_id="agent",
        )
    )
    memory_client.flush.assert_awaited_once_with(timeout=1.5)


async def test_scope_resolver_supports_independent_storage_and_search_scopes() -> None:
    memory_client = _client()
    storage_scope = PostgresMemoryScope(
        user_id="storage-user",
        thread_id="storage-thread",
        application_id="storage-app",
    )
    search_scope = PostgresMemoryScope(
        user_id="search-user",
        application_id="search-app",
    )
    provider = PostgresMemoryContextProvider(
        memory_client=cast(Any, memory_client),
        scope_resolver=lambda session, state: PostgresMemoryContextProviderState(
            storage_scope,
            search_scope,
        ),
    )
    session = AgentSession(session_id="ignored-thread")
    context = SessionContext(
        session_id="ignored-thread",
        input_messages=[Message(role="user", contents=["question"])],
    )

    await provider.before_run(agent=_STUB_AGENT, session=session, context=context, state={})
    await provider.after_run(agent=_STUB_AGENT, session=session, context=context, state={})
    await provider.process_now(session=session, state={})

    assert memory_client.search.await_args.args[0] == search_scope
    assert memory_client.get_user_summary.await_args.args[0] == search_scope
    assert memory_client.upsert_memory.await_args.args[0] == storage_scope
    memory_client.process_now.assert_awaited_once_with(storage_scope)


async def test_message_filters_control_search_and_stored_turns() -> None:
    memory_client = _client()
    provider = PostgresMemoryContextProvider(
        memory_client=cast(Any, memory_client),
        user_id="user-1",
        search_input_message_filter=lambda messages: [message for message in messages if message.role == "user"],
        storage_input_request_message_filter=lambda messages: [
            message for message in messages if message.role == "system"
        ],
        storage_input_response_message_filter=lambda messages: [
            message for message in messages if message.role == "assistant"
        ],
    )
    session = AgentSession(session_id="thread-1")
    context = SessionContext(
        session_id="thread-1",
        input_messages=[
            Message(role="user", contents=["search this"]),
            Message(role="system", contents=["store this request"]),
        ],
    )
    context._response = AgentResponse(
        messages=[
            Message(role="assistant", contents=["store this response"]),
            Message(role="user", contents=["skip this response"]),
        ]
    )

    await provider.before_run(agent=_STUB_AGENT, session=session, context=context, state={})
    await provider.after_run(agent=_STUB_AGENT, session=session, context=context, state={})

    assert memory_client.search.await_args.args[1] == "search this"
    assert [call.args[1:] for call in memory_client.upsert_memory.await_args_list] == [
        ("system", "store this request"),
        ("assistant", "store this response"),
    ]


def test_provider_state_and_scope_resolver_configuration_are_validated() -> None:
    with pytest.raises(ValueError, match="thread_id"):
        PostgresMemoryContextProviderState(PostgresMemoryScope(user_id="user-1"))

    with pytest.raises(ValueError, match="scope_resolver cannot be combined"):
        PostgresMemoryContextProvider(
            memory_client=cast(Any, _client()),
            user_id="user-1",
            scope_resolver=lambda session, state: PostgresMemoryContextProviderState(
                PostgresMemoryScope(user_id="user-1", thread_id="thread-1")
            ),
        )

    provider = PostgresMemoryContextProvider(
        memory_client=cast(Any, _client()),
        scope_resolver=cast(Any, lambda session, state: "invalid"),
    )
    with pytest.raises(TypeError, match="must return"):
        provider._resolve_scopes(AgentSession(session_id="thread-1"), {})


async def test_provider_ownership_and_feature_usage() -> None:
    borrowed = _client()
    provider = PostgresMemoryContextProvider(memory_client=cast(Any, borrowed), user_id="user-1")
    empty_context = SessionContext(session_id="thread-1", input_messages=[])

    with patch("agent_framework_postgres._memory_context_provider.mark_feature_used") as mark_feature_used:
        await provider.before_run(
            agent=_STUB_AGENT,
            session=AgentSession(session_id="thread-1"),
            context=empty_context,
            state={},
        )
    mark_feature_used.assert_called_once_with(FeatureIndex.POSTGRES_MEMORY)

    await provider.close()
    borrowed.flush.assert_awaited_once_with(timeout=30.0)
    borrowed.close.assert_not_awaited()

    owned = _client()
    with patch(
        "agent_framework_postgres._memory_context_provider.PostgresMemoryClient",
        return_value=owned,
    ):
        constructed = PostgresMemoryContextProvider(
            embedding_generator=cast(Any, object()),
            chat_client=cast(Any, object()),
            connection_string="host=unused",
            user_id="user-1",
        )
    await constructed.close()
    owned.close.assert_awaited_once_with(timeout=30.0)


async def test_provider_context_entry_closes_constructed_client_after_schema_failure() -> None:
    owned = _client()
    owned.ensure_schema.side_effect = RuntimeError("schema failed")
    with patch(
        "agent_framework_postgres._memory_context_provider.PostgresMemoryClient",
        return_value=owned,
    ):
        provider = PostgresMemoryContextProvider(
            embedding_generator=cast(Any, object()),
            chat_client=cast(Any, object()),
            connection_string="host=unused",
            user_id="user-1",
        )

    with pytest.raises(RuntimeError, match="schema failed"):
        await provider.__aenter__()

    owned.close.assert_awaited_once()

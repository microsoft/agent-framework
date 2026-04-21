# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from agent_framework import (
    DEFAULT_MEMORY_SOURCE_ID,
    Agent,
    AgentSession,
    ChatResponse,
    Content,
    ExperimentalFeature,
    FileHistoryProvider,
    MemoryContextProvider,
    MemoryFileStore,
    MemoryIndexEntry,
    MemoryTopicRecord,
    Message,
)


def _tool_by_name(tools: list[object], name: str) -> object:
    """Return the tool with the requested name from a prepared tool list."""
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool
    raise AssertionError(f"Tool {name!r} was not found.")


class _MemoryHarnessClient:
    """Deterministic chat client used by the memory harness tests."""

    additional_properties: dict[str, Any]

    def __init__(
        self,
        *,
        extraction_payload: dict[str, Any] | None = None,
        consolidation_payload: dict[str, Any] | None = None,
        default_text: str = "Assistant reply.",
    ) -> None:
        self.additional_properties = {}
        self.extraction_payload = extraction_payload or {
            "memories": [
                {
                    "topic": "preferences",
                    "memory": "Prefers concise answers.",
                }
            ]
        }
        self.consolidation_payload = consolidation_payload or {
            "summary": "Prefers concise answers.",
            "memories": ["Prefers concise answers."],
        }
        self.default_text = default_text
        self.calls: list[str] = []

    async def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: Mapping[str, Any] | None = None,
        compaction_strategy: object | None = None,
        tokenizer: object | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ChatResponse[Any]:
        del options, compaction_strategy, tokenizer, function_invocation_kwargs, client_kwargs
        assert not stream
        system_text = messages[0].text if messages and messages[0].role == "system" else ""
        if "extract durable memory candidates" in system_text.lower():
            self.calls.append("extract")
            return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(self.extraction_payload)])])
        if "consolidate one topic memory file" in system_text.lower():
            self.calls.append("consolidate")
            return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(self.consolidation_payload)])])
        self.calls.append("agent")
        return ChatResponse(messages=[Message(role="assistant", contents=[self.default_text])])


def test_memory_index_entry_round_trips_and_trims_pointer_lines() -> None:
    """Memory index entries should preserve value equality and trim pointer lines."""
    raw_entry = {
        "topic": "Architecture Decisions",
        "slug": "architecture-decisions",
        "summary": (
            "PostgreSQL was chosen because it keeps the relational model while supporting flexible JSONB fields."
        ),
        "updated_at": "2026-04-21T10:00:00+00:00",
    }

    entry = MemoryIndexEntry.from_dict(raw_entry)

    assert entry == MemoryIndexEntry(**raw_entry)
    assert entry.to_dict() == raw_entry
    assert len(entry.to_pointer_line(max_length=80)) <= 80
    assert "MemoryIndexEntry(" in repr(entry)


def test_memory_topic_record_round_trips_through_dict_and_markdown() -> None:
    """Topic memory records should preserve their structured content and markdown form."""
    raw_record = {
        "topic": "preferences",
        "slug": "preferences",
        "summary": "Prefers concise answers.",
        "memories": ["Prefers concise answers.", "Prefers aisle seats."],
        "updated_at": "2026-04-21T10:05:00+00:00",
        "session_ids": ["session-1", "session-2"],
    }

    record = MemoryTopicRecord.from_dict(raw_record)
    reparsed_record = MemoryTopicRecord.from_markdown(record.to_markdown())

    assert record == MemoryTopicRecord(**raw_record)
    assert record.to_dict() == raw_record
    assert reparsed_record == record
    assert "MemoryTopicRecord(" in repr(record)


async def test_memory_file_store_writes_topics_index_state_and_transcripts(tmp_path) -> None:
    """The file-backed memory store should manage topics, ``MEMORY.md``, state, and transcript search."""
    store = MemoryFileStore(
        tmp_path,
        kind="memories",
        owner_prefix="user_",
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    updated_at = datetime(2026, 4, 21, tzinfo=UTC).replace(microsecond=0).isoformat()

    preferences_record = MemoryTopicRecord(
        topic="preferences",
        summary="Prefers concise answers.",
        memories=["Prefers concise answers.", "Prefers aisle seats."],
        updated_at=updated_at,
        session_ids=["session-1"],
    )
    travel_record = MemoryTopicRecord(
        topic="travel",
        summary="Planning a Norway trip.",
        memories=["Visit Oslo in June."],
        updated_at=updated_at,
        session_ids=["session-1"],
    )

    store.write_topic(session, preferences_record, source_id=DEFAULT_MEMORY_SOURCE_ID)
    store.write_topic(session, travel_record, source_id=DEFAULT_MEMORY_SOURCE_ID)
    entries = store.rebuild_index(
        session,
        source_id=DEFAULT_MEMORY_SOURCE_ID,
        line_limit=200,
        line_length=150,
    )

    assert [entry.topic for entry in entries] == ["preferences", "travel"]
    assert "preferences" in store.get_index_text(
        session,
        source_id=DEFAULT_MEMORY_SOURCE_ID,
        line_limit=200,
        line_length=150,
    )

    assert store.read_state(session, source_id=DEFAULT_MEMORY_SOURCE_ID) == {
        "last_consolidated_at": None,
        "sessions_since_consolidation": [],
    }
    store.write_state(
        session,
        {
            "last_consolidated_at": updated_at,
            "sessions_since_consolidation": ["session-1"],
        },
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )
    assert store.read_state(
        session,
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )["sessions_since_consolidation"] == ["session-1"]

    history_provider = FileHistoryProvider(
        store.get_transcripts_directory(session, source_id=DEFAULT_MEMORY_SOURCE_ID),
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    await history_provider.save_messages(
        session.session_id,
        [
            Message(role="user", contents=["I prefer aisle seats."]),
            Message(role="assistant", contents=["Recorded."]),
        ],
    )

    assert store.search_transcripts(session, source_id=DEFAULT_MEMORY_SOURCE_ID, query="aisle") == [
        {
            "session_id": "session-1",
            "line_number": 1,
            "role": "user",
            "text": "I prefer aisle seats.",
        }
    ]


async def test_memory_context_provider_tools_and_automation(tmp_path) -> None:
    """The memory provider should expose tools and automate extraction plus consolidation."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(
        tmp_path,
        kind="memories",
        owner_prefix="user_",
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    provider = MemoryContextProvider(
        store=store,
        consolidation_min_sessions=1,
        consolidation_interval=timedelta(0),
    )
    agent = Agent(
        client=_MemoryHarnessClient(),
        context_providers=[provider],
        default_options={"store": False},
    )

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Remember this."])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    write_memory = _tool_by_name(tools, "write_memory")
    list_memory_topics = _tool_by_name(tools, "list_memory_topics")
    search_memory_transcripts = _tool_by_name(tools, "search_memory_transcripts")
    consolidate_memories = _tool_by_name(tools, "consolidate_memories")

    write_result = await write_memory.invoke(arguments={"topic": "travel", "memory": "Visit Oslo in June."})
    created_topic = json.loads(write_result[0].text)
    assert created_topic["topic"] == "travel"

    list_result = await list_memory_topics.invoke()
    assert [entry["topic"] for entry in json.loads(list_result[0].text)] == ["travel"]

    await agent.run("Please remember that I prefer concise answers.", session=session)

    serialized_session = session.to_dict()
    assert serialized_session["state"][DEFAULT_MEMORY_SOURCE_ID] == {"owner_id": "alice"}

    preferences_topic = store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic="preferences")
    assert preferences_topic.summary == "Prefers concise answers."
    assert preferences_topic.memories == ["Prefers concise answers."]

    transcript_search_result = await search_memory_transcripts.invoke(arguments={"query": "concise", "limit": 5})
    search_payload = json.loads(transcript_search_result[0].text)
    assert search_payload[0]["role"] == "user"
    assert "concise answers" in search_payload[0]["text"]

    consolidate_result = await consolidate_memories.invoke()
    assert json.loads(consolidate_result[0].text)["consolidated_topics"] >= 1


async def test_memory_context_provider_injects_recent_turns(tmp_path) -> None:
    """The memory provider should inject only the configured recent transcript turns."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(
        tmp_path,
        kind="memories",
        owner_prefix="user_",
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    provider = MemoryContextProvider(store=store, recent_turns=2)
    provider_state = store.export_provider_state(session)
    await provider.save_messages(
        session.session_id,
        [
            Message(role="user", contents=["First question"]),
            Message(role="assistant", contents=["First answer"]),
            Message(role="user", contents=["Second question"]),
            Message(role="assistant", contents=["Second answer"]),
            Message(role="user", contents=["Third question"]),
            Message(role="assistant", contents=["Third answer"]),
        ],
        state=provider_state,
    )
    agent = Agent(
        client=_MemoryHarnessClient(),
        context_providers=[provider],
        default_options={"store": False},
    )

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Current question"])],
    )
    prepared_messages = session_context.get_messages(include_input=True)

    assert [message.text for message in prepared_messages[:4]] == [
        "Second question",
        "Second answer",
        "Third question",
        "Third answer",
    ]
    assert "First question" not in [message.text for message in prepared_messages]
    assert "### MEMORY.md" in prepared_messages[4].text
    assert prepared_messages[-1].text == "Current question"


async def test_memory_context_provider_recent_turns_can_skip_tool_call_groups(tmp_path) -> None:
    """Recent-turn loading should follow compaction grouping and optionally skip tool-call groups."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(
        tmp_path,
        kind="memories",
        owner_prefix="user_",
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    provider_state = store.export_provider_state(session)
    await MemoryContextProvider(store=store).save_messages(
        session.session_id,
        [
            Message(role="user", contents=["First question"]),
            Message(role="assistant", contents=["First answer"]),
            Message(role="user", contents=["Second question"]),
            Message(role="assistant", contents=[Content.from_text_reasoning(text="Let me check that.")]),
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call-1", name="lookup_answer", arguments='{"topic":"second"}')
                ],
            ),
            Message(role="tool", contents=[Content.from_function_result(call_id="call-1", result="Tool result")]),
            Message(role="assistant", contents=["Second final answer"]),
            Message(role="user", contents=["Third question"]),
            Message(role="assistant", contents=["Third answer"]),
        ],
        state=provider_state,
    )
    with_tools_agent = Agent(
        client=_MemoryHarnessClient(),
        context_providers=[MemoryContextProvider(store=store, recent_turns=2, load_tool_turns=True)],
        default_options={"store": False},
    )
    without_tools_agent = Agent(
        client=_MemoryHarnessClient(),
        context_providers=[MemoryContextProvider(store=store, recent_turns=2, load_tool_turns=False)],
        default_options={"store": False},
    )

    with_tools_context, _ = await with_tools_agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Current question"])],
    )
    without_tools_context, _ = await without_tools_agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Current question"])],
    )
    with_tools_messages = with_tools_context.get_messages(include_input=True)
    without_tools_messages = without_tools_context.get_messages(include_input=True)

    assert [message.text for message in without_tools_messages[:4]] == [
        "Second question",
        "Second final answer",
        "Third question",
        "Third answer",
    ]
    assert not any(message.role == "tool" for message in without_tools_messages)
    assert not any(
        any(content.type == "function_call" for content in message.contents) for message in without_tools_messages
    )
    assert not any(
        any(content.type == "text_reasoning" for content in message.contents) for message in without_tools_messages
    )

    assert with_tools_messages[0].text == "Second question"
    assert with_tools_messages[1].contents[0].type == "text_reasoning"
    assert with_tools_messages[2].contents[0].type == "function_call"
    assert with_tools_messages[3].role == "tool"
    assert with_tools_messages[3].contents[0].type == "function_result"
    assert with_tools_messages[4].text == "Second final answer"


async def test_memory_context_provider_uses_explicit_consolidation_client(tmp_path) -> None:
    """The memory provider should use the explicit consolidation client when one is configured."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(
        tmp_path,
        kind="memories",
        owner_prefix="user_",
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    main_client = _MemoryHarnessClient()
    consolidation_client = _MemoryHarnessClient(
        consolidation_payload={
            "summary": "Consolidated by the cheaper client.",
            "memories": ["Visit Oslo in June."],
        }
    )
    provider = MemoryContextProvider(
        store=store,
        consolidation_client=consolidation_client,
    )
    agent = Agent(
        client=main_client,
        context_providers=[provider],
        default_options={"store": False},
    )

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Remember this."])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    write_memory = _tool_by_name(tools, "write_memory")
    consolidate_memories = _tool_by_name(tools, "consolidate_memories")

    await write_memory.invoke(arguments={"topic": "travel", "memory": "Visit Oslo in June."})
    await consolidate_memories.invoke()

    travel_topic = store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic="travel")
    assert travel_topic.summary == "Consolidated by the cheaper client."
    assert main_client.calls == []
    assert consolidation_client.calls == ["consolidate"]


def test_memory_harness_classes_are_marked_experimental() -> None:
    """Memory harness public classes should expose HARNESS experimental metadata."""
    assert MemoryIndexEntry.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert MemoryTopicRecord.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert MemoryFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert MemoryContextProvider.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert ".. warning:: Experimental" in MemoryContextProvider.__doc__

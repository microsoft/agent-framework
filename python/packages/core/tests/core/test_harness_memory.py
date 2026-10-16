# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from agent_framework import (
    DEFAULT_MEMORY_SOURCE_ID,
    Agent,
    AgentSession,
    ChatOptions,
    ChatResponse,
    Content,
    ExperimentalFeature,
    FileHistoryProvider,
    MemoryContextProvider,
    MemoryFileStore,
    MemoryIndexEntry,
    MemoryStore,
    MemoryTopicRecord,
    Message,
)
from agent_framework import _filesystem as filesystem_module

from .test_filesystem import COLLIDING_IDENTIFIERS


def _no_store_options() -> ChatOptions:
    return {"store": False}


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

    assert record == MemoryTopicRecord(**raw_record)  # type: ignore[arg-type]
    assert record.to_dict() == raw_record
    assert reparsed_record == record
    assert "MemoryTopicRecord(" in repr(record)


@pytest.mark.parametrize(
    "summary",
    [
        "Updated: the release date changed.",
        "Sessions: keep the troubleshooting context.",
        "The plan was Updated: yesterday and Sessions: remain useful.",
        "Prefers concise answers.",
        "## Summary is part of the stored text.",
    ],
)
def test_memory_file_store_preserves_metadata_like_summary_text(tmp_path: Path, summary: str) -> None:
    """Summary text must not replace metadata when a topic is reloaded from disk."""
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    record = MemoryTopicRecord(
        topic="preferences",
        summary=summary,
        memories=["Updated: the milestone moved.", "Sessions: retain previous notes."],
        updated_at="2026-04-21T10:05:00+00:00",
        session_ids=["session-1", "session-2"],
    )

    assert MemoryTopicRecord.from_markdown(record.to_markdown()) == record
    store.write_topic(session, record, source_id=DEFAULT_MEMORY_SOURCE_ID)

    assert store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic=record.slug) == record
    assert store.list_topics(session, source_id=DEFAULT_MEMORY_SOURCE_ID) == [record]
    entries = store.rebuild_index(session, source_id=DEFAULT_MEMORY_SOURCE_ID, line_limit=200, line_length=150)
    assert entries == [MemoryIndexEntry.from_topic_record(record)]


@pytest.mark.parametrize("summary_line", ["Updated: the release date changed.", "Sessions: keep previous notes."])
def test_memory_topic_record_preserves_multiline_summary_metadata_text(summary_line: str) -> None:
    """Metadata labels inside a multiline summary remain content in that section."""
    markdown = (
        "# preferences\n\n"
        "Updated: 2026-04-21T10:05:00+00:00\n"
        "Sessions: session-1, session-2\n\n"
        "## Summary\n\n"
        f"Keep the release notes.\n{summary_line}\n\n"
        "## Memories\n\n"
        "- Updated: the milestone moved.\n"
        "- Sessions: retain previous notes.\n"
    )

    record = MemoryTopicRecord.from_markdown(markdown)

    assert record.summary == f"Keep the release notes. {summary_line}"
    assert record.updated_at == "2026-04-21T10:05:00+00:00"
    assert record.session_ids == ["session-1", "session-2"]
    assert record.memories == ["Updated: the milestone moved.", "Sessions: retain previous notes."]


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
    updated_at = datetime(2026, 4, 21, tzinfo=timezone.utc).replace(microsecond=0).isoformat()

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
        "pending_turn_ids": {},
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

    history_provider = FileHistoryProvider(store.get_transcripts_directory(session, source_id=DEFAULT_MEMORY_SOURCE_ID))
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


async def _write_transcript(store: MemoryFileStore, session: AgentSession, session_id: str, text: str) -> None:
    """Append a one-message transcript for ``session_id`` through the real write path."""
    provider = FileHistoryProvider(store.get_transcripts_directory(session, source_id=DEFAULT_MEMORY_SOURCE_ID))
    await provider.save_messages(session_id, [Message(role="user", contents=[text])])


async def test_search_transcripts_finds_session_stored_under_digest_stem(tmp_path) -> None:
    """A session ID too long to encode is stored under an irreversible digest stem but stays findable."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "user-1"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    long_session_id = "a/" + "a" * 108

    await _write_transcript(store, session, "short-id", "Short session transcript.")
    await _write_transcript(store, session, long_session_id, "Long session transcript.")

    # The long ID must genuinely land on a digest stem, otherwise this test proves nothing.
    stem = store._transcript_file_stem(long_session_id)
    assert "sha256-" in stem
    assert store._decode_transcript_session_id(Path(f"{stem}.jsonl")) is None

    results = store.search_transcripts(
        session, source_id=DEFAULT_MEMORY_SOURCE_ID, query="transcript", session_id=long_session_id
    )
    assert [(result["session_id"], result["text"]) for result in results] == [
        (long_session_id, "Long session transcript.")
    ]

    results = store.search_transcripts(
        session, source_id=DEFAULT_MEMORY_SOURCE_ID, query="transcript", session_id="short-id"
    )
    assert [(result["session_id"], result["text"]) for result in results] == [("short-id", "Short session transcript.")]

    unfiltered = store.search_transcripts(session, source_id=DEFAULT_MEMORY_SOURCE_ID, query="transcript")
    assert {result["text"] for result in unfiltered} == {"Short session transcript.", "Long session transcript."}


async def test_search_transcripts_isolates_colliding_session_ids(tmp_path) -> None:
    """Session IDs that normalize alike must each retrieve only their own transcript."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "user-1"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")

    for index, candidate in enumerate(COLLIDING_IDENTIFIERS):
        await _write_transcript(store, session, candidate, f"Transcript {index}.")

    for index, candidate in enumerate(COLLIDING_IDENTIFIERS):
        results = store.search_transcripts(
            session, source_id=DEFAULT_MEMORY_SOURCE_ID, query="Transcript", session_id=candidate
        )
        assert [result["text"] for result in results] == [f"Transcript {index}."]
        assert all(result["session_id"] == candidate for result in results)


async def test_search_transcripts_returns_nothing_for_unknown_session(tmp_path) -> None:
    """Filtering by a session that never wrote a transcript should return no results."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "user-1"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    await _write_transcript(store, session, "known-id", "Known transcript.")

    assert (
        store.search_transcripts(
            session, source_id=DEFAULT_MEMORY_SOURCE_ID, query="transcript", session_id="unknown-id"
        )
        == []
    )


def test_memory_file_store_rejects_owner_path_traversal(tmp_path) -> None:
    """Owner IDs with path traversal segments should not escape ``base_path``."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "../escape"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    record = MemoryTopicRecord(
        topic="preferences",
        summary="Prefers concise answers.",
        memories=["Prefers concise answers."],
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc).replace(microsecond=0).isoformat(),
    )

    with pytest.raises(ValueError, match="path traversal"):
        store.write_topic(session, record, source_id=DEFAULT_MEMORY_SOURCE_ID)

    assert not (tmp_path.parent / "escape").exists()


async def test_memory_file_store_namespaces_topics_state_and_transcripts_by_source_id(tmp_path) -> None:
    """Providers sharing one file store should not collide when they use different source IDs."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(
        tmp_path,
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    updated_at = datetime(2026, 4, 21, tzinfo=timezone.utc).replace(microsecond=0).isoformat()

    store.write_topic(
        session,
        MemoryTopicRecord(
            topic="preferences",
            summary="Source A summary.",
            memories=["Source A memory."],
            updated_at=updated_at,
        ),
        source_id="source-a",
    )
    store.write_topic(
        session,
        MemoryTopicRecord(
            topic="preferences",
            summary="Source B summary.",
            memories=["Source B memory."],
            updated_at=updated_at,
        ),
        source_id="source-b",
    )
    store.write_state(
        session, {"last_consolidated_at": updated_at, "sessions_since_consolidation": ["a"]}, source_id="source-a"
    )
    store.write_state(
        session, {"last_consolidated_at": None, "sessions_since_consolidation": ["b"]}, source_id="source-b"
    )

    await FileHistoryProvider(store.get_transcripts_directory(session, source_id="source-a")).save_messages(
        "session-1", [Message(role="user", contents=["Source A transcript."])]
    )
    await FileHistoryProvider(store.get_transcripts_directory(session, source_id="source-b")).save_messages(
        "session-1", [Message(role="user", contents=["Source B transcript."])]
    )

    assert store.get_topic(session, source_id="source-a", topic="preferences").memories == ["Source A memory."]
    assert store.get_topic(session, source_id="source-b", topic="preferences").memories == ["Source B memory."]
    assert store.read_state(session, source_id="source-a")["sessions_since_consolidation"] == ["a"]
    assert store.read_state(session, source_id="source-b")["sessions_since_consolidation"] == ["b"]
    assert (
        store.search_transcripts(session, source_id="source-a", query="transcript")[0]["text"] == "Source A transcript."
    )
    assert (
        store.search_transcripts(session, source_id="source-b", query="transcript")[0]["text"] == "Source B transcript."
    )


async def test_memory_context_provider_does_not_rewrite_unchanged_index(tmp_path) -> None:
    """A second before-run pass with unchanged memories should preserve ``MEMORY.md`` mtime."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    agent = Agent(
        client=_MemoryHarnessClient(),  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[MemoryContextProvider(store=store)],
        default_options=_no_store_options(),
    )

    await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Current question"])],
    )
    index_path = next(tmp_path.rglob("MEMORY.md"))
    first_mtime_ns = index_path.stat().st_mtime_ns

    await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Current question"])],
    )

    assert index_path.stat().st_mtime_ns == first_mtime_ns


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
        client=_MemoryHarnessClient(),  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[provider],
        default_options=_no_store_options(),
    )

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Remember this."])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    write_memory = _tool_by_name(tools, "write_memory")
    list_memory_topics = _tool_by_name(tools, "list_memory_topics")
    search_memory_transcripts = _tool_by_name(tools, "search_memory_transcripts")
    consolidate_memories = _tool_by_name(tools, "consolidate_memories")

    write_result = await write_memory.invoke(arguments={"topic": "travel", "memory": "Visit Oslo in June."})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    created_topic = json.loads(write_result[0].text)
    assert created_topic["topic"] == "travel"

    list_result = await list_memory_topics.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert [entry["topic"] for entry in json.loads(list_result[0].text)] == ["travel"]

    await agent.run("Please remember that I prefer concise answers.", session=session)

    serialized_session = session.to_dict()
    assert serialized_session["state"][DEFAULT_MEMORY_SOURCE_ID] == {"owner_id": "alice"}

    preferences_topic = store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic="preferences")
    assert preferences_topic.summary == "Prefers concise answers."
    assert preferences_topic.memories == ["Prefers concise answers."]

    transcript_search_result = await search_memory_transcripts.invoke(arguments={"query": "concise", "limit": 5})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    search_payload = json.loads(transcript_search_result[0].text)
    assert search_payload[0]["role"] == "user"
    assert "concise answers" in search_payload[0]["text"]

    consolidate_result = await consolidate_memories.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
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
        client=_MemoryHarnessClient(),  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[provider],
        default_options=_no_store_options(),
    )

    session_context, _ = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
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
        client=_MemoryHarnessClient(),  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[MemoryContextProvider(store=store, recent_turns=2, load_tool_turns=True)],
        default_options=_no_store_options(),
    )
    without_tools_agent = Agent(
        client=_MemoryHarnessClient(),  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[MemoryContextProvider(store=store, recent_turns=2, load_tool_turns=False)],
        default_options=_no_store_options(),
    )

    with_tools_context, _ = await with_tools_agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Current question"])],
    )
    without_tools_context, _ = await without_tools_agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
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


async def test_memory_context_provider_marks_cross_session_origins(tmp_path) -> None:
    """Injected memory should carry all prior session origins without duplicates.

    Exercises the cross-session attribution surface added to support downstream observers
    detecting attacks of the class documented in Dai et al. (arXiv:2605.06158).
    """
    session = AgentSession(session_id="session-current")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(
        tmp_path,
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    updated_at = datetime(2026, 4, 21, tzinfo=timezone.utc).replace(microsecond=0).isoformat()
    store.write_topic(
        session,
        MemoryTopicRecord(
            topic="travel preferences",
            summary="Loves Oslo trips.",
            memories=["Prefers Oslo in summer."],
            updated_at=updated_at,
            session_ids=["session-current", "session-prior-1", "session-prior-2", "session-prior-1"],
        ),
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )

    agent = Agent(
        client=_MemoryHarnessClient(),  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[MemoryContextProvider(store=store)],
        default_options=_no_store_options(),
    )

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Tell me about my travel preferences."])],
    )

    memory_messages = [
        m for m in session_context.context_messages.get(DEFAULT_MEMORY_SOURCE_ID, []) if "### MEMORY.md" in m.text
    ]
    assert memory_messages, "expected an injected memory block under the memory source"
    attribution: dict[str, Any] = memory_messages[0].additional_properties.get("_attribution") or {}
    assert attribution.get("origin_session_ids") == ["session-prior-1", "session-prior-2"]


async def test_memory_context_provider_omits_origin_when_only_current_session(tmp_path) -> None:
    """When all contributing topics are from the current session, attribution must NOT advertise an origin."""
    session = AgentSession(session_id="session-current")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(
        tmp_path,
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    updated_at = datetime(2026, 4, 21, tzinfo=timezone.utc).replace(microsecond=0).isoformat()
    store.write_topic(
        session,
        MemoryTopicRecord(
            topic="travel preferences",
            summary="Loves Oslo trips.",
            memories=["Prefers Oslo in summer."],
            updated_at=updated_at,
            session_ids=["session-current"],
        ),
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )

    agent = Agent(
        client=_MemoryHarnessClient(),  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[MemoryContextProvider(store=store)],
        default_options=_no_store_options(),
    )

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Tell me about my travel preferences."])],
    )

    memory_messages = [
        m for m in session_context.context_messages.get(DEFAULT_MEMORY_SOURCE_ID, []) if "### MEMORY.md" in m.text
    ]
    assert memory_messages
    attribution: dict[str, Any] = memory_messages[0].additional_properties.get("_attribution") or {}
    assert "origin_session_ids" not in attribution


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
        consolidation_client=consolidation_client,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    )
    agent = Agent(
        client=main_client,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        context_providers=[provider],
        default_options=_no_store_options(),
    )

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Remember this."])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    write_memory = _tool_by_name(tools, "write_memory")
    consolidate_memories = _tool_by_name(tools, "consolidate_memories")

    await write_memory.invoke(arguments={"topic": "travel", "memory": "Visit Oslo in June."})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    await consolidate_memories.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    travel_topic = store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic="travel")
    assert travel_topic.summary == "Consolidated by the cheaper client."
    assert main_client.calls == []
    assert consolidation_client.calls == ["consolidate"]


async def test_memory_context_provider_preserves_concurrent_writes_to_same_topic(tmp_path) -> None:
    """Concurrent writes to one topic should preserve every memory line."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    provider = MemoryContextProvider(store=store)
    agent = Agent(client=_MemoryHarnessClient(), context_providers=[provider], default_options=_no_store_options())  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Remember these."])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)
    write_memory = _tool_by_name(tools, "write_memory")
    memories = [f"Concurrent memory {index}." for index in range(20)]

    await asyncio.gather(
        *(write_memory.invoke(arguments={"topic": "preferences", "memory": memory}) for memory in memories)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    )

    topic = store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic="preferences")
    assert sorted(topic.memories) == sorted(memories)


class _GatedMemoryClient:
    """Chat client that can hold extraction for one marked turn, and consolidation, until released."""

    additional_properties: dict[str, Any]

    def __init__(self, *, extraction_marker: str) -> None:
        self.additional_properties = {}
        self.extraction_marker = extraction_marker
        self.extraction_started = asyncio.Event()
        self.release_extraction = asyncio.Event()
        self.consolidation_started = asyncio.Event()
        self.release_consolidation = asyncio.Event()
        self.release_consolidation.set()
        self.consolidated_topics: list[str] = []

    async def get_response(self, messages: Sequence[Message], **kwargs: object) -> ChatResponse[Any]:
        del kwargs
        system_text = messages[0].text.lower() if messages and messages[0].role == "system" else ""
        if "extract durable memory candidates" in system_text:
            memories: list[dict[str, str]] = []
            if self.extraction_marker in messages[1].text:
                self.extraction_started.set()
                await self.release_extraction.wait()
                memories = [{"topic": "New", "memory": f"{self.extraction_marker} fact"}]
            return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps({"memories": memories})])])
        if "consolidate one topic memory file" in system_text:
            self.consolidated_topics.append(messages[1].text)
            self.consolidation_started.set()
            await self.release_consolidation.wait()
            payload = {"summary": "Old summary.", "memories": ["Old fact"]}
            return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(payload)])])
        return ChatResponse(messages=[Message(role="assistant", contents=["Assistant reply."])])


def _gated_consolidation_setup(tmp_path: Path, client: _GatedMemoryClient) -> tuple[MemoryFileStore, Agent]:
    """Seed an Old topic and one pending session so the next finished session triggers consolidation."""
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    provider = MemoryContextProvider(store=store, consolidation_min_sessions=2, consolidation_interval=timedelta(0))
    seed_session = _owned_session("session-a")
    store.write_topic(
        seed_session,
        MemoryTopicRecord(
            topic="Old",
            summary="Old summary.",
            memories=["Old fact"],
            updated_at="2026-10-01T00:00:00+00:00",
            session_ids=["session-a"],
        ),
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )
    store.write_state(
        seed_session,
        {"last_consolidated_at": None, "sessions_since_consolidation": ["session-a"]},
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )
    agent = Agent(client=client, context_providers=[provider], default_options=_no_store_options())  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    return store, agent


def _owned_session(session_id: str) -> AgentSession:
    session = AgentSession(session_id=session_id)
    session.state["owner_id"] = "alice"
    return session


def _pending_sessions(store: MemoryFileStore) -> list[str]:
    pending: list[str] = store.read_state(_owned_session("reader"), source_id=DEFAULT_MEMORY_SOURCE_ID)[
        "sessions_since_consolidation"
    ]
    return pending


async def _run_turn(agent: Agent, text: str, session_id: str) -> None:
    await agent.run(text, session=_owned_session(session_id))


async def test_automatic_consolidation_keeps_session_extracting_during_pass(tmp_path: Path) -> None:
    """A session still extracting when a consolidation pass finishes stays pending for the next pass."""
    client = _GatedMemoryClient(extraction_marker="B turn")
    store, agent = _gated_consolidation_setup(tmp_path, client)
    client.release_consolidation.clear()

    consolidating_run = asyncio.create_task(_run_turn(agent, "Second turn.", "session-2"))
    await client.consolidation_started.wait()
    extracting_run = asyncio.create_task(_run_turn(agent, "B turn.", "session-b"))
    await client.extraction_started.wait()

    client.release_consolidation.set()
    await consolidating_run
    client.release_extraction.set()
    await extracting_run

    assert _pending_sessions(store) == ["session-b"]

    await agent.run("Third turn.", session=_owned_session("session-c"))
    assert _pending_sessions(store) == []
    assert len(client.consolidated_topics) == 3
    assert any("B turn fact" in topic for topic in client.consolidated_topics[1:])


async def test_automatic_consolidation_keeps_session_extracting_before_snapshot(tmp_path: Path) -> None:
    """A session that starts extracting before a pass snapshots the topics stays pending for the next pass."""
    client = _GatedMemoryClient(extraction_marker="B turn")
    store, agent = _gated_consolidation_setup(tmp_path, client)

    extracting_run = asyncio.create_task(_run_turn(agent, "B turn.", "session-b"))
    await client.extraction_started.wait()

    await agent.run("Second turn.", session=_owned_session("session-2"))
    assert len(client.consolidated_topics) == 1
    assert _pending_sessions(store) == []

    client.release_extraction.set()
    await extracting_run

    assert _pending_sessions(store) == ["session-b"]
    new_topic = store.get_topic(_owned_session("reader"), source_id=DEFAULT_MEMORY_SOURCE_ID, topic="New")
    assert new_topic.memories == ["B turn fact"]

    await agent.run("Third turn.", session=_owned_session("session-c"))
    assert _pending_sessions(store) == []
    assert any("B turn fact" in topic for topic in client.consolidated_topics[1:])


class _OrderedConsolidationClient:
    """Chat client that holds each consolidation call until the test releases it."""

    additional_properties: dict[str, Any]

    def __init__(self, *, extraction_marker: str) -> None:
        self.additional_properties = {}
        self.extraction_marker = extraction_marker
        self.consolidated_topics: list[str] = []
        self.consolidation_gates: list[asyncio.Event] = []
        self.consolidation_call_started = asyncio.Event()

    async def wait_for_consolidation_calls(self, count: int) -> None:
        while len(self.consolidation_gates) < count:
            self.consolidation_call_started.clear()
            await self.consolidation_call_started.wait()

    async def get_response(self, messages: Sequence[Message], **kwargs: object) -> ChatResponse[Any]:
        del kwargs
        system_text = messages[0].text.lower() if messages and messages[0].role == "system" else ""
        if "extract durable memory candidates" in system_text:
            memories: list[dict[str, str]] = []
            if self.extraction_marker in messages[1].text:
                memories = [{"topic": "New", "memory": f"{self.extraction_marker} fact"}]
            return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps({"memories": memories})])])
        if "consolidate one topic memory file" in system_text:
            self.consolidated_topics.append(messages[1].text)
            gate = asyncio.Event()
            self.consolidation_gates.append(gate)
            self.consolidation_call_started.set()
            await gate.wait()
            topic = "New" if self.extraction_marker in messages[1].text else "Old"
            payload = {"summary": f"{topic} summary.", "memories": [f"{topic} fact"]}
            return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(payload)])])
        return ChatResponse(messages=[Message(role="assistant", contents=["Assistant reply."])])


async def test_automatic_consolidation_keeps_overlapping_turn_of_covered_session_pending(tmp_path: Path) -> None:
    """A later turn of a session that a running pass already covers stays pending after that pass.

    ``Agent.run`` does not serialize runs per session, so a second ``session-1`` turn can write a new
    topic and register itself while a pass that snapshotted ``session-1`` as pending is still running.
    """
    client = _OrderedConsolidationClient(extraction_marker="Later turn")
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    provider = MemoryContextProvider(store=store, consolidation_min_sessions=2, consolidation_interval=timedelta(0))
    seed_session = _owned_session("session-a")
    store.write_topic(
        seed_session,
        MemoryTopicRecord(
            topic="Old",
            summary="Old summary.",
            memories=["Old fact"],
            updated_at="2026-10-01T00:00:00+00:00",
            session_ids=["session-a"],
        ),
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )
    store.write_state(
        seed_session,
        {"last_consolidated_at": None, "sessions_since_consolidation": ["session-a"]},
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )
    agent = Agent(client=client, context_providers=[provider], default_options=_no_store_options())  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

    # The first turn registers session-1 and starts a pass whose snapshot covers it and the Old topic.
    first_run = asyncio.create_task(_run_turn(agent, "First turn.", "session-1"))
    await client.wait_for_consolidation_calls(1)

    # The overlapping second turn writes the New topic, registers session-1 again and starts its own
    # pass, which holds on the New topic.
    second_run = asyncio.create_task(_run_turn(agent, "Later turn.", "session-1"))
    await client.wait_for_consolidation_calls(2)
    assert "Later turn fact" in client.consolidated_topics[1]
    assert _pending_sessions(store) == ["session-a", "session-1"]

    # The first pass finishes: its snapshot did not include the second turn, so session-1 stays pending.
    client.consolidation_gates[0].set()
    await first_run
    assert _pending_sessions(store) == ["session-1"]

    # The second pass covered the second turn and retires it.
    client.consolidation_gates[1].set()
    await client.wait_for_consolidation_calls(3)
    client.consolidation_gates[2].set()
    await second_run
    assert _pending_sessions(store) == []


class _RegisteringConsolidationClient:
    """Consolidation client that registers another finished turn while the pass is running."""

    additional_properties: dict[str, Any]

    def __init__(self, store: MemoryFileStore, session: AgentSession, session_id: str) -> None:
        self.additional_properties = {}
        self.store = store
        self.session = session
        self.session_id = session_id

    async def get_response(self, *args: object, **kwargs: object) -> ChatResponse[Any]:
        del args, kwargs
        state = self.store.read_state(self.session, source_id=DEFAULT_MEMORY_SOURCE_ID)
        if self.session_id not in state["sessions_since_consolidation"]:
            state["sessions_since_consolidation"].append(self.session_id)
        state["pending_turn_ids"][self.session_id] = "later-turn"
        self.store.write_state(self.session, state, source_id=DEFAULT_MEMORY_SOURCE_ID)
        payload = {"summary": "Old summary.", "memories": ["Old fact"]}
        return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(payload)])])


@pytest.mark.parametrize(
    "later_session_id",
    [
        pytest.param("session-b", id="new_session"),
        pytest.param("session-a", id="pending_session_without_turn_id"),
        pytest.param("session-2", id="pending_session_with_turn_id"),
    ],
)
async def test_memory_consolidation_retires_only_turns_in_its_snapshot(tmp_path: Path, later_session_id: str) -> None:
    """Completing a pass clears the turns it covered and keeps turns registered after its snapshot.

    ``session-a`` is pending without a turn id, like state written before turn ids were recorded.
    """
    session = _owned_session("session-2")
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    client = _RegisteringConsolidationClient(store, session, later_session_id)
    provider = MemoryContextProvider(store=store, consolidation_min_sessions=2, consolidation_interval=timedelta(0))
    store.write_state(
        session,
        {
            "last_consolidated_at": None,
            "sessions_since_consolidation": ["session-a", "session-2"],
            "pending_turn_ids": {"session-2": "earlier-turn"},
        },
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )
    store.write_topic(
        session,
        MemoryTopicRecord(
            topic="Old",
            summary="Old summary.",
            memories=["Old fact"],
            updated_at="2026-10-01T00:00:00+00:00",
            session_ids=["session-a"],
        ),
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )

    consolidated_count = await provider._run_consolidation(  # pyright: ignore[reportPrivateUsage]
        client=client,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        session=session,
        force=False,
        now=datetime(2026, 10, 8, tzinfo=timezone.utc),
    )

    assert consolidated_count == 1
    assert store.read_state(session, source_id=DEFAULT_MEMORY_SOURCE_ID) == {
        "last_consolidated_at": "2026-10-08T00:00:00+00:00",
        "sessions_since_consolidation": [later_session_id],
        "pending_turn_ids": {later_session_id: "later-turn"},
    }


class _TwoTopicExtractionClient:
    """Chat client whose extraction returns two memories in different topics."""

    additional_properties: dict[str, Any]

    def __init__(self) -> None:
        self.additional_properties = {}

    async def get_response(self, messages: Sequence[Message], **kwargs: object) -> ChatResponse[Any]:
        del kwargs
        system_text = messages[0].text.lower() if messages and messages[0].role == "system" else ""
        if "extract durable memory candidates" in system_text:
            memories = [{"topic": "First", "memory": "First fact"}, {"topic": "Second", "memory": "Second fact"}]
            return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps({"memories": memories})])])
        return ChatResponse(messages=[Message(role="assistant", contents=["Assistant reply."])])


def _two_topic_setup(tmp_path: Path) -> tuple[MemoryFileStore, MemoryContextProvider, Agent]:
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    provider = MemoryContextProvider(store=store, consolidation_min_sessions=10)
    agent = Agent(client=_TwoTopicExtractionClient(), context_providers=[provider], default_options=_no_store_options())  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    return store, provider, agent


@pytest.mark.parametrize("failing_step", ["second_topic_write", "rebuild_index"])
async def test_memory_session_stays_pending_when_extraction_fails_after_a_topic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_step: str
) -> None:
    """A run that persisted a topic and then failed still registers its session for consolidation."""
    store, _, agent = _two_topic_setup(tmp_path)
    if failing_step == "second_topic_write":
        original_write_topic = store.write_topic
        written_topics: list[str] = []

        def write_topic(session: AgentSession, record: MemoryTopicRecord, **kwargs: Any) -> None:
            if written_topics:
                raise OSError("disk full")
            written_topics.append(record.topic)
            original_write_topic(session, record, **kwargs)

        monkeypatch.setattr(store, "write_topic", write_topic)
    else:
        original_rebuild_index = store.rebuild_index

        def rebuild_index(session: AgentSession, **kwargs: Any) -> list[MemoryIndexEntry]:
            # ``before_run`` also rebuilds the index; fail only the rebuild after extraction wrote topics.
            if store.list_topics(session, source_id=DEFAULT_MEMORY_SOURCE_ID):
                raise OSError("disk full")
            return original_rebuild_index(session, **kwargs)

        monkeypatch.setattr(store, "rebuild_index", rebuild_index)

    with pytest.raises(OSError, match="disk full"):
        await _run_turn(agent, "Remember this.", "session-1")

    first_topic = store.get_topic(_owned_session("reader"), source_id=DEFAULT_MEMORY_SOURCE_ID, topic="First")
    assert first_topic.memories == ["First fact"]
    assert _pending_sessions(store) == ["session-1"]


async def test_memory_session_stays_pending_when_extraction_is_cancelled_after_a_topic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run cancelled after persisting a topic still registers its session for consolidation."""
    store, provider, agent = _two_topic_setup(tmp_path)
    original_merge_memory = provider._merge_memory  # pyright: ignore[reportPrivateUsage]
    second_merge_started = asyncio.Event()

    async def merge_memory(**kwargs: Any) -> MemoryTopicRecord:
        if kwargs["topic"] == "Second":
            second_merge_started.set()
            await asyncio.Event().wait()
        return await original_merge_memory(**kwargs)

    monkeypatch.setattr(provider, "_merge_memory", merge_memory)

    run = asyncio.create_task(_run_turn(agent, "Remember this.", "session-1"))
    await second_merge_started.wait()
    assert _pending_sessions(store) == []
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run

    first_topic = store.get_topic(_owned_session("reader"), source_id=DEFAULT_MEMORY_SOURCE_ID, topic="First")
    assert first_topic.memories == ["First fact"]
    assert _pending_sessions(store) == ["session-1"]


def test_memory_harness_classes_are_marked_experimental() -> None:
    """Memory harness public classes should expose HARNESS experimental metadata."""
    assert MemoryIndexEntry.__feature_id__ == ExperimentalFeature.HARNESS.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert MemoryTopicRecord.__feature_id__ == ExperimentalFeature.HARNESS.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert MemoryStore.__feature_id__ == ExperimentalFeature.HARNESS.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert MemoryFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert MemoryContextProvider.__feature_id__ == ExperimentalFeature.HARNESS.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert ".. warning:: Experimental" in MemoryContextProvider.__doc__  # type: ignore[operator]  # pyrefly: ignore[not-iterable]  # ty: ignore[unsupported-operator]


def test_memory_topic_record_round_trips_when_text_contains_section_markers() -> None:
    """Embedded ``## Summary``/``## Memories`` markers must not be re-interpreted as headings."""
    record = MemoryTopicRecord(
        topic="weird",
        summary="Multi line summary.\n## Summary\nstill summary",
        memories=[
            "## Memories pretend",
            "Real memory.",
            "  ## Memories nested",
        ],
        updated_at="2026-04-21T10:00:00+00:00",
        session_ids=["session-1"],
    )

    reparsed = MemoryTopicRecord.from_markdown(record.to_markdown())

    assert reparsed.summary == record.summary
    assert reparsed.memories == record.memories


async def test_memory_file_store_atomic_write_preserves_prior_topic_on_failure(tmp_path, monkeypatch) -> None:
    """If ``os.replace`` fails mid-write, the previous topic file must remain intact."""
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    original = MemoryTopicRecord(
        topic="preferences",
        summary="Prefers concise answers.",
        memories=["Prefers concise answers."],
        updated_at="2026-04-21T10:00:00+00:00",
        session_ids=["session-1"],
    )
    store.write_topic(session, original, source_id=DEFAULT_MEMORY_SOURCE_ID)

    real_replace = filesystem_module.os.replace

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk-full")

    monkeypatch.setattr(filesystem_module.os, "replace", _boom)
    with pytest.raises(OSError, match="simulated disk-full"):
        store.write_topic(
            session,
            MemoryTopicRecord(
                topic="preferences",
                summary="Updated.",
                memories=["Updated."],
                updated_at="2026-04-21T11:00:00+00:00",
                session_ids=["session-1"],
            ),
            source_id=DEFAULT_MEMORY_SOURCE_ID,
        )

    monkeypatch.setattr(filesystem_module.os, "replace", real_replace)
    surviving = store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic="preferences")
    assert surviving.summary == "Prefers concise answers."
    # Temp file should not be left behind.
    topics_dir = surviving_dir = tmp_path
    leftover = [path for path in topics_dir.rglob(".maf-state-*.tmp")]
    assert leftover == []
    del surviving_dir


async def test_memory_file_store_does_not_mkdir_on_pure_read_paths(tmp_path) -> None:
    """List/read calls on a never-written session should not create any directories."""
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"

    assert store.list_topics(session, source_id=DEFAULT_MEMORY_SOURCE_ID) == []
    assert store.read_state(session, source_id=DEFAULT_MEMORY_SOURCE_ID) == {
        "last_consolidated_at": None,
        "sessions_since_consolidation": [],
        "pending_turn_ids": {},
    }
    assert store.search_transcripts(session, source_id=DEFAULT_MEMORY_SOURCE_ID, query="anything") == []

    # tmp_path itself was passed in by pytest so it exists; assert no children were created.
    assert list(tmp_path.iterdir()) == []


class _RaisingMemoryClient:
    """Chat client that raises a transient error for every consolidation request."""

    additional_properties: dict[str, Any]

    def __init__(self) -> None:
        from agent_framework.exceptions import ChatClientException

        self.additional_properties = {}
        self.error_class = ChatClientException
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
        del messages, stream, options, compaction_strategy, tokenizer
        del function_invocation_kwargs, client_kwargs
        self.calls.append("call")
        raise self.error_class("simulated transient failure")


class _ProgrammerErrorMemoryClient:
    """Chat client whose ``get_response`` raises a non-transient programmer error."""

    additional_properties: dict[str, Any]

    def __init__(self) -> None:
        self.additional_properties = {}

    async def get_response(self, *args: object, **kwargs: object) -> ChatResponse[Any]:
        del args, kwargs
        raise AttributeError("misconfigured client")


async def test_memory_consolidation_transient_failure_preserves_state(tmp_path) -> None:
    """A transient consolidation failure must not advance the maintenance window."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    raising_client = _RaisingMemoryClient()
    provider = MemoryContextProvider(store=store, consolidation_client=raising_client)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    pre_state = {
        "last_consolidated_at": "2026-04-20T09:00:00+00:00",
        "sessions_since_consolidation": ["queued-session"],
        "pending_turn_ids": {"queued-session": "turn-1"},
    }
    store.write_state(session, pre_state, source_id=DEFAULT_MEMORY_SOURCE_ID)
    store.write_topic(
        session,
        MemoryTopicRecord(
            topic="preferences",
            summary="Prefers concise answers.",
            memories=["Prefers concise answers."],
            updated_at="2026-04-21T10:00:00+00:00",
            session_ids=["session-1"],
        ),
        source_id=DEFAULT_MEMORY_SOURCE_ID,
    )

    consolidated_count = await provider._run_consolidation(  # pyright: ignore[reportPrivateUsage]
        client=raising_client,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        session=session,
        force=True,
        now=datetime(2026, 4, 22, tzinfo=timezone.utc),
    )

    assert consolidated_count == 0
    assert raising_client.calls == ["call"]
    assert store.read_state(session, source_id=DEFAULT_MEMORY_SOURCE_ID) == pre_state
    surviving = store.get_topic(session, source_id=DEFAULT_MEMORY_SOURCE_ID, topic="preferences")
    assert surviving.summary == "Prefers concise answers."


async def test_memory_extraction_propagates_programmer_errors(tmp_path) -> None:
    """Non-transient errors from the chat client must surface so misconfigurations fail loudly."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    provider = MemoryContextProvider(store=store)
    bad_client = _ProgrammerErrorMemoryClient()

    from agent_framework import AgentResponse
    from agent_framework._sessions import SessionContext

    context = SessionContext(
        input_messages=[Message(role="user", contents=["q"])],
    )
    context._response = AgentResponse(messages=[Message(role="assistant", contents=["a"])])  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(AttributeError, match="misconfigured client"):
        await provider._extract_memories(  # pyright: ignore[reportPrivateUsage]
            client=bad_client,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
            session=session,
            context=context,
            now=datetime(2026, 4, 22, tzinfo=timezone.utc),
        )


def test_extract_keywords_handles_non_english_text() -> None:
    """Keyword extraction yields tokens for non-English input (#6989).

    The pattern used to be ASCII-only, so CJK/Cyrillic messages produced an
    empty keyword set and therefore never matched any topic file.
    """
    from agent_framework._harness._memory import _extract_keywords  # pyright: ignore[reportPrivateUsage]

    cjk = _extract_keywords([Message(role="user", contents=["こんにちは 元気ですか"])])
    cyrillic = _extract_keywords([Message(role="user", contents=["привет мир друзья"])])
    english = _extract_keywords([Message(role="user", contents=["hello world"])])

    assert cjk == {"こんにちは", "元気ですか"}
    assert cyrillic == {"привет", "мир", "друзья"}
    # English extraction is unchanged.
    assert english == {"hello", "world"}


# region Storage-key parity: identifiers must map injectively onto directories


def test_memory_file_store_derives_distinct_roots_for_colliding_owner_ids(tmp_path) -> None:
    """Owner IDs that a path normalizer would fold together stay separate.

    ``MemoryFileStore`` shares the storage-key derivation with the session
    store, the todo store, and the file-memory provider, so it is held to the
    same injectivity contract. Owner IDs that trip the independent traversal
    guard are rejected outright rather than merged.
    """
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    roots: dict[str, Path] = {}
    rejected: set[str] = set()
    for owner_id in COLLIDING_IDENTIFIERS:
        session = AgentSession(session_id="session-1")
        session.state["owner_id"] = owner_id
        try:
            roots[owner_id] = store._get_memory_root(session, source_id=DEFAULT_MEMORY_SOURCE_ID)
        except ValueError:
            rejected.add(owner_id)

    assert rejected, "the traversal guard should still reject absolute and '..' owner IDs"
    assert len(set(roots.values())) == len(roots), roots
    assert len({str(root).lower() for root in roots.values()}) == len(roots), roots
    assert len(roots) + len(rejected) == len(COLLIDING_IDENTIFIERS)
    for root in roots.values():
        assert root.is_relative_to(tmp_path.resolve())


def test_memory_file_store_encodes_non_ascii_owner_ids(tmp_path) -> None:
    """NFC and NFD spellings of one word must not share a directory."""
    store = MemoryFileStore(tmp_path, owner_state_key="owner_id")
    roots: list[Path] = []
    for owner_id in ("caf\u00e9", "cafe\u0301"):
        session = AgentSession(session_id="session-1")
        session.state["owner_id"] = owner_id
        root = store._get_memory_root(session, source_id=DEFAULT_MEMORY_SOURCE_ID)
        assert all(part.isascii() for part in root.relative_to(tmp_path.resolve()).parts)
        roots.append(root)

    assert roots[0] != roots[1]


def test_memory_file_store_uses_literal_folders_for_safe_identifiers(tmp_path) -> None:
    """Safe identifiers are readable on disk rather than opaque encoded segments."""
    store = MemoryFileStore(tmp_path, owner_prefix="user_", owner_state_key="owner_id")
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"

    root = store._get_memory_root(session, source_id="memory")
    parts = root.relative_to(tmp_path.resolve()).parts
    assert parts[0] == "memory"
    assert parts[1] == "user_alice"


# endregion

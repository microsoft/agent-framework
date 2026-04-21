# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from agent_framework import (
    Agent,
    AgentSession,
    ExperimentalFeature,
    Message,
    SavedItemRecord,
    SavedItemsContextProvider,
    SavedItemsFileStore,
    SavedItemsSessionStore,
    SavedTopicLogEntry,
    SupportsChatGetResponse,
)


def _tool_by_name(tools: list[object], name: str) -> object:
    """Return the tool with the requested name from a prepared tool list."""
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool
    raise AssertionError(f"Tool {name!r} was not found.")


def test_saved_item_record_round_trips_and_tracks_expiration() -> None:
    """Saved item records should preserve value equality and TTL-derived timestamps."""
    created_at = datetime(2026, 4, 16, tzinfo=UTC)
    raw_record = {
        "item_id": "item-1",
        "item_type": "memory",
        "scope": "user",
        "topic": "preferences",
        "text": "Prefers concise answers",
        "date": created_at.isoformat(),
        "session_id": "session-1",
        "owner_id": "alice",
        "ttl_seconds": 60,
    }

    record = SavedItemRecord.from_dict(raw_record)

    assert record == SavedItemRecord(**raw_record)
    assert record.to_dict() == raw_record
    assert record.created_at == created_at
    assert record.expires_at == created_at + timedelta(seconds=60)
    assert not record.is_expired(now=created_at + timedelta(seconds=59))
    assert record.is_expired(now=created_at + timedelta(seconds=60))
    assert "SavedItemRecord(" in repr(record)


def test_saved_topic_log_entry_round_trips_with_value_equality() -> None:
    """Saved topic log entries should preserve value equality without dataclasses."""
    raw_entry = {
        "topic": "preferences",
        "first_seen": "2026-04-16T00:00:00+00:00",
        "last_seen": "2026-04-16T00:05:00+00:00",
        "times_recorded": 2,
    }

    entry = SavedTopicLogEntry.from_dict(raw_entry)

    assert entry == SavedTopicLogEntry(**raw_entry)
    assert entry.to_dict() == raw_entry
    assert "SavedTopicLogEntry(" in repr(entry)


def test_saved_items_session_store_persists_items_topics_and_visibility() -> None:
    """Session-backed saved items should manage visibility, IDs, and historical topics."""
    session = AgentSession(session_id="session-1")
    store = SavedItemsSessionStore()
    created_at = datetime(2026, 4, 16, tzinfo=UTC)

    user_record = SavedItemRecord(
        item_id=store.get_next_item_id(session, source_id="saved_items"),
        item_type="memory",
        scope="user",
        topic="preferences",
        text="Prefers concise answers",
        date=created_at.isoformat(),
        session_id="session-1",
        owner_id=None,
        ttl_seconds=None,
    )
    hidden_session_record = SavedItemRecord(
        item_id=store.get_next_item_id(session, source_id="saved_items"),
        item_type="note",
        scope="session",
        topic="drafts",
        text="Only visible in another session",
        date=(created_at + timedelta(minutes=1)).isoformat(),
        session_id="session-2",
        owner_id=None,
        ttl_seconds=None,
    )
    visible_session_record = SavedItemRecord(
        item_id=store.get_next_item_id(session, source_id="saved_items"),
        item_type="note",
        scope="session",
        topic="travel",
        text="Visit Oslo in June",
        date=(created_at + timedelta(minutes=2)).isoformat(),
        session_id="session-1",
        owner_id=None,
        ttl_seconds=None,
    )

    store.write_item(session, user_record, source_id="saved_items")
    store.write_item(session, hidden_session_record, source_id="saved_items")
    store.write_item(session, visible_session_record, source_id="saved_items")
    store.record_topic(session, source_id="saved_items", topic="preferences", now=created_at)
    store.record_topic(session, source_id="saved_items", topic="preferences", now=created_at + timedelta(minutes=5))

    assert store.get_item(session, source_id="saved_items", item_id=user_record.item_id) == user_record
    assert store.list_items(session, source_id="saved_items", scope="user") == [user_record]
    assert store.list_items(session, source_id="saved_items", scope="session", session_id="session-1") == [
        visible_session_record
    ]
    assert [record.item_id for record in store.list_visible_items(session, source_id="saved_items")] == [
        user_record.item_id,
        visible_session_record.item_id,
    ]
    with pytest.raises(PermissionError, match="not visible"):
        store.get_visible_item(session, source_id="saved_items", item_id=hidden_session_record.item_id)

    assert store.list_topics(session, source_id="saved_items") == [
        SavedTopicLogEntry(
            topic="preferences",
            first_seen=created_at.replace(microsecond=0).isoformat(),
            last_seen=(created_at + timedelta(minutes=5)).replace(microsecond=0).isoformat(),
            times_recorded=2,
        )
    ]


def test_saved_items_store_prunes_expired_items() -> None:
    """Saved item stores should delete expired records through the shared prune API."""
    session = AgentSession(session_id="session-1")
    store = SavedItemsSessionStore()
    created_at = datetime(2026, 4, 16, tzinfo=UTC)
    expired_record = SavedItemRecord(
        item_id="item-1",
        item_type="memory",
        scope="session",
        topic="temporary",
        text="Short-lived context",
        date=created_at.isoformat(),
        session_id="session-1",
        owner_id=None,
        ttl_seconds=30,
    )

    store.write_item(session, expired_record, source_id="saved_items")

    removed_records = store.prune_expired_items(
        session,
        source_id="saved_items",
        now=created_at + timedelta(seconds=31),
    )

    assert removed_records == [expired_record]
    with pytest.raises(FileNotFoundError, match="item-1"):
        store.get_item(session, source_id="saved_items", item_id="item-1")


def test_saved_items_file_store_shares_user_scoped_items_across_sessions(tmp_path) -> None:
    """Saved-item file storage should share user-scoped records and merge topic logs."""
    store = SavedItemsFileStore(
        tmp_path,
        kind="memories",
        owner_prefix="user_",
        owner_state_key="owner_id",
        dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True),
        loads=json.loads,
    )
    session_one = AgentSession(session_id="session-1")
    session_one.state["owner_id"] = "alice"
    session_two = AgentSession(session_id="session-2")
    session_two.state["owner_id"] = "alice"
    created_at = datetime(2026, 4, 16, tzinfo=UTC)

    user_record = SavedItemRecord(
        item_id="item-1",
        item_type="memory",
        scope="user",
        topic="preferences",
        text="Prefers concise answers",
        date=created_at.isoformat(),
        session_id="session-1",
        owner_id="alice",
        ttl_seconds=None,
    )
    session_record = SavedItemRecord(
        item_id="item-2",
        item_type="note",
        scope="session",
        topic="travel",
        text="Visit Oslo in June",
        date=(created_at + timedelta(minutes=1)).isoformat(),
        session_id="session-1",
        owner_id="alice",
        ttl_seconds=None,
    )

    store.write_item(session_one, user_record, source_id="saved_items")
    store.write_item(session_one, session_record, source_id="saved_items")
    store.record_topic(session_one, source_id="saved_items", topic="preferences", now=created_at)
    store.record_topic(session_two, source_id="saved_items", topic="preferences", now=created_at + timedelta(minutes=1))

    assert store.get_item(session_two, source_id="saved_items", item_id="item-1") == user_record
    assert store.list_items(session_two, source_id="saved_items", scope="user") == [user_record]
    assert store.list_items(session_two, source_id="saved_items", scope="session", session_id="session-1") == [
        session_record
    ]
    assert store.list_topics(session_two, source_id="saved_items") == [
        SavedTopicLogEntry(
            topic="preferences",
            first_seen=created_at.replace(microsecond=0).isoformat(),
            last_seen=(created_at + timedelta(minutes=1)).replace(microsecond=0).isoformat(),
            times_recorded=2,
        )
    ]
    assert store.get_next_item_id(session_two, source_id="saved_items") == "item-3"
    assert (tmp_path / "user_alice" / "memories" / "session-1" / "item-1.json").exists()


async def test_saved_items_context_provider_tools_manage_visible_items(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Saved-items provider tools should create, update, list, and delete visible items."""
    session = AgentSession(session_id="session-1")
    provider = SavedItemsContextProvider(dumps=lambda value: json.dumps(value, separators=(",", ":"), sort_keys=True))
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Remember this"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    add_saved_item = _tool_by_name(tools, "add_saved_item")
    read_saved_item = _tool_by_name(tools, "read_saved_item")
    update_saved_item = _tool_by_name(tools, "update_saved_item")
    set_saved_item_ttl = _tool_by_name(tools, "set_saved_item_ttl")
    delete_saved_item = _tool_by_name(tools, "delete_saved_item")
    list_saved_items = _tool_by_name(tools, "list_saved_items")
    list_saved_item_topics = _tool_by_name(tools, "list_saved_item_topics")

    add_result = await add_saved_item.invoke(
        arguments={
            "topic": "preferences",
            "text": "Prefers concise answers",
            "item_type": "memory",
            "scope": "session",
        }
    )
    created_record = json.loads(add_result[0].text)
    item_id = created_record["item_id"]
    assert created_record["topic"] == "preferences"

    read_result = await read_saved_item.invoke(arguments={"item_id": item_id})
    assert json.loads(read_result[0].text)["text"] == "Prefers concise answers"

    update_result = await update_saved_item.invoke(
        arguments={
            "item_id": item_id,
            "topic": "travel",
            "text": "Visit Oslo in June",
            "item_type": "note",
        }
    )
    updated_record = json.loads(update_result[0].text)
    assert updated_record["topic"] == "travel"
    assert updated_record["item_type"] == "note"

    list_result = await list_saved_items.invoke(arguments={"scope": "session"})
    assert json.loads(list_result[0].text) == [updated_record]

    topics_result = await list_saved_item_topics.invoke()
    assert {entry["topic"] for entry in json.loads(topics_result[0].text)} == {"preferences", "travel"}

    ttl_result = await set_saved_item_ttl.invoke(arguments={"item_id": item_id, "ttl_seconds": 60})
    ttl_record = json.loads(ttl_result[0].text)
    assert ttl_record["ttl_seconds"] == 60
    assert ttl_record["ttl"] == "60 seconds"

    delete_result = await delete_saved_item.invoke(arguments={"item_id": item_id})
    assert delete_result[0].text == f"Deleted saved item '{item_id}'."

    final_list_result = await list_saved_items.invoke(arguments={"scope": "session"})
    assert json.loads(final_list_result[0].text) == []


def test_saved_items_harness_classes_are_marked_experimental() -> None:
    """Saved-items harness public classes should expose HARNESS experimental metadata."""
    assert SavedItemRecord.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert SavedTopicLogEntry.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert SavedItemsSessionStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert SavedItemsFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert SavedItemsContextProvider.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert ".. warning:: Experimental" in SavedItemsContextProvider.__doc__

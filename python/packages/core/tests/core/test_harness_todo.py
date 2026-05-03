# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_framework import (
    Agent,
    AgentSession,
    ExperimentalFeature,
    Message,
    SupportsChatGetResponse,
    TodoFileStore,
    TodoInput,
    TodoItem,
    TodoListContextProvider,
    TodoSessionStore,
    TodoStore,
)


def _tool_by_name(tools: list[object], name: str) -> object:
    """Return the tool with the requested name from a prepared tool list."""
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool
    raise AssertionError(f"Tool {name!r} was not found.")


def test_todo_item_round_trips_with_value_equality() -> None:
    """Todo items should support value equality and JSON serialization."""
    raw_item = {
        "id": 1,
        "title": "Write tests",
        "description": "Cover the harness",
        "is_complete": False,
    }

    item = TodoItem.from_dict(raw_item)

    assert item == TodoItem(**raw_item)
    assert item.to_dict() == raw_item
    assert json.loads(item.to_json()) == raw_item
    assert "TodoItem(" in repr(item)


def test_todo_input_round_trips_and_validates() -> None:
    """Todo input should trim titles and reject invalid payloads."""
    todo_input = TodoInput.from_dict({"title": "  Write tests  ", "description": "Cover the harness"})

    assert todo_input.title == "Write tests"
    assert todo_input.to_dict() == {"title": "Write tests", "description": "Cover the harness"}
    assert json.loads(todo_input.to_json()) == {"title": "Write tests", "description": "Cover the harness"}

    with pytest.raises(ValueError, match="non-empty string"):
        TodoInput(title="   ")

    with pytest.raises(ValueError, match="description must be a string or null"):
        TodoInput.from_dict({"title": "Write tests", "description": 123})


def test_todo_session_store_initializes_and_round_trips_state() -> None:
    """Session-backed todo storage should initialize and persist todo state."""
    session = AgentSession(session_id="session-1")
    store = TodoSessionStore()

    items, next_id = store.load_state(session, source_id="todo")
    assert items == []
    assert next_id == 1
    assert session.state["todo"] == {"items": [], "next_id": 1}

    todo_item = TodoItem(id=1, title="Ship feature", description="Use session storage")
    store.save_state(session, [todo_item], next_id=2, source_id="todo")

    loaded_items, loaded_next_id = store.load_state(session, source_id="todo")
    assert loaded_items == [todo_item]
    assert loaded_next_id == 2
    assert store.load_items(session, source_id="todo") == [todo_item]


def test_todo_file_store_round_trips_state(tmp_path: Path) -> None:
    """Todo file storage should persist one JSON state file per owner and session."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = TodoFileStore(
        tmp_path,
        kind="todos",
        owner_prefix="user_",
        owner_state_key="owner_id",
    )

    store.save_state(
        session,
        [TodoItem(id=1, title="Ship feature", description="Use file storage")],
        next_id=2,
        source_id="todo",
    )

    items, next_id = store.load_state(session, source_id="todo")
    assert items == [TodoItem(id=1, title="Ship feature", description="Use file storage", is_complete=False)]
    assert next_id == 2

    state_path = tmp_path / "user_alice" / "todos" / "session-1" / "todos.todo.json"
    assert state_path.exists()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "items": [{"id": 1, "title": "Ship feature", "description": "Use file storage", "is_complete": False}],
        "next_id": 2,
    }

    with pytest.raises(RuntimeError, match="owner_id"):
        store.load_state(AgentSession(session_id="missing-owner"), source_id="todo")


def test_todo_session_store_rejects_non_mapping_items() -> None:
    """Session-backed todo storage should report malformed item entries clearly."""
    session = AgentSession(session_id="session-1")
    session.state["todo"] = {"items": [{"id": 1, "title": "Good"}, "bad"], "next_id": 2}
    store = TodoSessionStore()

    with pytest.raises(ValueError, match="index 1.*str"):
        store.load_state(session, source_id="todo")


def test_todo_file_store_namespaces_state_by_source_id(tmp_path: Path) -> None:
    """File-backed todo storage should isolate providers that share a session."""
    session = AgentSession(session_id="session-1")
    store = TodoFileStore(tmp_path)

    store.save_state(session, [TodoItem(id=1, title="First source")], next_id=2, source_id="first")
    store.save_state(session, [TodoItem(id=1, title="Second source")], next_id=2, source_id="second")

    first_items, _ = store.load_state(session, source_id="first")
    second_items, _ = store.load_state(session, source_id="second")

    assert first_items == [TodoItem(id=1, title="First source")]
    assert second_items == [TodoItem(id=1, title="Second source")]
    assert (tmp_path / "session-1" / "todos.first.json").exists()
    assert (tmp_path / "session-1" / "todos.second.json").exists()


def test_todo_file_store_rejects_session_path_traversal(tmp_path: Path) -> None:
    """File-backed todo storage should not write outside its base path for malicious session IDs."""
    session = AgentSession(session_id="../escape")
    store = TodoFileStore(tmp_path)

    with pytest.raises(ValueError, match="session_id.*path separators"):
        store.save_state(session, [TodoItem(id=1, title="Escape")], next_id=2, source_id="todo")

    assert list(tmp_path.rglob("*")) == []


async def test_todo_context_provider_tools_manage_session_state(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Todo provider tools should add, complete, remove, and list session-backed todos."""
    session = AgentSession(session_id="session-1")
    provider = TodoListContextProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Track this work"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    add_todos = _tool_by_name(tools, "add_todos")
    complete_todos = _tool_by_name(tools, "complete_todos")
    remove_todos = _tool_by_name(tools, "remove_todos")
    get_remaining_todos = _tool_by_name(tools, "get_remaining_todos")
    get_all_todos = _tool_by_name(tools, "get_all_todos")

    add_result = await add_todos.invoke(
        arguments={
            "todos": [
                {"title": "  Write tests  ", "description": "  Cover stores  "},
                {"title": "Ship feature"},
            ]
        }
    )
    assert json.loads(add_result[0].text) == [
        {"id": 1, "title": "Write tests", "description": "Cover stores", "is_complete": False},
        {"id": 2, "title": "Ship feature", "description": None, "is_complete": False},
    ]

    complete_result = await complete_todos.invoke(arguments={"ids": [1]})
    assert json.loads(complete_result[0].text) == {"completed": 1}

    remaining_result = await get_remaining_todos.invoke()
    assert json.loads(remaining_result[0].text) == [
        {"id": 2, "title": "Ship feature", "description": None, "is_complete": False}
    ]

    remove_result = await remove_todos.invoke(arguments={"ids": [2]})
    assert json.loads(remove_result[0].text) == {"removed": 1}

    get_all_result = await get_all_todos.invoke()
    assert json.loads(get_all_result[0].text) == [
        {"id": 1, "title": "Write tests", "description": "Cover stores", "is_complete": True}
    ]


async def test_todo_context_provider_serializes_concurrent_mutations(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Concurrent todo mutations should not duplicate IDs or lose updates."""
    session = AgentSession(session_id="session-1")
    provider = TodoListContextProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Track this work"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    add_todos = _tool_by_name(tools, "add_todos")
    complete_todos = _tool_by_name(tools, "complete_todos")
    get_all_todos = _tool_by_name(tools, "get_all_todos")

    await add_todos.invoke(arguments={"todos": [{"title": f"Existing {index}"} for index in range(1, 6)]})

    await asyncio.gather(
        add_todos.invoke(arguments={"todos": [{"title": "Add A1"}, {"title": "Add A2"}]}),
        add_todos.invoke(arguments={"todos": [{"title": "Add B1"}, {"title": "Add B2"}]}),
        complete_todos.invoke(arguments={"ids": [1, 2, 3, 4, 5]}),
    )

    get_all_result = await get_all_todos.invoke()
    payload = json.loads(get_all_result[0].text)
    ids = [item["id"] for item in payload]

    assert sorted(ids) == list(range(1, 10))
    assert len(ids) == len(set(ids))
    assert {item["title"] for item in payload} == {
        "Existing 1",
        "Existing 2",
        "Existing 3",
        "Existing 4",
        "Existing 5",
        "Add A1",
        "Add A2",
        "Add B1",
        "Add B2",
    }
    assert {item["id"] for item in payload if item["is_complete"]} == {1, 2, 3, 4, 5}


def test_todo_harness_classes_are_marked_experimental() -> None:
    """Todo harness public classes should expose HARNESS experimental metadata."""
    assert TodoStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert TodoItem.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert TodoInput.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert TodoSessionStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert TodoFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert TodoListContextProvider.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert ".. warning:: Experimental" in TodoListContextProvider.__doc__

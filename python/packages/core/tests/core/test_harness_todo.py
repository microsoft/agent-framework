# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import threading
from pathlib import Path

import pytest

from agent_framework import (
    Agent,
    AgentSession,
    ExperimentalFeature,
    Message,
    SupportsChatGetResponse,
    TodoFileStore,
    TodoItem,
    TodoProvider,
    TodoSessionStore,
    TodoStore,
)
from agent_framework._harness._todo import TodoInput

from .test_filesystem import COLLIDING_IDENTIFIERS


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

    assert item == TodoItem(**raw_item)  # type: ignore[arg-type]
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


async def test_todo_session_store_initializes_and_round_trips_state() -> None:
    """Session-backed todo storage should initialize and persist todo state."""
    session = AgentSession(session_id="session-1")
    store = TodoSessionStore()

    items, next_id = await store.load_state(session, source_id="todo")
    assert items == []
    assert next_id == 1
    assert session.state["todo"] == {}

    todo_item = TodoItem(id=1, title="Ship feature", description="Use session storage")
    await store.save_state(session, [todo_item], next_id=2, source_id="todo")

    loaded_items, loaded_next_id = await store.load_state(session, source_id="todo")
    assert loaded_items == [todo_item]
    assert loaded_next_id == 2
    assert await store.load_items(session, source_id="todo") == [todo_item]


async def test_todo_file_store_round_trips_state(tmp_path: Path) -> None:
    """Todo file storage should persist one JSON state file per owner and session."""
    session = AgentSession(session_id="session-1")
    session.state["owner_id"] = "alice"
    store = TodoFileStore(
        tmp_path,
        kind="todos",
        owner_prefix="user_",
        owner_state_key="owner_id",
    )

    await store.save_state(
        session,
        [TodoItem(id=1, title="Ship feature", description="Use file storage")],
        next_id=2,
        source_id="todo",
    )

    items, next_id = await store.load_state(session, source_id="todo")
    assert items == [TodoItem(id=1, title="Ship feature", description="Use file storage", is_complete=False)]
    assert next_id == 2

    state_path = tmp_path / "user_alice" / "todos" / "session-1" / "todos.todo.json"
    assert state_path.exists()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "items": [{"id": 1, "title": "Ship feature", "description": "Use file storage", "is_complete": False}],
        "next_id": 2,
    }

    with pytest.raises(RuntimeError, match="owner_id"):
        await store.load_state(AgentSession(session_id="missing-owner"), source_id="todo")


async def test_todo_file_store_load_does_not_create_directories(tmp_path: Path) -> None:
    """Loading from a never-written session must not create empty directories on disk."""
    session = AgentSession(session_id="session-1")
    store = TodoFileStore(tmp_path)

    items, next_id = await store.load_state(session, source_id="todo")
    assert items == []
    assert next_id == 1
    assert list(tmp_path.iterdir()) == []  # noqa: ASYNC240


async def test_todo_file_store_writes_state_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash between writing the temp file and renaming must not corrupt existing state."""
    session = AgentSession(session_id="session-1")
    store = TodoFileStore(tmp_path)

    await store.save_state(session, [TodoItem(id=1, title="Initial")], next_id=2, source_id="todo")
    state_path = tmp_path / "session-1" / "todos.todo.json"
    original_contents = state_path.read_text(encoding="utf-8")

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError, match="disk full"):
        await store.save_state(session, [TodoItem(id=2, title="Replacement")], next_id=3, source_id="todo")

    # Original file is untouched, no temp leftovers.
    assert state_path.read_text(encoding="utf-8") == original_contents
    assert sorted(p.name for p in state_path.parent.iterdir()) == [state_path.name]


async def test_todo_session_store_rejects_non_mapping_items() -> None:
    """Session-backed todo storage should report malformed item entries clearly."""
    session = AgentSession(session_id="session-1")
    session.state["todo"] = {"items": [{"id": 1, "title": "Good"}, "bad"], "next_id": 2}
    store = TodoSessionStore()

    with pytest.raises(ValueError, match="index 1.*str"):
        await store.load_state(session, source_id="todo")


async def test_todo_session_store_rejects_malformed_state_types() -> None:
    """Session-backed todo storage should raise for malformed top-level state, mirroring TodoFileStore."""
    session = AgentSession(session_id="session-1")
    session.state["todo"] = "not a dict"
    store = TodoSessionStore()

    with pytest.raises(ValueError, match="must be a dict"):
        await store.load_state(session, source_id="todo")

    session.state["todo"] = {"items": "not a list", "next_id": 1}
    with pytest.raises(ValueError, match="non-list 'items'"):
        await store.load_state(session, source_id="todo")

    session.state["todo"] = {"items": [], "next_id": "1"}
    with pytest.raises(ValueError, match="non-integer 'next_id'"):
        await store.load_state(session, source_id="todo")


async def test_todo_stores_clamp_next_id_to_avoid_collisions(tmp_path: Path) -> None:
    """Both stores should clamp ``next_id`` to ``max(item.id) + 1`` to prevent ID collisions."""
    session_a = AgentSession(session_id="session-a")
    session_a.state["todo"] = {"items": [{"id": 5, "title": "Seeded"}], "next_id": 1}

    session_store = TodoSessionStore()
    items, next_id = await session_store.load_state(session_a, source_id="todo")
    assert next_id == 6  # clamped over the stored next_id of 1
    assert items == [TodoItem(id=5, title="Seeded")]

    session_b = AgentSession(session_id="session-b")
    file_store = TodoFileStore(tmp_path)
    state_path = tmp_path / "session-b" / "todos.todo.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"items": [{"id": 7, "title": "Seeded"}], "next_id": 1}) + "\n", encoding="utf-8")
    items, next_id = await file_store.load_state(session_b, source_id="todo")
    assert next_id == 8
    assert items == [TodoItem(id=7, title="Seeded")]


async def test_todo_mutation_locks_are_evicted_when_no_longer_needed() -> None:
    """Mutation locks should not be retained once no mutation holds or awaits them."""
    import gc

    from agent_framework._harness._todo import _TODO_MUTATION_LOCKS

    store = TodoSessionStore()
    provider = TodoProvider(store=store)
    session = AgentSession(session_id="session-1")
    lock = provider._mutation_lock(session)  # pyright: ignore[reportPrivateUsage]
    assert len(_TODO_MUTATION_LOCKS) == 1

    del lock, session, provider
    gc.collect()
    assert len(_TODO_MUTATION_LOCKS) == 0


async def test_todo_mutation_lock_is_scoped_to_the_storage_identity() -> None:
    """Providers over one storage identity share a lock; another identity gets its own."""
    session = AgentSession(session_id="session-1")
    first_provider = TodoProvider(store=TodoSessionStore())
    second_provider = TodoProvider(store=TodoSessionStore())
    other_session_provider = TodoProvider(store=TodoSessionStore())

    lock = first_provider._mutation_lock(session)  # pyright: ignore[reportPrivateUsage]
    # Session stores keep their state on the session object itself, so both providers —
    # and both stores — serialize on that one session instance.
    assert second_provider._mutation_lock(session) is lock  # pyright: ignore[reportPrivateUsage]
    assert other_session_provider._mutation_lock(AgentSession(session_id="session-1")) is not lock  # pyright: ignore[reportPrivateUsage]


async def test_todo_mutation_lock_shares_one_file_identity_for_equivalent_sessions(tmp_path: Path) -> None:
    """Sessions that resolve to the same todo file must share one mutation lock."""
    provider = TodoProvider(store=TodoFileStore(tmp_path))
    first_lock = provider._mutation_lock(AgentSession(session_id="session-1"))  # pyright: ignore[reportPrivateUsage]
    second_lock = provider._mutation_lock(AgentSession(session_id="session-1"))  # pyright: ignore[reportPrivateUsage]
    assert first_lock is second_lock

    # A different session ID resolves to a different file and keeps its own lock.
    assert provider._mutation_lock(AgentSession(session_id="session-2")) is not first_lock  # pyright: ignore[reportPrivateUsage]

    # Two store instances over the same directory resolve to the same file as well.
    other_provider = TodoProvider(store=TodoFileStore(tmp_path))
    assert other_provider._mutation_lock(AgentSession(session_id="session-1")) is first_lock  # pyright: ignore[reportPrivateUsage]


def test_todo_mutation_lock_is_scoped_to_the_event_loop() -> None:
    """Reusing a session across ``asyncio.run`` boundaries must not reuse a loop-bound lock."""

    async def _lock_from_new_loop(provider: TodoProvider, session: AgentSession) -> asyncio.Lock:
        return provider._mutation_lock(session)  # pyright: ignore[reportPrivateUsage]

    provider = TodoProvider()
    session = AgentSession(session_id="session-1")
    first_lock = asyncio.run(_lock_from_new_loop(provider, session))
    second_lock = asyncio.run(_lock_from_new_loop(provider, session))
    assert first_lock is not second_lock


async def test_todo_file_store_rejects_session_path_traversal(tmp_path: Path) -> None:
    """File-backed todo storage should not write outside its base path for malicious session IDs."""
    session = AgentSession(session_id="../escape")
    store = TodoFileStore(tmp_path)

    with pytest.raises(ValueError, match="session_id.*path separators"):
        await store.save_state(session, [TodoItem(id=1, title="Escape")], next_id=2, source_id="todo")

    assert list(tmp_path.rglob("*")) == []  # noqa: ASYNC240


async def test_todo_file_store_namespaces_state_by_source_id(tmp_path: Path) -> None:
    """File-backed todo storage should isolate providers that share a session."""
    session = AgentSession(session_id="session-1")
    store = TodoFileStore(tmp_path)

    await store.save_state(session, [TodoItem(id=1, title="First source")], next_id=2, source_id="first")
    await store.save_state(session, [TodoItem(id=1, title="Second source")], next_id=2, source_id="second")

    first_items, _ = await store.load_state(session, source_id="first")
    second_items, _ = await store.load_state(session, source_id="second")

    assert first_items == [TodoItem(id=1, title="First source")]
    assert second_items == [TodoItem(id=1, title="Second source")]
    assert (tmp_path / "session-1" / "todos.first.json").exists()
    assert (tmp_path / "session-1" / "todos.second.json").exists()


async def test_todo_provider_runs_with_file_store(tmp_path: Path, chat_client_base: SupportsChatGetResponse) -> None:
    """The provider should drive the full add/list flow when backed by ``TodoFileStore``."""
    session = AgentSession(session_id="session-1")
    provider = TodoProvider(store=TodoFileStore(tmp_path))
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Track this work"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    add_todos = _tool_by_name(tools, "todos_add")
    get_all_todos = _tool_by_name(tools, "todos_get_all")

    await add_todos.invoke(arguments={"todos": [{"title": "Persist me"}]})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    state_path = tmp_path / "session-1" / "todos.todo.json"
    assert state_path.exists()
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["items"] == [{"id": 1, "title": "Persist me", "description": None, "is_complete": False}]
    assert persisted["next_id"] == 2

    get_all_result = await get_all_todos.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(get_all_result[0].text) == [
        {"id": 1, "title": "Persist me", "description": None, "is_complete": False}
    ]


async def test_todo_provider_tools_manage_session_state(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Todo provider tools should add, complete, remove, and list session-backed todos."""
    session = AgentSession(session_id="session-1")
    provider = TodoProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Track this work"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    add_todos = _tool_by_name(tools, "todos_add")
    complete_todos = _tool_by_name(tools, "todos_complete")
    remove_todos = _tool_by_name(tools, "todos_remove")
    get_remaining_todos = _tool_by_name(tools, "todos_get_remaining")
    get_all_todos = _tool_by_name(tools, "todos_get_all")

    add_result = await add_todos.invoke(  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
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

    complete_result = await complete_todos.invoke(arguments={"items": [{"id": 1, "reason": "Tests written"}]})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(complete_result[0].text) == {"completed": 1}

    remaining_result = await get_remaining_todos.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(remaining_result[0].text) == [
        {"id": 2, "title": "Ship feature", "description": None, "is_complete": False}
    ]

    remove_result = await remove_todos.invoke(arguments={"ids": [2]})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(remove_result[0].text) == {"removed": 1}

    get_all_result = await get_all_todos.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(get_all_result[0].text) == [
        {"id": 1, "title": "Write tests", "description": "Cover stores", "is_complete": True}
    ]


async def test_todo_provider_serializes_concurrent_mutations(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Concurrent todo mutations should not duplicate IDs or lose updates."""
    session = AgentSession(session_id="session-1")
    provider = TodoProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Track this work"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    add_todos = _tool_by_name(tools, "todos_add")
    complete_todos = _tool_by_name(tools, "todos_complete")
    get_all_todos = _tool_by_name(tools, "todos_get_all")

    await add_todos.invoke(arguments={"todos": [{"title": f"Existing {index}"} for index in range(1, 6)]})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    await asyncio.gather(
        add_todos.invoke(arguments={"todos": [{"title": "Add A1"}, {"title": "Add A2"}]}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        add_todos.invoke(arguments={"todos": [{"title": "Add B1"}, {"title": "Add B2"}]}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        complete_todos.invoke(arguments={"items": [{"id": i, "reason": "Done"} for i in range(1, 6)]}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    )

    get_all_result = await get_all_todos.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
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


async def test_todo_providers_sharing_one_store_serialize_mutations(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Two providers over one shared store must not load the same state and drop an add."""

    class _GatedSharedTodoStore(TodoStore):
        """Hold each load until a competing caller also finishes loading, so the loads interleave."""

        GATE_TIMEOUT = 0.25

        def __init__(self) -> None:
            self.items: list[TodoItem] = []
            self.next_id = 1
            self.load_count = 0
            self.both_loaded = asyncio.Event()

        def reset_gate(self) -> None:
            self.load_count = 0
            self.both_loaded.clear()

        async def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
            snapshot = (list(self.items), self.next_id)
            self.load_count += 1
            if self.load_count >= 2:
                self.both_loaded.set()
            # A caller whose mutations are already serialized never sees a competing load,
            # so bound the wait instead of blocking until the gate opens.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.both_loaded.wait(), timeout=self.GATE_TIMEOUT)
            return snapshot

        async def save_state(
            self, session: AgentSession, items: list[TodoItem], *, next_id: int, source_id: str
        ) -> None:
            self.items = list(items)
            self.next_id = next_id

    session = AgentSession(session_id="session-1")
    store = _GatedSharedTodoStore()
    add_tools = []
    for _ in range(2):
        agent = Agent(client=chat_client_base, context_providers=[TodoProvider(store=store)])
        _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
            session=session,
            input_messages=[Message(role="user", contents=["Track this work"])],
        )
        tools = options["tools"]
        assert isinstance(tools, list)
        add_tools.append(_tool_by_name(tools, "todos_add"))

    # Preparation above loads the todo list once per provider; gate only the mutations.
    store.reset_gate()

    results = await asyncio.gather(
        add_tools[0].invoke(arguments={"todos": [{"title": "From A"}]}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        add_tools[1].invoke(arguments={"todos": [{"title": "From B"}]}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    )

    reported_ids = sorted(json.loads(result[0].text)[0]["id"] for result in results)
    assert store.load_count == 2
    assert sorted(item.id for item in store.items) == [1, 2]
    assert {item.title for item in store.items} == {"From A", "From B"}
    assert reported_ids == [1, 2]


async def test_todo_providers_serialize_equivalent_sessions_over_one_file(
    tmp_path: Path, chat_client_base: SupportsChatGetResponse
) -> None:
    """Two sessions that resolve to the same todo file must not both start from an empty state."""

    class _GatedFileTodoStore(TodoFileStore):
        """Hold each load until a competing caller also finishes loading, so the loads interleave."""

        GATE_TIMEOUT = 0.25

        def __init__(self, base_path: Path) -> None:
            super().__init__(base_path)
            self.load_count = 0
            self.both_loaded = asyncio.Event()

        def reset_gate(self) -> None:
            self.load_count = 0
            self.both_loaded.clear()

        async def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
            result = await super().load_state(session, source_id=source_id)
            self.load_count += 1
            if self.load_count >= 2:
                self.both_loaded.set()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.both_loaded.wait(), timeout=self.GATE_TIMEOUT)
            return result

    store = _GatedFileTodoStore(tmp_path)
    add_tools = []
    for _ in range(2):
        agent = Agent(client=chat_client_base, context_providers=[TodoProvider(store=store)])
        _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
            session=AgentSession(session_id="session-1"),
            input_messages=[Message(role="user", contents=["Track this work"])],
        )
        tools = options["tools"]
        assert isinstance(tools, list)
        add_tools.append(_tool_by_name(tools, "todos_add"))

    # Preparation above loads the todo list once per provider; gate only the mutations.
    store.reset_gate()

    results = await asyncio.gather(
        add_tools[0].invoke(arguments={"todos": [{"title": "From A"}]}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        add_tools[1].invoke(arguments={"todos": [{"title": "From B"}]}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    )

    # Distinct session objects, one shared file: serialized mutations assign unique IDs.
    reported_ids = sorted(json.loads(result[0].text)[0]["id"] for result in results)
    assert reported_ids == [1, 2]


async def test_todo_mutation_keeps_lock_until_cancelled_write_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chat_client_base: SupportsChatGetResponse
) -> None:
    """A cancelled mutation must not release the lock while its write is still in flight."""
    store = TodoFileStore(tmp_path)
    provider = TodoProvider(store=store)
    session = AgentSession(session_id="session-1")
    agent = Agent(client=chat_client_base, context_providers=[provider])
    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Track this work"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)
    add_todos = _tool_by_name(tools, "todos_add")

    write_started = threading.Event()
    release_write = threading.Event()
    real_save = TodoFileStore._save_state_sync

    def _gated_save_sync(state_path: Path, payload: str) -> None:
        write_started.set()
        release_write.wait(timeout=5)
        real_save(state_path, payload)

    monkeypatch.setattr(TodoFileStore, "_save_state_sync", staticmethod(_gated_save_sync))

    first = asyncio.create_task(
        add_todos.invoke(arguments={"todos": [{"title": "Survives"}]})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    )
    await asyncio.to_thread(write_started.wait, 5)
    first.cancel()
    # Give the cancellation a chance to (wrongly) release the lock while the write runs.
    await asyncio.sleep(0.1)

    second = asyncio.create_task(
        add_todos.invoke(arguments={"todos": [{"title": "After"}]})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    )
    await asyncio.sleep(0.1)
    assert not second.done(), "the second mutation must wait for the in-flight write to finish"

    release_write.set()
    with contextlib.suppress(asyncio.CancelledError):
        await first
    await second

    items, _ = await store.load_state(session, source_id=provider.source_id)
    assert [item.title for item in items] == ["Survives", "After"]
    assert [item.id for item in items] == [1, 2]


def test_todo_harness_graduated_classes_are_not_experimental() -> None:
    """Graduated todo harness types should carry no experimental metadata; TodoFileStore stays experimental."""
    for graduated in (TodoStore, TodoItem, TodoInput, TodoSessionStore, TodoProvider):
        assert not hasattr(graduated, "__feature_id__")
    assert TodoProvider.__doc__ is not None
    assert ".. warning:: Experimental" not in TodoProvider.__doc__

    # TodoFileStore remains opt-in and experimental.
    assert TodoFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert TodoFileStore.__doc__ is not None
    assert ".. warning:: Experimental" in TodoFileStore.__doc__


def test_todo_file_store_derives_distinct_directories_for_colliding_owner_ids(tmp_path: Path) -> None:
    """Owner IDs that a path normalizer would fold together stay separate.

    ``TodoFileStore`` shares the storage-key derivation with the session store,
    the memory store, and the file-memory provider, so it is held to the same
    injectivity contract.
    """
    store = TodoFileStore(tmp_path, owner_state_key="owner_id")
    paths: dict[str, Path] = {}
    for owner_id in COLLIDING_IDENTIFIERS:
        session = AgentSession(session_id="session-1")
        session.state["owner_id"] = owner_id
        paths[owner_id] = store._get_state_path(session, source_id="todo")  # pyright: ignore[reportPrivateUsage]

    assert len(set(paths.values())) == len(COLLIDING_IDENTIFIERS), paths
    assert len({str(path).lower() for path in paths.values()}) == len(COLLIDING_IDENTIFIERS), paths
    for path in paths.values():
        assert path.is_relative_to(tmp_path.resolve())


def test_todo_file_store_encodes_non_ascii_owner_ids(tmp_path: Path) -> None:
    """Non-ASCII IDs are encoded, not used verbatim.

    A literal non-ASCII directory name is folded onto a single entry by macOS
    APFS/HFS+, so the NFC and NFD spellings of one word would otherwise share a
    directory despite being byte-distinct.
    """
    store = TodoFileStore(tmp_path, owner_state_key="owner_id")
    paths: list[Path] = []
    for owner_id in ("caf\u00e9", "cafe\u0301"):
        session = AgentSession(session_id="session-1")
        session.state["owner_id"] = owner_id
        path = store._get_state_path(session, source_id="todo")  # pyright: ignore[reportPrivateUsage]
        assert path.parent.parent.name.isascii()
        paths.append(path)

    assert paths[0] != paths[1]


def test_todo_file_store_encodes_windows_reserved_stems_with_an_extension(tmp_path: Path) -> None:
    """``CON.txt`` still resolves to the reserved console device on Windows."""
    session = AgentSession(session_id="CON.txt")
    store = TodoFileStore(tmp_path)
    path = store._get_state_path(session, source_id="todo")  # pyright: ignore[reportPrivateUsage]
    assert path.parent.name.startswith("~todo-")

# Copyright (c) Microsoft. All rights reserved.

"""Tests for the ThreadSnapshotSession interface.

ThreadSnapshotSession is the single owner of the AG-UI Thread Snapshot
lifecycle: load-once at open, hydration replay, effective-state overlay,
resume message seeding, and save-with-swallow semantics. These tests drive
that interface only; runner integration is covered by the existing suite.
"""

import pytest
from ag_ui.core import (
    EventType,
    MessagesSnapshotEvent,
    RunStartedEvent,
    StateSnapshotEvent,
)

from agent_framework_ag_ui import AGUIThreadSnapshot, InMemoryAGUIThreadSnapshotStore
from agent_framework_ag_ui._snapshot_session import ThreadSnapshotSession


async def make_store_with(
    scope: str,
    thread_id: str,
    snapshot: AGUIThreadSnapshot,
) -> InMemoryAGUIThreadSnapshotStore:
    store = InMemoryAGUIThreadSnapshotStore()
    await store.save(scope=scope, thread_id=thread_id, snapshot=snapshot)
    return store


class TestOpenUnscoped:
    """A session without a store or scope is inert but safe to call."""

    async def test_open_without_store_is_disabled(self) -> None:
        session = await ThreadSnapshotSession.open(store=None, scope="user-1", thread_id="t1")
        assert session.enabled is False
        assert session.stored is None

    async def test_open_without_scope_is_disabled(self) -> None:
        store = InMemoryAGUIThreadSnapshotStore()
        session = await ThreadSnapshotSession.open(store=store, scope=None, thread_id="t1")
        assert session.enabled is False
        assert session.stored is None


class TestOpenScoped:
    """A scoped session loads the stored snapshot exactly once at open."""

    async def test_open_loads_stored_snapshot(self) -> None:
        snapshot = AGUIThreadSnapshot(
            messages=[{"id": "m1", "role": "user", "content": "hi"}],
            state={"counter": 1},
        )
        store = await make_store_with("user-1", "t1", snapshot)

        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        assert session.enabled is True
        assert session.stored is not None
        assert session.stored.messages == [{"id": "m1", "role": "user", "content": "hi"}]
        assert session.stored.state == {"counter": 1}

    async def test_open_with_no_prior_snapshot_is_enabled_but_empty(self) -> None:
        store = InMemoryAGUIThreadSnapshotStore()
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")
        assert session.enabled is True
        assert session.stored is None


class TestHydrateEvents:
    """Hydration replays the stored snapshot as a complete run, no agent invoked."""

    async def test_full_snapshot_replays_state_messages_and_interrupts(self) -> None:
        interrupts = [{"id": "int-1", "type": "approval"}]
        snapshot = AGUIThreadSnapshot(
            messages=[{"id": "m1", "role": "user", "content": "hi"}],
            state={"counter": 1},
            interrupt=interrupts,
        )
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        events = [event async for event in session.hydrate_events(run_id="r1")]

        assert [event.type for event in events] == [
            EventType.RUN_STARTED,
            EventType.STATE_SNAPSHOT,
            EventType.MESSAGES_SNAPSHOT,
            EventType.RUN_FINISHED,
        ]
        run_started, state_snapshot, messages_snapshot = events[0], events[1], events[2]
        assert isinstance(run_started, RunStartedEvent)
        assert run_started.run_id == "r1"
        assert run_started.thread_id == "t1"
        assert isinstance(state_snapshot, StateSnapshotEvent)
        assert state_snapshot.snapshot == {"counter": 1}
        assert isinstance(messages_snapshot, MessagesSnapshotEvent)
        assert [message.id for message in messages_snapshot.messages] == ["m1"]
        outcome = getattr(events[3], "outcome", None)
        assert getattr(outcome, "type", None) == "interrupt"

    async def test_no_stored_snapshot_replays_empty_run(self) -> None:
        store = InMemoryAGUIThreadSnapshotStore()
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        events = [event async for event in session.hydrate_events(run_id="r1")]

        assert [event.type for event in events] == [EventType.RUN_STARTED, EventType.RUN_FINISHED]

    async def test_snapshot_without_state_or_interrupts_replays_messages_only(self) -> None:
        snapshot = AGUIThreadSnapshot(messages=[{"id": "m1", "role": "user", "content": "hi"}])
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        events = [event async for event in session.hydrate_events(run_id="r1")]

        assert [event.type for event in events] == [
            EventType.RUN_STARTED,
            EventType.MESSAGES_SNAPSHOT,
            EventType.RUN_FINISHED,
        ]


class TestEffectiveState:
    """Request values overlay stored values; defaults never reset either."""

    async def test_request_overlays_stored_and_defaults_fill_missing(self) -> None:
        snapshot = AGUIThreadSnapshot(messages=[], state={"a": "stored", "b": "stored"})
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        state = session.effective_state(
            request_state={"b": "request", "c": "request"},
            deferred_defaults={"a": "default", "c": "default", "d": "default"},
        )

        assert state == {"a": "stored", "b": "request", "c": "request", "d": "default"}

    async def test_defaults_are_copied_not_aliased(self) -> None:
        store = InMemoryAGUIThreadSnapshotStore()
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")
        defaults = {"items": ["seed"]}

        state = session.effective_state(request_state=None, deferred_defaults=defaults)
        state["items"].append("mutated")

        assert defaults == {"items": ["seed"]}

    async def test_non_dict_request_state_is_ignored(self) -> None:
        snapshot = AGUIThreadSnapshot(messages=[], state={"a": 1})
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        assert session.effective_state(request_state="bogus", deferred_defaults=None) == {"a": 1}

    async def test_disabled_session_uses_request_and_defaults_only(self) -> None:
        session = await ThreadSnapshotSession.open(store=None, scope=None, thread_id="t1")

        state = session.effective_state(
            request_state={"a": "request"},
            deferred_defaults={"a": "default", "b": "default"},
        )

        assert state == {"a": "request", "b": "default"}


class TestResumeSeededMessages:
    """Resume requests carry only the interrupt response; stored history is prepended."""

    async def test_prepends_stored_messages_to_incoming(self) -> None:
        snapshot = AGUIThreadSnapshot(messages=[{"id": "m1", "role": "user", "content": "hi"}])
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")
        incoming = [{"id": "m2", "role": "tool", "content": "approved"}]

        seeded = session.resume_seeded_messages(incoming)

        assert [message["id"] for message in seeded] == ["m1", "m2"]

    async def test_seeded_copies_do_not_alias_stored_snapshot(self) -> None:
        snapshot = AGUIThreadSnapshot(messages=[{"id": "m1", "role": "user", "content": "hi"}])
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        seeded = session.resume_seeded_messages([])
        seeded[0]["content"] = "mutated"

        assert session.stored is not None
        assert session.stored.messages[0]["content"] == "hi"

    async def test_without_stored_snapshot_returns_incoming_unchanged(self) -> None:
        session = await ThreadSnapshotSession.open(store=None, scope=None, thread_id="t1")
        incoming = [{"id": "m2", "role": "user", "content": "hello"}]

        assert session.resume_seeded_messages(incoming) == incoming


class FailingStore:
    """Store whose writes always fail, for exercising save-failure semantics."""

    async def save(self, *, scope, thread_id, snapshot) -> None:
        raise RuntimeError("storage down")

    async def get(self, *, scope, thread_id):
        return None

    async def delete(self, *, scope, thread_id) -> bool:
        return False

    async def clear(self, *, scope=None) -> None:
        return None


class TestSave:
    """One snapshot write commits messages, state, interrupts, and session state together."""

    async def test_save_persists_full_snapshot(self) -> None:
        store = InMemoryAGUIThreadSnapshotStore()
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        await session.save(
            messages=[{"id": "m1", "role": "user", "content": "hi"}],
            state={"counter": 2},
            interrupt=[{"id": "int-1"}],
            session_state={"provider": {"k": "v"}},
        )

        saved = await store.get(scope="user-1", thread_id="t1")
        assert saved is not None
        assert saved.messages == [{"id": "m1", "role": "user", "content": "hi"}]
        assert saved.state == {"counter": 2}
        assert saved.interrupt == [{"id": "int-1"}]
        assert saved.session_state == {"provider": {"k": "v"}}

    async def test_save_on_disabled_session_is_a_noop(self) -> None:
        store = InMemoryAGUIThreadSnapshotStore()
        session = await ThreadSnapshotSession.open(store=store, scope=None, thread_id="t1")

        await session.save(messages=[{"id": "m1"}], state=None, interrupt=None, session_state=None)

        assert await store.get(scope="unused", thread_id="t1") is None

    async def test_store_failure_is_swallowed_and_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        session = await ThreadSnapshotSession.open(store=FailingStore(), scope="user-1", thread_id="t1")

        with caplog.at_level("ERROR"):
            await session.save(messages=[], state=None, interrupt=None, session_state=None)

        assert any("keeping previous snapshot" in record.message for record in caplog.records)


class TestClearInterrupts:
    """Completed interrupts are removed from the latest stored snapshot."""

    async def test_clears_only_matching_interrupt_ids(self) -> None:
        snapshot = AGUIThreadSnapshot(
            messages=[{"id": "m1", "role": "user", "content": "hi"}],
            interrupt=[{"id": "int-1"}, {"id": "int-2"}],
        )
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        await session.clear_interrupts(interrupt_ids={"int-1"})

        saved = await store.get(scope="user-1", thread_id="t1")
        assert saved is not None
        assert saved.interrupt == [{"id": "int-2"}]

    async def test_clears_all_interrupts_when_ids_omitted(self) -> None:
        snapshot = AGUIThreadSnapshot(messages=[], interrupt=[{"id": "int-1"}])
        store = await make_store_with("user-1", "t1", snapshot)
        session = await ThreadSnapshotSession.open(store=store, scope="user-1", thread_id="t1")

        await session.clear_interrupts()

        saved = await store.get(scope="user-1", thread_id="t1")
        assert saved is not None
        assert saved.interrupt is None

    async def test_disabled_session_clear_is_a_noop(self) -> None:
        session = await ThreadSnapshotSession.open(store=None, scope=None, thread_id="t1")
        await session.clear_interrupts(interrupt_ids={"int-1"})

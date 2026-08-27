# Copyright (c) Microsoft. All rights reserved.

"""Single owner of the AG-UI Thread Snapshot lifecycle for a run.

A ThreadSnapshotSession is opened once per run and owns every interaction
with the AG-UI Thread Snapshot store: the load-once read, hydration replay,
the effective-state overlay, resume message seeding, and the save whose
storage failures must never surface on an already-streamed run.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import AsyncGenerator
from typing import Any, cast

from ag_ui.core import (
    BaseEvent,
    MessagesSnapshotEvent,
    RunStartedEvent,
    StateSnapshotEvent,
)

from ._run_common import _build_run_finished_event
from ._snapshots import (
    AGUIThreadSnapshot,
    AGUIThreadSnapshotStore,
    _clear_thread_snapshot_interrupt,
)
from ._utils import make_json_safe

logger = logging.getLogger(__name__)


def _event_messages_to_snapshot_dicts(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert AG-UI message event models back to plain snapshot dictionaries."""
    safe_messages = make_json_safe(messages)
    if not isinstance(safe_messages, list):
        return []
    return [cast(dict[str, Any], message) for message in safe_messages if isinstance(message, dict)]


class ThreadSnapshotSession:
    """Per-run owner of one scoped AG-UI Thread Snapshot.

    Open with :meth:`open`. When the store or scope is not configured the
    session is disabled: reads return nothing and writes are no-ops, so
    callers never branch on configuration themselves.
    """

    def __init__(
        self,
        *,
        store: AGUIThreadSnapshotStore | None,
        scope: str | None,
        thread_id: str,
        stored: AGUIThreadSnapshot | None,
    ) -> None:
        self._store = store
        self._scope = scope
        self._thread_id = thread_id
        self._stored = stored

    @classmethod
    async def open(
        cls,
        *,
        store: AGUIThreadSnapshotStore | None,
        scope: str | None,
        thread_id: str,
    ) -> ThreadSnapshotSession:
        """Open the session, loading the stored snapshot once when scoped."""
        stored: AGUIThreadSnapshot | None = None
        if store is not None and scope is not None:
            stored = await store.get(scope=scope, thread_id=thread_id)
        return cls(store=store, scope=scope, thread_id=thread_id, stored=stored)

    @property
    def enabled(self) -> bool:
        """Whether a store and scope are both configured."""
        return self._store is not None and self._scope is not None

    @property
    def stored(self) -> AGUIThreadSnapshot | None:
        """The snapshot loaded at open, or ``None``."""
        return self._stored

    def rebind_thread_id(self, thread_id: str) -> None:
        """Use a provider-resolved fallback ID for subsequent snapshot operations.

        Runners call this only when the request omitted its AG-UI Thread ID and
        the provider supplies the lifecycle fallback after the session opened.
        """
        self._thread_id = thread_id

    async def hydrate_events(self, *, run_id: str) -> AsyncGenerator[BaseEvent]:
        """Replay the stored snapshot as a complete run without invoking the agent."""
        yield RunStartedEvent(run_id=run_id, thread_id=self._thread_id)
        snapshot = self._stored
        if snapshot is None:
            yield _build_run_finished_event(run_id=run_id, thread_id=self._thread_id)
            return

        if snapshot.state is not None:
            yield StateSnapshotEvent(snapshot=snapshot.state)
        if snapshot.messages:
            yield MessagesSnapshotEvent(messages=snapshot.messages)  # type: ignore[arg-type]
        yield _build_run_finished_event(run_id=run_id, thread_id=self._thread_id, interrupts=snapshot.interrupt)

    def effective_state(
        self,
        *,
        request_state: Any,
        deferred_defaults: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Overlay request state onto stored state, then fill missing keys with defaults.

        Request values overlay stored values with the same keys; endpoint-deferred
        defaults apply only to keys missing from both, so defaults never reset
        persisted state. Default values are copied, never aliased.
        """
        state: dict[str, Any] = {}
        if self._stored is not None and self._stored.state is not None:
            state.update(self._stored.state)
        if isinstance(request_state, dict):
            state.update(request_state)
        if deferred_defaults:
            for key, value in deferred_defaults.items():
                if key not in state:
                    state[key] = copy.deepcopy(value)
        return state

    def resume_seeded_messages(self, incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prepend copies of stored thread history to a resume request's messages.

        Resume requests carry only the synthesized interrupt response; seeding
        with stored history keeps the persisted thread from being truncated.
        """
        if self._stored is None:
            return incoming
        return [copy.deepcopy(message) for message in self._stored.messages] + incoming

    async def save(
        self,
        *,
        messages: list[dict[str, Any]],
        state: dict[str, Any] | None,
        interrupt: list[dict[str, Any]] | None,
        session_state: dict[str, Any] | None,
    ) -> None:
        """Commit the latest thread snapshot in one write when persistence is configured.

        The run has already streamed by the time this is called, so a store
        failure is logged and swallowed; the previous snapshot stays
        authoritative for hydration.
        """
        if self._store is None or self._scope is None:
            return
        try:
            await self._store.save(
                scope=self._scope,
                thread_id=self._thread_id,
                snapshot=AGUIThreadSnapshot(
                    messages=messages,
                    state=state,
                    interrupt=interrupt,
                    session_state=session_state,
                ),
            )
        except Exception:
            logger.exception(
                "Failed to save AG-UI Thread Snapshot for scope=%s thread_id=%s; keeping previous snapshot.",
                self._scope,
                self._thread_id,
            )

    async def clear_interrupts(self, *, interrupt_ids: set[str] | None = None) -> None:
        """Remove completed interrupts from the latest stored snapshot.

        Clears all interrupts when ``interrupt_ids`` is omitted. Failures are
        logged and swallowed for the same reason as :meth:`save`.
        """
        if self._stored is not None and self._stored.interrupt is not None:
            if interrupt_ids is None:
                self._stored.interrupt = None
            else:
                remaining_interrupts = [
                    interrupt
                    for interrupt in self._stored.interrupt
                    if str(interrupt.get("id") or interrupt.get("interruptId")) not in interrupt_ids
                ]
                self._stored.interrupt = remaining_interrupts or None
        if self._store is None or self._scope is None:
            return
        await _clear_thread_snapshot_interrupt(
            snapshot_store=self._store,
            scope=self._scope,
            thread_id=self._thread_id,
            interrupt_ids=interrupt_ids,
        )
